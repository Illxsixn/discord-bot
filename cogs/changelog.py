"""
Changelog-Cog — zeigt Bot-Updates und Versionshistorie.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from utils.changelog import build_changelog_embed

logger = logging.getLogger(__name__)


class ChangelogCog(commands.Cog):
    """Slash-Command für den Bot-Changelog."""

    @app_commands.command(name="changelog", description="Zeigt Bot-Updates und die aktuelle Version.")
    @app_commands.guild_only()
    async def changelog(self, interaction: discord.Interaction) -> None:
        """Sendet den Changelog als Embed."""
        await interaction.response.defer()
        try:
            embed = build_changelog_embed()
        except (OSError, KeyError, ValueError, TypeError) as exc:
            logger.exception("Changelog konnte nicht geladen werden: %s", exc)
            from utils.embeds import error_embed

            await interaction.followup.send(
                embed=error_embed("Changelog-Fehler", "Der Changelog ist momentan nicht verfügbar."),
                ephemeral=True,
            )
            return
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    """Lädt den Changelog-Cog."""
    await bot.add_cog(ChangelogCog())
