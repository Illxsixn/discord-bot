"""
Zahlenraten-Spiel (1–100) mit Statistiken und Bestenliste.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from config import Config
from database.database import Database
from database.models import GuessStatsRecord
from utils.embeds import error_embed, info_embed, spaced_list, success_embed
from utils.game_locks import game_lock
from utils.game_rewards import award_game_xp

logger = logging.getLogger(__name__)


class GuessCog(commands.Cog):
    """Zahlenraten mit Kanal-Spielen und Statistiken."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db
        self._guess_cooldowns: dict[tuple[int, int], datetime] = {}

    def _guess_cooldown_remaining(self, guild_id: int, user_id: int) -> timedelta | None:
        """Verbleibende Wartezeit für /guess."""
        expires = self._guess_cooldowns.get((guild_id, user_id))
        if expires is None:
            return None
        remaining = expires - datetime.now(timezone.utc)
        if remaining.total_seconds() <= 0:
            self._guess_cooldowns.pop((guild_id, user_id), None)
            return None
        return remaining

    def _set_guess_cooldown(self, guild_id: int, user_id: int) -> None:
        """Startet den /guess-Cooldown."""
        expires = datetime.now(timezone.utc) + timedelta(seconds=Config.GUESS_COOLDOWN)
        self._guess_cooldowns[(guild_id, user_id)] = expires

    async def _finalize_guess_stats(
        self,
        guild_id: int,
        channel_id: int,
        *,
        winner_id: int | None,
        win_attempts: int | None,
        win_seconds: int | None,
    ) -> None:
        """Schreibt Teilnehmer-Statistiken nach Spielende."""
        participants = await self.db.get_guess_participants(channel_id)
        for user_id, attempts in participants:
            stats = await self.db.get_guess_stats(guild_id, user_id)
            stats.games_played += 1
            stats.total_guesses += attempts
            if user_id == winner_id and win_attempts is not None:
                stats.games_won += 1
                stats.win_attempts_sum += win_attempts
                if stats.best_win_attempts is None or win_attempts < stats.best_win_attempts:
                    stats.best_win_attempts = win_attempts
                if win_seconds is not None and (
                    stats.fastest_win_seconds is None or win_seconds < stats.fastest_win_seconds
                ):
                    stats.fastest_win_seconds = win_seconds
            await self.db.save_guess_stats(stats)

    @app_commands.command(name="guess-start", description="Startet ein neues Zahlenraten-Spiel in diesem Kanal.")
    @app_commands.guild_only()
    async def guess_start(self, interaction: discord.Interaction) -> None:
        """Startet Zahlenraten (1 pro Kanal)."""
        await interaction.response.defer()
        if interaction.guild is None or interaction.channel is None:
            return

        channel_id = interaction.channel.id

        async with game_lock("guess", channel_id):
            if await self.db.get_guess_game(channel_id) is not None:
                await interaction.followup.send(
                    embed=error_embed(
                        "Spiel läuft bereits",
                        "In diesem Kanal läuft schon ein Zahlenraten-Spiel.\n"
                        "Nutze `/guess`, um zu raten.",
                    ),
                    ephemeral=True,
                )
                return

            target = random.randint(Config.GUESS_MIN, Config.GUESS_MAX)
            await self.db.create_guess_game(interaction.guild.id, channel_id, target)

        await interaction.followup.send(
            embed=success_embed(
                "Zahlenraten gestartet",
                f"{interaction.user.mention} hat ein neues Spiel gestartet!\n\n"
                f"Rate eine Zahl zwischen **{Config.GUESS_MIN}** und **{Config.GUESS_MAX}** mit `/guess`.",
            ),
            embed_persistent=True,
        )

    @app_commands.command(
        name="guess",
        description="Gibt einen Tipp für das laufende Zahlenraten-Spiel ab (Cooldown: 5 Min.).",
    )
    @app_commands.guild_only()
    @app_commands.describe(zahl="Deine geratene Zahl (1–100)")
    async def guess(
        self,
        interaction: discord.Interaction,
        zahl: app_commands.Range[int, 1, 100],
    ) -> None:
        """Verarbeitet einen Rateversuch."""
        await interaction.response.defer(ephemeral=True)
        if interaction.guild is None or interaction.channel is None:
            return

        remaining = self._guess_cooldown_remaining(interaction.guild.id, interaction.user.id)
        if remaining is not None:
            minutes = int(remaining.total_seconds() // 60)
            seconds = int(remaining.total_seconds() % 60)
            await interaction.followup.send(
                embed=error_embed(
                    "Cooldown",
                    f"Du kannst erst in **{minutes}m {seconds}s** wieder raten.",
                ),
                ephemeral=True,
            )
            return

        channel_id = interaction.channel.id
        target_number: int | None = None
        attempts = 0

        async with game_lock("guess", channel_id):
            game = await self.db.get_guess_game(channel_id)
            if game is None:
                await interaction.followup.send(
                    embed=error_embed(
                        "Kein Spiel aktiv",
                        "In diesem Kanal läuft kein Zahlenraten-Spiel.\nStarte eins mit `/guess-start`.",
                    ),
                    ephemeral=True,
                )
                return

            attempts = await self.db.increment_guess_attempt(channel_id, interaction.user.id)

            if zahl < game.target_number:
                self._set_guess_cooldown(interaction.guild.id, interaction.user.id)
                await interaction.followup.send(
                    embed=info_embed(
                        "Tipp",
                        f"Die gesuchte Zahl ist **höher**.\nVersuch **#{attempts}**",
                    ),
                    ephemeral=True,
                )
                return

            if zahl > game.target_number:
                self._set_guess_cooldown(interaction.guild.id, interaction.user.id)
                await interaction.followup.send(
                    embed=info_embed(
                        "Tipp",
                        f"Die gesuchte Zahl ist **niedriger**.\nVersuch **#{attempts}**",
                    ),
                    ephemeral=True,
                )
                return

            target_number = game.target_number
            elapsed = int((datetime.now(timezone.utc) - game.started_at).total_seconds())
            await self._finalize_guess_stats(
                interaction.guild.id,
                channel_id,
                winner_id=interaction.user.id,
                win_attempts=attempts,
                win_seconds=elapsed,
            )
            await self.db.delete_guess_game(channel_id)

        self._set_guess_cooldown(interaction.guild.id, interaction.user.id)

        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        channel = interaction.channel if isinstance(interaction.channel, (discord.TextChannel, discord.Thread)) else None
        xp_note = ""
        if member is not None and await award_game_xp(self.bot, member, channel=channel):
            xp_note = f"\n\n🎁 Du erhältst **{Config.GAME_WIN_XP} XP**!"

        await interaction.followup.send(
            embed=success_embed(
                "Richtig geraten!",
                f"🎉 Du hast die Zahl **{target_number}** in **{attempts}** Versuchen erraten!{xp_note}",
            ),
            ephemeral=True,
        )

        if isinstance(interaction.channel, discord.abc.Messageable):
            await interaction.channel.send(
                embed=success_embed(
                    "Spiel beendet",
                    f"{interaction.user.mention} hat das Zahlenraten gewonnen "
                    f"(Zahl **{target_number}**, **{attempts}** Versuche).",
                ),
                embed_persistent=True,
            )

    def _format_stats_line(self, guild: discord.Guild, stats: GuessStatsRecord, *, suffix: str) -> str:
        member = guild.get_member(stats.user_id)
        name = member.display_name if member else f"User `{stats.user_id}`"
        return f"**{name}** — {suffix}"

    @app_commands.command(name="guess-leaderboard", description="Zeigt die Zahlenraten-Bestenliste.")
    @app_commands.guild_only()
    async def guess_leaderboard(self, interaction: discord.Interaction) -> None:
        """Bestenliste für Zahlenraten."""
        await interaction.response.defer(ephemeral=True)
        if interaction.guild is None:
            return

        wins = await self.db.get_guess_leaderboard_wins(interaction.guild.id, limit=5)
        attempts = await self.db.get_guess_leaderboard_attempts(interaction.guild.id, limit=5)
        fastest = await self.db.get_guess_leaderboard_fastest(interaction.guild.id, limit=5)

        win_lines = [
            self._format_stats_line(interaction.guild, row, suffix=f"**{row.games_won}** Siege")
            for row in wins
        ] or ["Noch keine Siege."]
        attempt_lines = [
            self._format_stats_line(
                interaction.guild,
                row,
                suffix=(
                    f"**{row.average_win_attempts:.1f}** Ø Versuche"
                    if row.average_win_attempts is not None
                    else f"**{row.best_win_attempts}** Versuche"
                ),
            )
            for row in attempts
        ] or ["Noch keine Daten."]
        fast_lines = [
            self._format_stats_line(
                interaction.guild,
                row,
                suffix=f"**{row.fastest_win_seconds}s** (schnellster Sieg)",
            )
            for row in fastest
        ] or ["Noch keine Daten."]

        embed = info_embed(
            f"Zahlenraten — {interaction.guild.name}",
            "Bestenliste für diesen Server.",
            fields=[
                ("Meiste Siege", spaced_list(win_lines), False),
                ("Wenigste Ø Versuche", spaced_list(attempt_lines), False),
                ("Schnellster Sieg", spaced_list(fast_lines), False),
            ],
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Lädt den Guess-Cog."""
    db: Database = bot.db  # type: ignore[attr-defined]
    cog = GuessCog(bot, db)
    await bot.add_cog(cog)
