"""
Umfragen-Cog.

Erstellt Ja/Nein- und Mehrfach-Umfragen mit Reaktions-Stimmen
und optionaler automatischer Auswertung nach Ablauf.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import Config
from database.database import Database
from database.models import PollRecord, PollType
from utils.embeds import apply_brand_footer, error_embed, info_embed, success_embed
from utils.helpers import parse_duration_minutes
from utils.permissions import bot_can_use_channel, can_manage_community
from utils.reactions import (
    POLL_NUMBER_EMOJIS,
    POLL_YES_NO_EMOJIS,
    count_reaction_votes,
    emoji_to_partial,
    poll_emojis_for_record,
)

logger = logging.getLogger(__name__)


class PollsCog(commands.GroupCog, group_name="poll", group_description="Umfragen erstellen und verwalten"):
    """Umfrage-System."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db
        self.expire_polls.start()

    def cog_unload(self) -> None:
        self.expire_polls.cancel()

    async def _build_poll_embed(self, poll: PollRecord, *, footer: str | None = None) -> discord.Embed:
        """Erstellt Umfrage-Embed."""
        if poll.poll_type == PollType.YES_NO:
            options_text = "\n".join(
                f"{emoji} — **{label}**"
                for emoji, label in zip(POLL_YES_NO_EMOJIS, ("Ja", "Nein"), strict=True)
            )
        else:
            options_text = "\n".join(
                f"{POLL_NUMBER_EMOJIS[index]} — **{option}**"
                for index, option in enumerate(poll.options)
            )

        description = poll.question
        if poll.ends_at and not poll.ended:
            description += f"\n\n⏱ Endet: {discord.utils.format_dt(poll.ends_at, 'R')}"
        if poll.ended:
            description += "\n\n🔒 **Umfrage beendet**"

        embed = info_embed("Umfrage", description, fields=[("Optionen", options_text, False)])
        apply_brand_footer(embed, prefix=footer or f"Umfrage #{poll.id} • Reagiere zum Abstimmen")
        return embed

    async def _add_poll_reactions(self, message: discord.Message, poll: PollRecord) -> None:
        """Fügt Reaktions-Emojis zur Umfrage hinzu."""
        emojis = poll_emojis_for_record(poll)
        guild = message.guild
        for emoji_key in emojis:
            if guild is None:
                reaction = emoji_key
            else:
                reaction = await emoji_to_partial(self.bot, guild, emoji_key)
            try:
                await message.add_reaction(reaction)
            except discord.HTTPException:
                logger.warning("Poll-Reaktion konnte nicht hinzugefügt werden: %s", emoji_key)

    async def finalize_poll(self, poll: PollRecord) -> discord.Embed | None:
        """Wertet Umfrage aus und aktualisiert Nachricht."""
        if poll.ended:
            return None

        ended = await self.db.end_poll(poll.id)
        if ended is None:
            return None
        poll = ended
        guild = self.bot.get_guild(poll.guild_id)
        if guild is None:
            return None

        channel = guild.get_channel(poll.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return None

        try:
            message = await channel.fetch_message(poll.message_id)
        except (discord.NotFound, discord.Forbidden):
            return None

        emojis = poll_emojis_for_record(poll)
        counts = await count_reaction_votes(message, emojis)

        if poll.poll_type == PollType.YES_NO:
            labels = ("Ja", "Nein")
            lines = [
                f"{emoji} **{label}**: **{counts.get(emoji, 0)}** Stimme(n)"
                for emoji, label in zip(emojis, labels, strict=True)
            ]
        else:
            lines = [
                f"{emoji} **{poll.options[index]}**: **{counts.get(emoji, 0)}** Stimme(n)"
                for index, emoji in enumerate(emojis)
            ]

        total = sum(counts.values())
        winner_line = ""
        if counts and total > 0:
            best_emoji = max(counts, key=counts.get)  # type: ignore[arg-type]
            best_votes = counts[best_emoji]
            if poll.poll_type == PollType.YES_NO:
                idx = emojis.index(best_emoji)
                winner_label = ("Ja", "Nein")[idx]
            else:
                winner_label = poll.options[emojis.index(best_emoji)]
            winner_line = f"\n\n🏆 **Führend:** {winner_label} ({best_votes} Stimmen)"

        result_embed = info_embed(
            "Umfrage — Ergebnis",
            poll.question + winner_line,
            fields=[
                ("Stimmen gesamt", str(total), True),
                ("Status", "Beendet", True),
                ("Auswertung", "\n".join(lines), False),
            ],
        )
        apply_brand_footer(result_embed, prefix=f"Umfrage #{poll.id} • Beendet")

        try:
            await message.edit(embed=result_embed)
        except discord.HTTPException as exc:
            logger.warning("Poll-Ergebnis konnte nicht bearbeitet werden: %s", exc)

        return result_embed

    @tasks.loop(seconds=Config.COMMUNITY_TASK_INTERVAL)
    async def expire_polls(self) -> None:
        """Beendet abgelaufene Umfragen automatisch."""
        now = datetime.now(timezone.utc)
        try:
            for poll in await self.db.get_active_polls():
                if poll.ends_at and poll.ends_at <= now:
                    await self.finalize_poll(poll)
        except Exception as exc:
            logger.exception("Poll-Ablauf-Task fehlgeschlagen: %s", exc)

    @expire_polls.before_loop
    async def before_expire_polls(self) -> None:
        await self.bot.wait_until_ready()

    @app_commands.command(name="yesno", description="Erstellt eine Ja/Nein-Umfrage.")
    @app_commands.describe(
        question="Frage",
        channel="Kanal (Standard: aktueller Kanal)",
        duration_minutes="Optional: Dauer in Minuten",
    )
    @app_commands.default_permissions(manage_messages=True)
    @can_manage_community()
    async def yesno(
        self,
        interaction: discord.Interaction,
        question: str,
        channel: discord.TextChannel | None = None,
        duration_minutes: app_commands.Range[int, 1, 10080] | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return

            target = channel or interaction.channel
            if not isinstance(target, (discord.TextChannel, discord.Thread)):
                await interaction.followup.send(embed=error_embed("Fehler", "Ungültiger Kanal."), ephemeral=True)
                return

            allowed, msg = bot_can_use_channel(
                target,
                send=True,
                embed_links=True,
                add_reactions=True,
                manage_messages=True,
            )
            if not allowed:
                await interaction.followup.send(embed=error_embed("Kanal nicht nutzbar", msg), ephemeral=True)
                return

            ends_at = None
            if duration_minutes:
                ends_at = datetime.now(timezone.utc) + parse_duration_minutes(duration_minutes)

            temp_embed = info_embed("Umfrage", question)
            try:
                message = await target.send(embed=temp_embed)
            except discord.Forbidden:
                await interaction.followup.send(
                    embed=error_embed("Fehler", "Ich kann in diesem Kanal keine Nachrichten senden."),
                    ephemeral=True,
                )
                return

            poll = await self.db.create_poll(
                interaction.guild.id,
                target.id,
                message.id,
                question,
                PollType.YES_NO,
                ["Ja", "Nein"],
                interaction.user.id,  # type: ignore[union-attr]
                ends_at,
            )

            embed = await self._build_poll_embed(poll)
            await message.edit(embed=embed)
            await self._add_poll_reactions(message, poll)

            await interaction.followup.send(
                embed=success_embed("Umfrage erstellt", f"{message.jump_url}\nID: **#{poll.id}**"),
                ephemeral=True,
            )
        except Exception as exc:
            logger.exception("Poll yesno fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="multi", description="Erstellt eine Umfrage mit mehreren Optionen.")
    @app_commands.describe(
        question="Frage",
        option1="Option 1",
        option2="Option 2",
        option3="Option 3 (optional)",
        option4="Option 4 (optional)",
        option5="Option 5 (optional)",
        channel="Kanal (Standard: aktueller Kanal)",
        duration_minutes="Optional: Dauer in Minuten",
    )
    @app_commands.default_permissions(manage_messages=True)
    @can_manage_community()
    async def multi(
        self,
        interaction: discord.Interaction,
        question: str,
        option1: str,
        option2: str,
        option3: str | None = None,
        option4: str | None = None,
        option5: str | None = None,
        channel: discord.TextChannel | None = None,
        duration_minutes: app_commands.Range[int, 1, 10080] | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return

            options = [opt for opt in (option1, option2, option3, option4, option5) if opt]
            if len(options) < 2:
                await interaction.followup.send(embed=error_embed("Fehler", "Mindestens 2 Optionen erforderlich."), ephemeral=True)
                return
            if len(options) > Config.POLL_MAX_OPTIONS:
                await interaction.followup.send(
                    embed=error_embed("Fehler", f"Maximal **{Config.POLL_MAX_OPTIONS}** Optionen."),
                    ephemeral=True,
                )
                return

            target = channel or interaction.channel
            if not isinstance(target, (discord.TextChannel, discord.Thread)):
                await interaction.followup.send(embed=error_embed("Fehler", "Ungültiger Kanal."), ephemeral=True)
                return

            allowed, msg = bot_can_use_channel(
                target,
                send=True,
                embed_links=True,
                add_reactions=True,
                manage_messages=True,
            )
            if not allowed:
                await interaction.followup.send(embed=error_embed("Kanal nicht nutzbar", msg), ephemeral=True)
                return

            ends_at = None
            if duration_minutes:
                ends_at = datetime.now(timezone.utc) + parse_duration_minutes(duration_minutes)

            temp_embed = info_embed("Umfrage", question)
            try:
                message = await target.send(embed=temp_embed)
            except discord.Forbidden:
                await interaction.followup.send(
                    embed=error_embed("Fehler", "Ich kann in diesem Kanal keine Nachrichten senden."),
                    ephemeral=True,
                )
                return

            poll = await self.db.create_poll(
                interaction.guild.id,
                target.id,
                message.id,
                question,
                PollType.MULTI,
                options,
                interaction.user.id,  # type: ignore[union-attr]
                ends_at,
            )

            embed = await self._build_poll_embed(poll)
            await message.edit(embed=embed)
            await self._add_poll_reactions(message, poll)

            await interaction.followup.send(
                embed=success_embed("Umfrage erstellt", f"{message.jump_url}\nID: **#{poll.id}**"),
                ephemeral=True,
            )
        except Exception as exc:
            logger.exception("Poll multi fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="end", description="Beendet eine Umfrage vorzeitig und zeigt Ergebnisse.")
    @app_commands.describe(poll_id="ID der Umfrage")
    @app_commands.default_permissions(manage_messages=True)
    @can_manage_community()
    async def end(self, interaction: discord.Interaction, poll_id: int) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return

            poll = await self.db.get_poll(poll_id)
            if poll is None or poll.guild_id != interaction.guild.id:
                await interaction.followup.send(embed=error_embed("Nicht gefunden", f"Keine Umfrage **#{poll_id}**."), ephemeral=True)
                return
            if poll.ended:
                await interaction.followup.send(embed=error_embed("Fehler", "Umfrage ist bereits beendet."), ephemeral=True)
                return

            result = await self.finalize_poll(poll)
            if result:
                await interaction.followup.send(embed=success_embed("Umfrage beendet", "Ergebnis wurde veröffentlicht."), ephemeral=True)
            else:
                await interaction.followup.send(embed=error_embed("Fehler", "Auswertung fehlgeschlagen."), ephemeral=True)
        except Exception as exc:
            logger.exception("Poll end fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Lädt Umfragen-Cog."""
    db: Database = bot.db  # type: ignore[attr-defined]
    await bot.add_cog(PollsCog(bot, db))
