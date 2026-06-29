"""
Brettspiel-Verwaltung: Abbruch, Admin-Cleanup und Startup-Aufräumen.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from database.database import Database
from database.models import BoardGameStatus
from utils.board_game_lifecycle import (
    cleanup_stale_board_games,
    finalize_cancelled_game_message,
    game_type_label,
)
from utils.embeds import error_embed, success_embed
from utils.game_locks import game_lock
from utils.permissions import is_admin

logger = logging.getLogger(__name__)


class GamesCog(commands.GroupCog, group_name="game", group_description="Brettspiele verwalten"):
    """Slash-Commands für Brettspiel-Lebenszyklus."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db
        self._startup_cleanup_done = False

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Räumt verwaiste Spiele einmalig nach Bot-Start auf."""
        if self._startup_cleanup_done:
            return
        self._startup_cleanup_done = True

        try:
            count = await cleanup_stale_board_games(self.bot, self.db)
            if count:
                logger.info("Startup-Cleanup: %d verwaiste(s) Brettspiel(e) abgebrochen.", count)
        except Exception:
            logger.exception("Startup-Cleanup für Brettspiele fehlgeschlagen.")

    @app_commands.command(name="cancel", description="Bricht dein laufendes Brettspiel ab.")
    @app_commands.guild_only()
    async def cancel(self, interaction: discord.Interaction) -> None:
        """Beendet pending/active-Spiele des aufrufenden Spielers."""
        await interaction.response.defer(ephemeral=True)
        if interaction.guild is None:
            return

        game = await self.db.user_in_active_board_game(interaction.guild.id, interaction.user.id)
        if game is None:
            await interaction.followup.send(
                embed=error_embed(
                    "Kein aktives Spiel",
                    "Du nimmst an keinem offenen Brettspiel teil.",
                ),
                ephemeral=True,
            )
            return

        member = interaction.user if isinstance(interaction.user, discord.Member) else None

        async with game_lock(game.id):
            fresh = await self.db.get_board_game(game.id)
            if fresh is None or fresh.status not in (
                BoardGameStatus.PENDING,
                BoardGameStatus.ACTIVE,
            ):
                await interaction.followup.send(
                    embed=error_embed("Nicht mehr aktiv", "Dieses Spiel ist bereits beendet."),
                    ephemeral=True,
                )
                return

            await self.db.update_board_game(fresh.id, status=BoardGameStatus.CANCELLED)
            game = fresh

        await finalize_cancelled_game_message(self.bot, game, cancelled_by=member)
        await interaction.followup.send(
            embed=success_embed(
                "Spiel abgebrochen",
                f"**{game_type_label(game.game_type)}** (Spiel `#{game.id}`) wurde beendet.",
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="cleanup",
        description="Bricht alle offenen Brettspiele auf diesem Server ab (Admin).",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    async def cleanup(self, interaction: discord.Interaction) -> None:
        """Admin-Befehl zum Freigeben hängender Spiele."""
        await interaction.response.defer(ephemeral=True)
        if interaction.guild is None:
            return

        games = await self.db.get_open_board_games_for_guild(interaction.guild.id)
        if not games:
            await interaction.followup.send(
                embed=error_embed("Nichts zu tun", "Es gibt keine offenen Brettspiele auf diesem Server."),
                ephemeral=True,
            )
            return

        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        cancelled = 0

        for game in games:
            async with game_lock(game.id):
                fresh = await self.db.get_board_game(game.id)
                if fresh is None or fresh.status not in (
                    BoardGameStatus.PENDING,
                    BoardGameStatus.ACTIVE,
                ):
                    continue
                await self.db.update_board_game(fresh.id, status=BoardGameStatus.CANCELLED)
                await finalize_cancelled_game_message(self.bot, fresh, cancelled_by=member)
                cancelled += 1

        await interaction.followup.send(
            embed=success_embed(
                "Cleanup abgeschlossen",
                f"**{cancelled}** offene(s) Brettspiel(e) wurden abgebrochen.",
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    """Lädt Brettspiel-Verwaltung."""
    db: Database = bot.db  # type: ignore[attr-defined]
    await bot.add_cog(GamesCog(bot, db))
