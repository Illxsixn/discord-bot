"""
Gewinnspiel-Cog.

Erstellt Giveaways mit Reaktions-Teilnahme, zieht Gewinner
automatisch nach Ablauf und unterstützt Rerolls.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import Config
from database.database import Database
from database.models import GiveawayRecord
from utils.embeds import apply_brand_footer, error_embed, info_embed, spaced_lines, success_embed
from utils.helpers import parse_duration_minutes
from utils.permissions import bot_can_use_channel, can_manage_giveaways
from utils.reactions import (
    DEFAULT_GIVEAWAY_EMOJI,
    collect_giveaway_entrants,
    emoji_display,
    emoji_to_partial,
    parse_emoji_input,
)

logger = logging.getLogger(__name__)


class GiveawaysCog(commands.GroupCog, group_name="giveaway", group_description="Gewinnspiele verwalten"):
    """Gewinnspiel-System."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db
        self.expire_giveaways.start()

    def cog_unload(self) -> None:
        self.expire_giveaways.cancel()

    async def _resolve_message_channel(
        self,
        guild: discord.Guild,
        channel_id: int,
    ) -> discord.TextChannel | discord.Thread | None:
        """Lädt Textkanal oder Thread für eine Gewinnspiel-Nachricht."""
        channel = self.bot.get_channel(channel_id)
        if isinstance(channel, (discord.TextChannel, discord.Thread)):
            return channel

        try:
            fetched = await self.bot.fetch_channel(channel_id)
        except (discord.NotFound, discord.Forbidden):
            return None

        if isinstance(fetched, (discord.TextChannel, discord.Thread)):
            return fetched
        return None

    def _build_giveaway_embed(self, giveaway: GiveawayRecord) -> discord.Embed:
        """Erstellt Gewinnspiel-Embed."""
        description = spaced_lines(
            f"🎁 **Preis:** {giveaway.prize}",
            f"🏆 **Gewinner:** {giveaway.winner_count}",
            f"{emoji_display(giveaway.emoji)} Reagiere mit {emoji_display(giveaway.emoji)} um teilzunehmen!",
        )
        if not giveaway.ended:
            description += f"\n\n⏱ Endet: {discord.utils.format_dt(giveaway.ends_at, 'R')}"
        else:
            description += "\n\n🔒 **Beendet**"
            if giveaway.winner_ids:
                winners = ", ".join(f"<@{uid}>" for uid in giveaway.winner_ids)
                description += f"\n\n🎉 **Gewinner:** {winners}"
            else:
                description += "\n\n❌ Keine gültigen Teilnehmer."

        embed = info_embed("Gewinnspiel", description)
        apply_brand_footer(embed, prefix=f"Giveaway #{giveaway.id}")
        return embed

    async def _draw_winners(
        self,
        giveaway: GiveawayRecord,
        *,
        reroll: bool = False,
    ) -> tuple[GiveawayRecord | None, str | None]:
        """Lost Gewinner aus und aktualisiert Nachricht."""
        guild = self.bot.get_guild(giveaway.guild_id)
        if guild is None:
            return None, "Server nicht erreichbar."

        channel = await self._resolve_message_channel(guild, giveaway.channel_id)
        if channel is None:
            return None, "Gewinnspiel-Kanal nicht gefunden oder nicht unterstützt."

        allowed, msg = bot_can_use_channel(
            channel,
            read_history=True,
            add_reactions=True,
        )
        if not allowed:
            return None, msg or "Mir fehlen Berechtigungen im Gewinnspiel-Kanal."

        try:
            message = await channel.fetch_message(giveaway.message_id)
        except discord.NotFound:
            return None, "Gewinnspiel-Nachricht wurde gelöscht."
        except discord.Forbidden:
            return None, "Ich kann die Gewinnspiel-Nachricht nicht lesen."

        entrants = await collect_giveaway_entrants(message, giveaway.emoji)
        member_ids = [member.id for member in entrants]

        exclude = set(giveaway.winner_ids) if reroll else set()
        pool = [uid for uid in member_ids if uid not in exclude]

        if not pool:
            if reroll:
                return giveaway, None
            finished = await self.db.finish_giveaway(giveaway.id, [])
            if finished:
                try:
                    await message.edit(embed=self._build_giveaway_embed(finished))
                except discord.HTTPException:
                    pass
            return finished, None

        count = min(giveaway.winner_count, len(pool))
        winner_ids = random.sample(pool, count)

        if reroll:
            finished = await self.db.update_giveaway_winners(giveaway.id, winner_ids)
        else:
            finished = await self.db.finish_giveaway(giveaway.id, winner_ids)

        if finished:
            try:
                await message.edit(embed=self._build_giveaway_embed(finished))
            except discord.HTTPException:
                pass

            if winner_ids:
                result_embed = success_embed(
                    "Gewinnspiel — Reroll" if reroll else "Gewinnspiel beendet",
                    f"**Preis:** {giveaway.prize}",
                    fields=[("Gewinner", ", ".join(f"<@{uid}>" for uid in winner_ids), False)],
                )
                try:
                    await channel.send(embed=result_embed, embed_persistent=True)
                except discord.Forbidden:
                    pass

        return finished, None

    @tasks.loop(seconds=Config.COMMUNITY_TASK_INTERVAL)
    async def expire_giveaways(self) -> None:
        """Beendet abgelaufene Gewinnspiele."""
        now = datetime.now(timezone.utc)
        try:
            for giveaway in await self.db.get_active_giveaways():
                if giveaway.ends_at <= now:
                    _, error = await self._draw_winners(giveaway)
                    if error:
                        logger.warning(
                            "Giveaway #%s konnte nicht beendet werden: %s",
                            giveaway.id,
                            error,
                        )
        except Exception as exc:
            logger.exception("Giveaway-Ablauf-Task fehlgeschlagen: %s", exc)

    @expire_giveaways.before_loop
    async def before_expire_giveaways(self) -> None:
        await self.bot.wait_until_ready()

    @app_commands.command(name="create", description="Erstellt ein Gewinnspiel.")
    @app_commands.describe(
        prize="Preis",
        duration_minutes="Laufzeit in Minuten",
        winners="Anzahl der Gewinner",
        channel="Kanal (Standard: aktueller Kanal)",
        emoji="Teilnahme-Emoji",
    )
    @app_commands.default_permissions(manage_guild=True)
    @can_manage_giveaways()
    async def create(
        self,
        interaction: discord.Interaction,
        prize: str,
        duration_minutes: app_commands.Range[int, 1, 43200],
        winners: app_commands.Range[int, 1, 20] = 1,
        channel: discord.TextChannel | None = None,
        emoji: str = DEFAULT_GIVEAWAY_EMOJI,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return

            if winners > Config.GIVEAWAY_MAX_WINNERS:
                await interaction.followup.send(
                    embed=error_embed("Fehler", f"Maximal **{Config.GIVEAWAY_MAX_WINNERS}** Gewinner."),
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
                read_history=True,
            )
            if not allowed:
                await interaction.followup.send(embed=error_embed("Kanal nicht nutzbar", msg), ephemeral=True)
                return

            ends_at = datetime.now(timezone.utc) + parse_duration_minutes(duration_minutes)
            emoji_key = parse_emoji_input(emoji)

            temp = info_embed("Gewinnspiel", "Wird erstellt …")
            try:
                message = await target.send(embed=temp, embed_persistent=True)
            except discord.Forbidden:
                await interaction.followup.send(
                    embed=error_embed("Fehler", "Ich kann in diesem Kanal keine Nachrichten senden."),
                    ephemeral=True,
                )
                return

            giveaway = await self.db.create_giveaway(
                interaction.guild.id,
                target.id,
                message.id,
                prize,
                winners,
                emoji_key,
                ends_at,
                interaction.user.id,  # type: ignore[union-attr]
            )

            embed = self._build_giveaway_embed(giveaway)
            await message.edit(embed=embed)

            reaction = await emoji_to_partial(self.bot, interaction.guild, emoji_key)
            try:
                await message.add_reaction(reaction)
            except discord.HTTPException:
                await self.db.delete_giveaway(giveaway.id)
                try:
                    await message.delete()
                except discord.HTTPException:
                    pass
                await interaction.followup.send(
                    embed=error_embed(
                        "Fehler",
                        "Teilnahme-Emoji konnte nicht hinzugefügt werden. Gewinnspiel wurde abgebrochen.",
                    ),
                    ephemeral=True,
                )
                return

            await interaction.followup.send(
                embed=success_embed("Gewinnspiel erstellt", f"{message.jump_url}\nID: **#{giveaway.id}**"),
                ephemeral=True,
            )
        except Exception as exc:
            logger.exception("Giveaway create fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="end", description="Beendet ein Gewinnspiel vorzeitig und lost Gewinner aus.")
    @app_commands.describe(giveaway_id="ID des Gewinnspiels")
    @app_commands.default_permissions(manage_guild=True)
    @can_manage_giveaways()
    async def end(self, interaction: discord.Interaction, giveaway_id: int) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return

            giveaway = await self.db.get_giveaway(giveaway_id)
            if giveaway is None or giveaway.guild_id != interaction.guild.id:
                await interaction.followup.send(embed=error_embed("Nicht gefunden", f"Kein Giveaway **#{giveaway_id}**."), ephemeral=True)
                return
            if giveaway.ended:
                await interaction.followup.send(embed=error_embed("Fehler", "Giveaway ist bereits beendet."), ephemeral=True)
                return

            result, error = await self._draw_winners(giveaway)
            if result:
                await interaction.followup.send(embed=success_embed("Giveaway beendet", "Gewinner wurden ausgelost."), ephemeral=True)
            else:
                await interaction.followup.send(
                    embed=error_embed("Fehler", error or "Auslosung fehlgeschlagen."),
                    ephemeral=True,
                )
        except Exception as exc:
            logger.exception("Giveaway end fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="reroll", description="Lost neue Gewinner für ein beendetes Gewinnspiel aus.")
    @app_commands.describe(giveaway_id="ID des Gewinnspiels")
    @app_commands.default_permissions(manage_guild=True)
    @can_manage_giveaways()
    async def reroll(self, interaction: discord.Interaction, giveaway_id: int) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return

            giveaway = await self.db.get_giveaway(giveaway_id)
            if giveaway is None or giveaway.guild_id != interaction.guild.id:
                await interaction.followup.send(embed=error_embed("Nicht gefunden", f"Kein Giveaway **#{giveaway_id}**."), ephemeral=True)
                return
            if not giveaway.ended:
                await interaction.followup.send(embed=error_embed("Fehler", "Giveaway muss zuerst beendet sein."), ephemeral=True)
                return

            # Für Reroll temporär als aktiv markieren durch direkte Auslosung
            result, error = await self._draw_winners(giveaway, reroll=True)
            if result and result.winner_ids:
                await interaction.followup.send(
                    embed=success_embed("Reroll", f"Neue Gewinner: {', '.join(f'<@{uid}>' for uid in result.winner_ids)}"),
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    embed=error_embed(
                        "Fehler",
                        error or "Keine weiteren gültigen Teilnehmer für Reroll.",
                    ),
                    ephemeral=True,
                )
        except Exception as exc:
            logger.exception("Giveaway reroll fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Lädt Gewinnspiel-Cog."""
    db: Database = bot.db  # type: ignore[attr-defined]
    await bot.add_cog(GiveawaysCog(bot, db))
