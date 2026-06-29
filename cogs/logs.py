"""
Log-System Cog.

Protokolliert Server-Ereignisse als Embeds und bietet
Slash Commands zur Konfiguration des Log-Kanals.
"""

from __future__ import annotations

import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from config import Config
from database.database import Database
from utils.embeds import error_embed, log_event_embed, success_embed
from utils.helpers import truncate_text
from utils.permissions import is_admin

logger = logging.getLogger(__name__)


@app_commands.default_permissions(administrator=True)
class LogsCog(commands.GroupCog, group_name="logs", group_description="Server-Logs konfigurieren"):
    """Slash-Command-Gruppe und Event-Listener für Server-Logs."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        """
        Initialisiert den Logs-Cog.

        Args:
            bot: Bot-Instanz.
            db: Datenbank-Instanz.
        """
        self.bot = bot
        self.db = db

    async def send_log(self, guild: discord.Guild, embed: discord.Embed) -> None:
        """
        Sendet ein Log-Embed in den konfigurierten Log-Kanal.

        Args:
            guild: Discord-Server.
            embed: Zu sendendes Embed.
        """
        try:
            settings = await self.db.get_guild_settings(guild.id)
            if not settings.logs_enabled or not settings.logs_channel_id:
                return

            channel = guild.get_channel(settings.logs_channel_id)
            if not isinstance(channel, discord.TextChannel):
                return

            await channel.send(embed=embed)
        except Exception as exc:
            logger.exception("Log senden fehlgeschlagen: %s", exc)

    @app_commands.command(name="setup", description="Richtet das Log-System ein.")
    @app_commands.describe(channel="Kanal für Server-Logs")
    @is_admin()
    async def setup(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        """Schnell-Setup für Logs."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return
            await self.db.update_guild_settings(
                interaction.guild.id,
                logs_enabled=True,
                logs_channel_id=channel.id,
            )
            await interaction.followup.send(
                embed=success_embed("Logs eingerichtet", f"Logs werden in {channel.mention} gesendet."),
                ephemeral=True,
            )
        except Exception as exc:
            logger.exception("Logs setup fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="channel", description="Setzt den Log-Kanal.")
    @app_commands.describe(channel="Textkanal")
    @is_admin()
    async def channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        """Log-Kanal ändern."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return
            await self.db.update_guild_settings(interaction.guild.id, logs_channel_id=channel.id)
            await interaction.followup.send(
                embed=success_embed("Kanal gesetzt", f"Log-Kanal: {channel.mention}"),
                ephemeral=True,
            )
        except Exception as exc:
            logger.exception("Logs channel fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="enable", description="Aktiviert Server-Logs.")
    @is_admin()
    async def enable(self, interaction: discord.Interaction) -> None:
        """Logs aktivieren."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return
            settings = await self.db.get_guild_settings(interaction.guild.id)
            if not settings.logs_channel_id:
                await interaction.followup.send(
                    embed=error_embed("Fehler", "Bitte zuerst `/logs channel` setzen."),
                    ephemeral=True,
                )
                return
            if settings.logs_enabled:
                await interaction.followup.send(
                    embed=error_embed("Bereits aktiv", "Das Log-System ist bereits aktiviert."),
                    ephemeral=True,
                )
                return
            await self.db.update_guild_settings(interaction.guild.id, logs_enabled=True)
            await interaction.followup.send(embed=success_embed("Aktiviert", "Log-System ist aktiv."), ephemeral=True)
        except Exception as exc:
            logger.exception("Logs enable fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="disable", description="Deaktiviert Server-Logs.")
    @is_admin()
    async def disable(self, interaction: discord.Interaction) -> None:
        """Logs deaktivieren."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return
            await self.db.update_guild_settings(interaction.guild.id, logs_enabled=False)
            await interaction.followup.send(embed=success_embed("Deaktiviert", "Log-System ist aus."), ephemeral=True)
        except Exception as exc:
            logger.exception("Logs disable fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    # ── Event Listener ──────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Loggt Beitritte (zusätzlich zum Welcome-System)."""
        embed = log_event_embed(
            "Mitglied beigetreten",
            f"{member.mention} ist dem Server beigetreten.",
            fields=[
                ("Benutzer", f"{member} (`{member.id}`)", True),
                ("Account erstellt", discord.utils.format_dt(member.created_at, "R"), True),
                ("Mitglieder", str(member.guild.member_count), True),
            ],
            color=Config.COLOR_SUCCESS,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await self.send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Loggt Austritte."""
        embed = log_event_embed(
            "Mitglied verlassen",
            f"**{member.display_name}** hat den Server verlassen.",
            fields=[("Benutzer-ID", str(member.id), True)],
            color=Config.COLOR_WARNING,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await self.send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User | discord.Member) -> None:
        """Loggt Bans."""
        try:
            ban_entry = await guild.fetch_ban(user)
            reason = ban_entry.reason or "Kein Grund"
        except discord.NotFound:
            reason = "Kein Grund"

        embed = log_event_embed(
            "Mitglied gebannt",
            f"{user.mention} wurde gebannt.",
            fields=[("Grund", reason, False)],
            color=Config.COLOR_ERROR,
        )
        await self.send_log(guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        """Loggt Unbans."""
        embed = log_event_embed(
            "Ban aufgehoben",
            f"{user.mention} wurde entbannt.",
            color=Config.COLOR_SUCCESS,
        )
        await self.send_log(guild, embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        """Loggt gelöschte Nachrichten."""
        if message.author.bot or message.guild is None:
            return

        content = message.content or "*Kein Text (Embed/Datei)*"
        embed = log_event_embed(
            "Nachricht gelöscht",
            truncate_text(content, 500),
            fields=[
                ("Autor", f"{message.author.mention} (`{message.author.id}`)", True),
                ("Kanal", message.channel.mention, True),
            ],
        )
        await self.send_log(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        """Loggt bearbeitete Nachrichten."""
        if before.author.bot or before.guild is None:
            return
        if before.content == after.content:
            return

        embed = log_event_embed(
            "Nachricht bearbeitet",
            "",
            fields=[
                ("Autor", before.author.mention, True),
                ("Kanal", before.channel.mention, True),
                ("Vorher", truncate_text(before.content or "—", 500), False),
                ("Nachher", truncate_text(after.content or "—", 500), False),
            ],
        )
        await self.send_log(before.guild, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """Loggt Rollenänderungen."""
        if before.guild is None:
            return

        added = set(after.roles) - set(before.roles)
        removed = set(before.roles) - set(after.roles)

        if not added and not removed:
            return

        fields: list[tuple[str, str, bool]] = [
            ("Mitglied", after.mention, True),
        ]
        if added:
            fields.append(("Rollen hinzugefügt", ", ".join(r.mention for r in added), False))
        if removed:
            fields.append(("Rollen entfernt", ", ".join(r.mention for r in removed), False))

        embed = log_event_embed("Rollen geändert", "", fields=fields)
        await self.send_log(after.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        """Loggt neue Kanäle."""
        embed = log_event_embed(
            "Kanal erstellt",
            f"{channel.mention} (`{channel.id}`)",
            color=Config.COLOR_SUCCESS,
        )
        await self.send_log(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        """Loggt gelöschte Kanäle."""
        embed = log_event_embed(
            "Kanal gelöscht",
            f"**{channel.name}** (`{channel.id}`)",
            color=Config.COLOR_ERROR,
        )
        await self.send_log(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self,
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel,
    ) -> None:
        """Loggt Kanaländerungen."""
        changes: list[str] = []
        if before.name != after.name:
            changes.append(f"Name: `{before.name}` → `{after.name}`")
        if hasattr(before, "topic") and hasattr(after, "topic") and before.topic != after.topic:
            changes.append("Topic geändert")

        if not changes:
            return

        embed = log_event_embed(
            "Kanal aktualisiert",
            after.mention if hasattr(after, "mention") else after.name,
            fields=[("Änderungen", "\n".join(changes), False)],
        )
        await self.send_log(after.guild, embed)


async def setup(bot: commands.Bot) -> None:
    """Lädt den Logs-Cog."""
    db: Database = bot.db  # type: ignore[attr-defined]
    await bot.add_cog(LogsCog(bot, db))
