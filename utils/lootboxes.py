"""
Lootbox-Logik: Kauf, Öffnen und XP-Roll.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import discord
from discord.ext import commands

from config import Config
from utils.pet_rewards import award_pet_xp


@dataclass
class LootboxRollResult:
    """Ergebnis einer Lootbox-Öffnung."""

    won_xp: bool
    chance_percent: int
    player_xp: int = 0
    pet_xp: int = 0


def roll_lootbox() -> LootboxRollResult:
    """
    Würfelt eine Lootbox-Öffnung.

    Pro Box wird eine Ziel-Chance zwischen LOOTBOX_XP_CHANCE_MIN und MAX gewürfelt.
    Bei Treffer: LOOTBOX_XP_REWARD Spieler- und Pet-XP.
    """
    chance = random.randint(Config.LOOTBOX_XP_CHANCE_MIN, Config.LOOTBOX_XP_CHANCE_MAX)
    won = random.randint(1, 100) <= chance
    if not won:
        return LootboxRollResult(won_xp=False, chance_percent=chance)
    reward = Config.LOOTBOX_XP_REWARD
    return LootboxRollResult(
        won_xp=True,
        chance_percent=chance,
        player_xp=reward,
        pet_xp=reward,
    )


async def apply_lootbox_roll(
    bot: commands.Bot,
    member: discord.Member,
    roll: LootboxRollResult,
    *,
    channel: discord.TextChannel | discord.Thread | None = None,
) -> tuple[bool, bool]:
    """
    Vergibt XP-Belohnungen aus einem Roll.

    Returns:
        (player_xp_awarded, pet_xp_awarded)
    """
    if not roll.won_xp:
        return False, False

    player_ok = False
    pet_ok = False

    levels = bot.get_cog("LevelsCog")
    if levels is not None:
        player_ok = await levels.award_xp(  # type: ignore[attr-defined]
            member,
            roll.player_xp,
            channel=channel,
        )

    pet_ok = await award_pet_xp(
        bot,
        member,
        roll.pet_xp,
        channel=channel,
        count_interaction=False,
        announce_evolution=True,
    )

    return player_ok, pet_ok
