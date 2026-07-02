"""
Hilfsfunktionen für Gold-Belohnungen.
"""

from __future__ import annotations

import random

import discord
from discord.ext import commands

from config import Config
from database.database import Database


async def award_gold(
    db: Database,
    member: discord.Member,
    amount: int,
) -> int:
    """
    Vergibt Gold an ein Mitglied.

    Returns:
        Tatsächlich gutgeschriebenes Gold (0 wenn ungültig).
    """
    if amount <= 0 or member.bot or member.guild is None:
        return 0
    await db.add_player_gold(member.guild.id, member.id, amount)
    return amount


async def award_game_gold(
    bot: commands.Bot,
    member: discord.Member,
) -> int:
    """Vergibt zufälliges Gold für einen Spielsieg."""
    db: Database = bot.db  # type: ignore[attr-defined]
    amount = random.randint(Config.GAME_WIN_GOLD_MIN, Config.GAME_WIN_GOLD_MAX)
    return await award_gold(db, member, amount)
