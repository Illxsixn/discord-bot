"""
Hilfsfunktionen für Spiel-Belohnungen und Statistiken.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from config import Config
from utils.pet_rewards import award_pet_game_xp
from database.database import Database
from database.models import BoardGameType


async def award_game_xp(
    bot: commands.Bot,
    member: discord.Member,
    *,
    channel: discord.TextChannel | discord.Thread | None = None,
) -> bool:
    """Vergibt XP für einen Spielsieg über das Level-System."""
    levels = bot.get_cog("LevelsCog")
    if levels is None:
        return False
    result = await levels.award_xp(member, Config.GAME_WIN_XP, channel=channel)  # type: ignore[attr-defined]
    await award_pet_game_xp(bot, member, channel=channel)
    return result


async def record_board_result(
    db: Database,
    guild_id: int,
    player1_id: int,
    player2_id: int,
    winner_id: int | None,
    *,
    game_type: BoardGameType,
) -> None:
    """Aktualisiert Siege/Niederlagen/Unentschieden für beide Spieler."""
    for user_id in (player1_id, player2_id):
        stats = await db.get_game_stats(guild_id, user_id)

        if game_type == BoardGameType.TICTACTOE:
            if winner_id is None:
                stats.ttt_draws += 1
            elif winner_id == user_id:
                stats.ttt_wins += 1
            else:
                stats.ttt_losses += 1
        elif winner_id is None:
            stats.c4_draws += 1
        elif winner_id == user_id:
            stats.c4_wins += 1
        else:
            stats.c4_losses += 1

        await db.save_game_stats(stats)
