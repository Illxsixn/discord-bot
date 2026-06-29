"""
Hilfsfunktionen für Pet-XP aus anderen Systemen.
"""

from __future__ import annotations

import random

import discord
from discord.ext import commands

from config import Config


async def award_pet_xp(
    bot: commands.Bot,
    member: discord.Member,
    amount: int,
    *,
    channel: discord.TextChannel | discord.Thread | None = None,
    count_interaction: bool = False,
    announce_evolution: bool = True,
) -> bool:
    """Vergibt Pet-XP über das Pets-System."""
    if amount <= 0 or member.bot:
        return False
    pets = bot.get_cog("PetsCog")
    if pets is None:
        return False
    return await pets.award_pet_xp(  # type: ignore[attr-defined]
        member,
        amount,
        channel=channel,
        count_interaction=count_interaction,
        announce_evolution=announce_evolution,
    )


async def award_pet_activity_xp(
    bot: commands.Bot,
    member: discord.Member,
    *,
    channel: discord.TextChannel | discord.Thread | None = None,
) -> bool:
    """Vergibt Pet-XP für Serveraktivität (Nachrichten)."""
    amount = random.randint(Config.PET_XP_ACTIVITY_MIN, Config.PET_XP_ACTIVITY_MAX)
    return await award_pet_xp(
        bot,
        member,
        amount,
        channel=channel,
        count_interaction=False,
        announce_evolution=False,
    )


async def award_pet_game_xp(
    bot: commands.Bot,
    member: discord.Member,
    *,
    channel: discord.TextChannel | discord.Thread | None = None,
) -> bool:
    """Vergibt Pet-XP für abgeschlossene Spiele."""
    amount = random.randint(Config.PET_XP_GAME_MIN, Config.PET_XP_GAME_MAX)
    return await award_pet_xp(
        bot,
        member,
        amount,
        channel=channel,
        count_interaction=False,
        announce_evolution=False,
    )
