"""
Welcome-System Cog.

Sendet konfigurierbare Willkommensnachrichten bei Member Join
und bietet Slash Commands zur Einrichtung.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from database.database import Database
from database.models import DEFAULT_WELCOME_MESSAGE
from utils.embeds import error_embed, info_embed, success_embed
from utils.helpers import format_join_date, format_placeholders, generate_welcome_image
from utils.permissions import is_admin

logger = logging.getLogger(__name__)


@app_commands.default_permissions(administrator=True)
class WelcomeCog(commands.GroupCog, group_name="welcome", group_description="Welcome-System konfigurieren"):
    """Slash-Command-Gruppe für Willkommensnachrichten."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        """
        Initialisiert den Welcome-Cog.

        Args:
            bot: Bot-Instanz.
            db: Datenbank-Instanz.
        """
        self.bot = bot
        self.db = db

    async def send_welcome(self, member: discord.Member) -> None:
        """
        Sendet die konfigurierte Willkommensnachricht.

        Args:
            member: Neues Servermitglied.
        """
        try:
            settings = await self.db.get_guild_settings(member.guild.id)
            if not settings.welcome_enabled or not settings.welcome_channel_id:
                return

            channel = member.guild.get_channel(settings.welcome_channel_id)
            if not isinstance(channel, discord.TextChannel):
                return

            message_text = format_placeholders(settings.welcome_message, member, member.guild)
            files: list[discord.File] = []

            if settings.welcome_image_enabled:
                welcome_file = await generate_welcome_image(member)
                if welcome_file:
                    files.append(welcome_file)

            if settings.welcome_use_embed:
                if settings.welcome_show_join_date:
                    fields = [
                        ("Beigetreten", format_join_date(member), True),
                        ("Mitglied", member.mention, True),
                        ("ID", str(member.id), True),
                    ]
                else:
                    fields = [
                        ("Mitglied", member.mention, True),
                        ("ID", str(member.id), True),
                        ("Server", member.guild.name, True),
                    ]

                embed = info_embed(
                    "Willkommen!",
                    message_text,
                    fields=fields,
                    thumbnail=member.display_avatar.url,
                    image="attachment://welcome.png" if files else None,
                )

                if files:
                    await channel.send(embed=embed, files=files, embed_persistent=True)
                else:
                    await channel.send(embed=embed, embed_persistent=True)
            else:
                if files:
                    await channel.send(content=message_text, files=files)
                else:
                    await channel.send(content=message_text)

        except Exception as exc:
            logger.exception("Welcome-Nachricht fehlgeschlagen: %s", exc)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Event: Mitglied tritt Server bei."""
        await self.send_welcome(member)

    @app_commands.command(name="setup", description="Richtet das Welcome-System schnell ein.")
    @app_commands.describe(channel="Kanal für Willkommensnachrichten")
    @is_admin()
    async def setup(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        """Schnell-Setup für Welcome."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return

            await self.db.update_guild_settings(
                interaction.guild.id,
                welcome_enabled=True,
                welcome_channel_id=channel.id,
                welcome_message=DEFAULT_WELCOME_MESSAGE,
                welcome_use_embed=True,
            )
            await interaction.followup.send(
                embed=success_embed(
                    "Welcome eingerichtet",
                    f"Willkommensnachrichten werden in {channel.mention} gesendet.",
                ),
                ephemeral=True,
            )
        except Exception as exc:
            logger.exception("Welcome setup fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="channel", description="Setzt den Welcome-Kanal.")
    @app_commands.describe(channel="Textkanal")
    @is_admin()
    async def channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        """Welcome-Kanal ändern."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return
            await self.db.update_guild_settings(interaction.guild.id, welcome_channel_id=channel.id)
            await interaction.followup.send(
                embed=success_embed("Kanal gesetzt", f"Welcome-Kanal: {channel.mention}"),
                ephemeral=True,
            )
        except Exception as exc:
            logger.exception("Welcome channel fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="message", description="Setzt die Welcome-Nachricht (Platzhalter unterstützt).")
    @app_commands.describe(
        message="Nachricht mit {user}, {username}, {userid}, {server}, {membercount}",
        use_embed="Als Embed senden?",
        show_join_date="Beitrittsdatum anzeigen?",
        image_enabled="Welcome-Bild generieren?",
    )
    @is_admin()
    async def message(
        self,
        interaction: discord.Interaction,
        message: str,
        use_embed: bool = True,
        show_join_date: bool = True,
        image_enabled: bool = False,
    ) -> None:
        """Welcome-Nachricht anpassen."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return
            await self.db.update_guild_settings(
                interaction.guild.id,
                welcome_message=message,
                welcome_use_embed=use_embed,
                welcome_show_join_date=show_join_date,
                welcome_image_enabled=image_enabled,
            )
            await interaction.followup.send(
                embed=success_embed("Nachricht gespeichert", "Die Welcome-Nachricht wurde aktualisiert."),
                ephemeral=True,
            )
        except Exception as exc:
            logger.exception("Welcome message fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="enable", description="Aktiviert das Welcome-System.")
    @is_admin()
    async def enable(self, interaction: discord.Interaction) -> None:
        """Welcome aktivieren."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return
            settings = await self.db.get_guild_settings(interaction.guild.id)
            if not settings.welcome_channel_id:
                await interaction.followup.send(
                    embed=error_embed("Fehler", "Bitte zuerst einen Kanal mit `/welcome channel` setzen."),
                    ephemeral=True,
                )
                return
            if settings.welcome_enabled:
                await interaction.followup.send(
                    embed=error_embed("Bereits aktiv", "Das Welcome-System ist bereits aktiviert."),
                    ephemeral=True,
                )
                return
            await self.db.update_guild_settings(interaction.guild.id, welcome_enabled=True)
            await interaction.followup.send(embed=success_embed("Aktiviert", "Welcome-System ist aktiv."), ephemeral=True)
        except Exception as exc:
            logger.exception("Welcome enable fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="disable", description="Deaktiviert das Welcome-System.")
    @is_admin()
    async def disable(self, interaction: discord.Interaction) -> None:
        """Welcome deaktivieren."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return
            await self.db.update_guild_settings(interaction.guild.id, welcome_enabled=False)
            await interaction.followup.send(embed=success_embed("Deaktiviert", "Welcome-System ist aus."), ephemeral=True)
        except Exception as exc:
            logger.exception("Welcome disable fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="test", description="Sendet eine Test-Willkommensnachricht.")
    @is_admin()
    async def test(self, interaction: discord.Interaction) -> None:
        """Testet Welcome-Nachricht."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None or not isinstance(interaction.user, discord.Member):
                return
            await self.send_welcome(interaction.user)
            await interaction.followup.send(embed=success_embed("Test gesendet", "Welcome-Nachricht wurde gesendet."), ephemeral=True)
        except Exception as exc:
            logger.exception("Welcome test fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Lädt den Welcome-Cog."""
    db: Database = bot.db  # type: ignore[attr-defined]
    await bot.add_cog(WelcomeCog(bot, db))
