"""
Hilfsfunktionen für Spiel-Belohnungen.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from config import Config
from utils.pet_rewards import award_pet_game_xp


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
