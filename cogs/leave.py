"""
Leave-System Cog.

Sendet konfigurierbare Abschiedsnachrichten bei Member Leave
und bietet Slash Commands zur Einrichtung.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from database.database import Database
from database.models import DEFAULT_LEAVE_MESSAGE
from utils.embeds import error_embed, info_embed, success_embed
from utils.helpers import format_placeholders
from utils.permissions import is_admin

logger = logging.getLogger(__name__)


@app_commands.default_permissions(administrator=True)
class LeaveCog(commands.GroupCog, group_name="leave", group_description="Leave-System konfigurieren"):
    """Slash-Command-Gruppe für Abschiedsnachrichten."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        """
        Initialisiert den Leave-Cog.

        Args:
            bot: Bot-Instanz.
            db: Datenbank-Instanz.
        """
        self.bot = bot
        self.db = db

    async def send_leave(self, member: discord.Member) -> None:
        """
        Sendet die konfigurierte Leave-Nachricht.

        Args:
            member: Mitglied das den Server verlässt.
        """
        try:
            settings = await self.db.get_guild_settings(member.guild.id)
            if not settings.leave_enabled or not settings.leave_channel_id:
                return

            channel = member.guild.get_channel(settings.leave_channel_id)
            if not isinstance(channel, discord.TextChannel):
                return

            message_text = format_placeholders(settings.leave_message, member, member.guild)

            if settings.leave_use_embed:
                embed = info_embed("Mitglied verlassen", message_text, thumbnail=member.display_avatar.url)
                embed.add_field(name="Benutzer", value=f"{member.display_name} (`{member.id}`)", inline=False)
                await channel.send(embed=embed, embed_persistent=True)
            else:
                await channel.send(content=message_text)

        except Exception as exc:
            logger.exception("Leave-Nachricht fehlgeschlagen: %s", exc)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Event: Mitglied verlässt Server."""
        await self.send_leave(member)

    @app_commands.command(name="setup", description="Richtet das Leave-System schnell ein.")
    @app_commands.describe(channel="Kanal für Abschiedsnachrichten")
    @is_admin()
    async def setup(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        """Schnell-Setup für Leave."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return
            await self.db.update_guild_settings(
                interaction.guild.id,
                leave_enabled=True,
                leave_channel_id=channel.id,
                leave_message=DEFAULT_LEAVE_MESSAGE,
                leave_use_embed=True,
            )
            await interaction.followup.send(
                embed=success_embed("Leave eingerichtet", f"Abschiedsnachrichten in {channel.mention}."),
                ephemeral=True,
            )
        except Exception as exc:
            logger.exception("Leave setup fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="channel", description="Setzt den Leave-Kanal.")
    @app_commands.describe(channel="Textkanal")
    @is_admin()
    async def channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        """Leave-Kanal ändern."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return
            await self.db.update_guild_settings(interaction.guild.id, leave_channel_id=channel.id)
            await interaction.followup.send(
                embed=success_embed("Kanal gesetzt", f"Leave-Kanal: {channel.mention}"),
                ephemeral=True,
            )
        except Exception as exc:
            logger.exception("Leave channel fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="message", description="Setzt die Leave-Nachricht.")
    @app_commands.describe(message="Nachricht mit Platzhaltern", use_embed="Als Embed senden?")
    @is_admin()
    async def message(
        self,
        interaction: discord.Interaction,
        message: str,
        use_embed: bool = True,
    ) -> None:
        """Leave-Nachricht anpassen."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return
            await self.db.update_guild_settings(
                interaction.guild.id,
                leave_message=message,
                leave_use_embed=use_embed,
            )
            await interaction.followup.send(
                embed=success_embed("Nachricht gespeichert", "Leave-Nachricht aktualisiert."),
                ephemeral=True,
            )
        except Exception as exc:
            logger.exception("Leave message fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="enable", description="Aktiviert das Leave-System.")
    @is_admin()
    async def enable(self, interaction: discord.Interaction) -> None:
        """Leave aktivieren."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return
            settings = await self.db.get_guild_settings(interaction.guild.id)
            if not settings.leave_channel_id:
                await interaction.followup.send(
                    embed=error_embed("Fehler", "Bitte zuerst `/leave channel` setzen."),
                    ephemeral=True,
                )
                return
            if settings.leave_enabled:
                await interaction.followup.send(
                    embed=error_embed("Bereits aktiv", "Das Leave-System ist bereits aktiviert."),
                    ephemeral=True,
                )
                return
            await self.db.update_guild_settings(interaction.guild.id, leave_enabled=True)
            await interaction.followup.send(embed=success_embed("Aktiviert", "Leave-System ist aktiv."), ephemeral=True)
        except Exception as exc:
            logger.exception("Leave enable fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="disable", description="Deaktiviert das Leave-System.")
    @is_admin()
    async def disable(self, interaction: discord.Interaction) -> None:
        """Leave deaktivieren."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return
            await self.db.update_guild_settings(interaction.guild.id, leave_enabled=False)
            await interaction.followup.send(embed=success_embed("Deaktiviert", "Leave-System ist aus."), ephemeral=True)
        except Exception as exc:
            logger.exception("Leave disable fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="test", description="Sendet eine Test-Abschiedsnachricht.")
    @is_admin()
    async def test(self, interaction: discord.Interaction) -> None:
        """Testet Leave-Nachricht."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None or not isinstance(interaction.user, discord.Member):
                return
            await self.send_leave(interaction.user)
            await interaction.followup.send(embed=success_embed("Test gesendet", "Leave-Nachricht wurde gesendet."), ephemeral=True)
        except Exception as exc:
            logger.exception("Leave test fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Lädt den Leave-Cog."""
    db: Database = bot.db  # type: ignore[attr-defined]
    await bot.add_cog(LeaveCog(bot, db))
