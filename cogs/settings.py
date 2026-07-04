"""
Settings-Cog.

Zeigt alle Server-Einstellungen an und ermöglicht das Zurücksetzen
über Slash Commands – ohne Code-Bearbeitung.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from database.database import Database
from utils.embeds import error_embed, info_embed, warning_embed
from utils.helpers import guild_settings_to_fields
from utils.permissions import is_admin

logger = logging.getLogger(__name__)


@app_commands.default_permissions(administrator=True)
class SettingsCog(commands.GroupCog, group_name="settings", group_description="Bot-Einstellungen verwalten"):
    """Slash-Command-Gruppe für globale Server-Einstellungen."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        """
        Initialisiert den Settings-Cog.

        Args:
            bot: Bot-Instanz.
            db: Datenbank-Instanz.
        """
        self.bot = bot
        self.db = db

    @app_commands.command(name="view", description="Zeigt alle aktuellen Server-Einstellungen.")
    @is_admin()
    async def view(self, interaction: discord.Interaction) -> None:
        """Zeigt Einstellungen als Embed."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return

            settings = await self.db.get_guild_settings(interaction.guild.id)
            fields = guild_settings_to_fields(settings)

            # Welcome/Leave Nachrichten als Vorschau
            fields.append(("Welcome-Nachricht", settings.welcome_message[:200], False))
            fields.append(("Leave-Nachricht", settings.leave_message[:200], False))

            if settings.bad_words:
                words_preview = ", ".join(settings.bad_words[:10])
                if len(settings.bad_words) > 10:
                    words_preview += f" … (+{len(settings.bad_words) - 10})"
                fields.append(("Bad Words", words_preview, False))

            embed = info_embed(
                f"Einstellungen – {interaction.guild.name}",
                "Alle konfigurierbaren Optionen für diesen Server.",
                fields=fields,
                thumbnail=interaction.guild.icon.url if interaction.guild.icon else None,
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as exc:
            logger.exception("Settings view fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="reset", description="Setzt alle Einstellungen auf Standard zurück.")
    @is_admin()
    async def reset(self, interaction: discord.Interaction) -> None:
        """Setzt Guild-Einstellungen zurück."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return

            await self.db.reset_guild_settings(interaction.guild.id)
            await interaction.followup.send(
                embed=warning_embed(
                    "Einstellungen zurückgesetzt",
                    "Alle Bot-Einstellungen wurden auf Standardwerte zurückgesetzt.\n"
                    "Warnungen in der Datenbank bleiben erhalten.",
                ),
                ephemeral=True,
            )

        except Exception as exc:
            logger.exception("Settings reset fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Lädt den Settings-Cog."""
    db: Database = bot.db  # type: ignore[attr-defined]
    await bot.add_cog(SettingsCog(bot, db))
