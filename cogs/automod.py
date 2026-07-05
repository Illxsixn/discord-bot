"""
AutoMod-Cog.

Automatische Moderation mit Spam-Schutz, Invite-/Link-Blocker,
Bad-Word-Filter und konfigurierbaren Strafen.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from database.database import Database
from database.models import AutoModPunishment
from utils.embeds import error_embed, info_embed, spaced_lines, spaced_list, success_embed, warning_embed
from utils.helpers import (
    contains_bad_word,
    contains_discord_invite,
    contains_link,
    is_spam,
    parse_duration_minutes,
)
from utils.permissions import is_admin, member_is_moderator

logger = logging.getLogger(__name__)

PUNISHMENT_CHOICES = [
    app_commands.Choice(name="Verwarnung", value="warn"),
    app_commands.Choice(name="Timeout", value="timeout"),
    app_commands.Choice(name="Kick", value="kick"),
    app_commands.Choice(name="Ban", value="ban"),
]


@app_commands.default_permissions(administrator=True)
class AutoModCog(commands.GroupCog, group_name="automod", group_description="AutoMod konfigurieren"):
    """Slash-Command-Gruppe und Message-Listener für AutoMod."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        """
        Initialisiert den AutoMod-Cog.

        Args:
            bot: Bot-Instanz.
            db: Datenbank-Instanz.
        """
        self.bot = bot
        self.db = db

    async def _apply_punishment(
        self,
        message: discord.Message,
        reason: str,
        punishment: AutoModPunishment,
        timeout_minutes: int,
    ) -> None:
        """
        Wendet die konfigurierte AutoMod-Strafe an.

        Args:
            message: Auslösende Nachricht.
            reason: Grund für die Strafe.
            punishment: Straf-Typ.
            timeout_minutes: Timeout-Dauer bei TIMEOUT-Strafe.
        """
        if not isinstance(message.author, discord.Member) or message.guild is None:
            return

        member = message.author
        moderator_reason = f"[AutoMod] {reason}"

        try:
            if punishment == AutoModPunishment.WARN:
                await self.db.add_warning(message.guild.id, member.id, self.bot.user.id, moderator_reason)
            elif punishment == AutoModPunishment.TIMEOUT:
                await member.timeout(parse_duration_minutes(timeout_minutes), reason=moderator_reason)
            elif punishment == AutoModPunishment.KICK:
                await member.kick(reason=moderator_reason)
            elif punishment == AutoModPunishment.BAN:
                await member.ban(reason=moderator_reason, delete_message_seconds=0)
        except discord.Forbidden:
            logger.warning("AutoMod konnte Strafe nicht anwenden: %s", reason)
        except Exception as exc:
            logger.exception("AutoMod Strafe fehlgeschlagen: %s", exc)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """
        Prüft eingehende Nachrichten auf AutoMod-Verstöße.

        Ignoriert Bots und Nachrichten ohne Guild-Kontext.
        """
        if message.author.bot or message.guild is None or not isinstance(message.author, discord.Member):
            return

        # Moderatoren vom AutoMod ausnehmen
        if member_is_moderator(message.author):
            return

        try:
            settings = await self.db.get_guild_settings(message.guild.id)
            if not settings.automod_enabled:
                return

            violation: str | None = None

            # Spam-Schutz
            if settings.spam_protection and is_spam(message.author.id):
                violation = "Spam erkannt"

            # Discord-Einladungen
            elif settings.invite_blocker and contains_discord_invite(message.content):
                violation = "Discord-Einladung nicht erlaubt"

            # Link-Blocker
            elif settings.link_blocker and contains_link(message.content):
                violation = "Links nicht erlaubt"

            # Bad-Word-Filter
            elif settings.bad_word_filter:
                bad = contains_bad_word(message.content, settings.bad_words)
                if bad:
                    violation = f"Verbotenes Wort: `{bad}`"

            if not violation:
                return

            # Nachricht löschen
            try:
                await message.delete()
            except discord.Forbidden:
                pass

            # Strafe anwenden
            await self._apply_punishment(
                message,
                violation,
                settings.automod_punishment,
                settings.automod_timeout_minutes,
            )

            # Warnung an User (ephemeral via DM)
            try:
                await message.author.send(
                    embed=warning_embed(
                        "AutoMod",
                        spaced_lines(
                            f"Deine Nachricht auf **{message.guild.name}** wurde entfernt.",
                            f"**Grund:** {violation}",
                        ),
                    ),
                )
            except discord.Forbidden:
                pass

        except Exception as exc:
            logger.exception("AutoMod on_message fehlgeschlagen: %s", exc)

    @app_commands.command(name="enable", description="Aktiviert AutoMod.")
    @is_admin()
    async def enable(self, interaction: discord.Interaction) -> None:
        """AutoMod aktivieren."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return
            settings = await self.db.get_guild_settings(interaction.guild.id)
            if settings.automod_enabled:
                await interaction.followup.send(
                    embed=error_embed("Bereits aktiv", "AutoMod ist bereits aktiviert."),
                    ephemeral=True,
                )
                return
            await self.db.update_guild_settings(interaction.guild.id, automod_enabled=True)
            await interaction.followup.send(embed=success_embed("AutoMod aktiv", "AutoMod ist eingeschaltet."), ephemeral=True)
        except Exception as exc:
            logger.exception("AutoMod enable fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="disable", description="Deaktiviert AutoMod.")
    @is_admin()
    async def disable(self, interaction: discord.Interaction) -> None:
        """AutoMod deaktivieren."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return
            await self.db.update_guild_settings(interaction.guild.id, automod_enabled=False)
            await interaction.followup.send(embed=success_embed("AutoMod aus", "AutoMod ist deaktiviert."), ephemeral=True)
        except Exception as exc:
            logger.exception("AutoMod disable fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="spam", description="Spam-Schutz ein-/ausschalten.")
    @app_commands.describe(enabled="Spam-Schutz aktivieren?")
    @is_admin()
    async def spam(self, interaction: discord.Interaction, enabled: bool) -> None:
        """Spam-Schutz konfigurieren."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return
            settings = await self.db.get_guild_settings(interaction.guild.id)
            if enabled and settings.spam_protection:
                await interaction.followup.send(
                    embed=error_embed("Bereits aktiv", "Der Spam-Schutz ist bereits aktiviert."),
                    ephemeral=True,
                )
                return
            await self.db.update_guild_settings(interaction.guild.id, spam_protection=enabled)
            status = "aktiviert" if enabled else "deaktiviert"
            await interaction.followup.send(embed=success_embed("Spam-Schutz", f"Spam-Schutz {status}."), ephemeral=True)
        except Exception as exc:
            logger.exception("AutoMod spam fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="invites", description="Discord-Einladungs-Blocker ein-/ausschalten.")
    @app_commands.describe(enabled="Invite-Blocker aktivieren?")
    @is_admin()
    async def invites(self, interaction: discord.Interaction, enabled: bool) -> None:
        """Invite-Blocker konfigurieren."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return
            settings = await self.db.get_guild_settings(interaction.guild.id)
            if enabled and settings.invite_blocker:
                await interaction.followup.send(
                    embed=error_embed("Bereits aktiv", "Der Invite-Blocker ist bereits aktiviert."),
                    ephemeral=True,
                )
                return
            await self.db.update_guild_settings(interaction.guild.id, invite_blocker=enabled)
            status = "aktiviert" if enabled else "deaktiviert"
            await interaction.followup.send(embed=success_embed("Invite-Blocker", f"Invite-Blocker {status}."), ephemeral=True)
        except Exception as exc:
            logger.exception("AutoMod invites fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="links", description="Link-Blocker ein-/ausschalten.")
    @app_commands.describe(enabled="Link-Blocker aktivieren?")
    @is_admin()
    async def links(self, interaction: discord.Interaction, enabled: bool) -> None:
        """Link-Blocker konfigurieren."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return
            settings = await self.db.get_guild_settings(interaction.guild.id)
            if enabled and settings.link_blocker:
                await interaction.followup.send(
                    embed=error_embed("Bereits aktiv", "Der Link-Blocker ist bereits aktiviert."),
                    ephemeral=True,
                )
                return
            await self.db.update_guild_settings(interaction.guild.id, link_blocker=enabled)
            status = "aktiviert" if enabled else "deaktiviert"
            await interaction.followup.send(embed=success_embed("Link-Blocker", f"Link-Blocker {status}."), ephemeral=True)
        except Exception as exc:
            logger.exception("AutoMod links fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="badwords", description="Verbotene Wörter verwalten.")
    @app_commands.describe(action="Aktion", word="Wort (bei add/remove)")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Hinzufügen", value="add"),
            app_commands.Choice(name="Entfernen", value="remove"),
            app_commands.Choice(name="Liste anzeigen", value="list"),
            app_commands.Choice(name="Filter ein/aus", value="toggle"),
        ]
    )
    @is_admin()
    async def badwords(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        word: str | None = None,
        enabled: bool | None = None,
    ) -> None:
        """Bad-Word-Filter verwalten."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return

            settings = await self.db.get_guild_settings(interaction.guild.id)
            words = list(settings.bad_words)

            if action.value == "add":
                if not word:
                    await interaction.followup.send(embed=error_embed("Fehler", "Bitte ein Wort angeben."), ephemeral=True)
                    return
                if word.lower() not in [w.lower() for w in words]:
                    words.append(word)
                await self.db.update_guild_settings(
                    interaction.guild.id,
                    bad_words=words,
                    bad_word_filter=True,
                )
                await interaction.followup.send(embed=success_embed("Wort hinzugefügt", f"`{word}` zur Liste hinzugefügt."), ephemeral=True)

            elif action.value == "remove":
                if not word:
                    await interaction.followup.send(embed=error_embed("Fehler", "Bitte ein Wort angeben."), ephemeral=True)
                    return
                words = [w for w in words if w.lower() != word.lower()]
                await self.db.update_guild_settings(interaction.guild.id, bad_words=words)
                await interaction.followup.send(embed=success_embed("Wort entfernt", f"`{word}` entfernt."), ephemeral=True)

            elif action.value == "list":
                if not words:
                    text = "Keine Wörter konfiguriert."
                else:
                    text = spaced_list([f"`{w}`" for w in words])
                await interaction.followup.send(embed=info_embed("Bad Words", text), ephemeral=True)

            elif action.value == "toggle":
                if enabled is None:
                    await interaction.followup.send(embed=error_embed("Fehler", "Bitte `enabled` setzen."), ephemeral=True)
                    return
                if enabled and settings.bad_word_filter:
                    await interaction.followup.send(
                        embed=error_embed("Bereits aktiv", "Der Bad-Word-Filter ist bereits aktiviert."),
                        ephemeral=True,
                    )
                    return
                await self.db.update_guild_settings(interaction.guild.id, bad_word_filter=enabled)
                status = "aktiviert" if enabled else "deaktiviert"
                await interaction.followup.send(embed=success_embed("Bad-Word-Filter", f"Filter {status}."), ephemeral=True)

        except Exception as exc:
            logger.exception("AutoMod badwords fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="punishment", description="Strafe bei AutoMod-Verstößen festlegen.")
    @app_commands.describe(
        punishment="Art der Strafe",
        timeout_minutes="Timeout-Dauer in Minuten (nur bei Timeout)",
    )
    @app_commands.choices(punishment=PUNISHMENT_CHOICES)
    @is_admin()
    async def punishment(
        self,
        interaction: discord.Interaction,
        punishment: app_commands.Choice[str],
        timeout_minutes: app_commands.Range[int, 1, 40320] | None = 10,
    ) -> None:
        """AutoMod-Strafe konfigurieren."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return

            p = AutoModPunishment(punishment.value)
            updates: dict = {"automod_punishment": p}
            if p == AutoModPunishment.TIMEOUT and timeout_minutes:
                updates["automod_timeout_minutes"] = timeout_minutes

            await self.db.update_guild_settings(interaction.guild.id, **updates)
            await interaction.followup.send(
                embed=success_embed("Strafe gesetzt", f"AutoMod-Strafe: **{punishment.name}**"),
                ephemeral=True,
            )
        except Exception as exc:
            logger.exception("AutoMod punishment fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Lädt den AutoMod-Cog."""
    db: Database = bot.db  # type: ignore[attr-defined]
    await bot.add_cog(AutoModCog(bot, db))
