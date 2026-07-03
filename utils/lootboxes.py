"""
Lootbox-Logik: Kauf, Öffnen, Trostpreis und Jackpot-Roll.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import discord
from discord.ext import commands

from config import Config
from database.database import Database
from utils.economy_rewards import award_gold
from utils.pet_rewards import award_pet_xp


@dataclass
class LootboxRollResult:
    """Ergebnis einer Lootbox-Öffnung."""

    consolation_gold: int
    consolation_player_xp: int
    consolation_pet_xp: int
    won_jackpot: bool
    jackpot_chance_percent: int
    jackpot_player_xp: int = 0
    jackpot_pet_xp: int = 0


@dataclass
class LootboxApplyResult:
    """Tatsächlich vergebene Belohnungen."""

    gold: int
    player_xp: int
    pet_xp: int
    jackpot_player_xp: int
    jackpot_pet_xp: int


def roll_lootbox() -> LootboxRollResult:
    """
    Würfelt eine Lootbox-Öffnung.

    Jede Box gibt einen Trostpreis (Gold + Spieler-XP + Pet-XP).
    Zusätzlich kann ein Jackpot mit extra XP fallen.
    """
    consolation_gold = random.randint(
        Config.LOOTBOX_CONSOLATION_GOLD_MIN,
        Config.LOOTBOX_CONSOLATION_GOLD_MAX,
    )
    consolation_player_xp = random.randint(
        Config.LOOTBOX_CONSOLATION_XP_MIN,
        Config.LOOTBOX_CONSOLATION_XP_MAX,
    )
    consolation_pet_xp = random.randint(
        Config.LOOTBOX_CONSOLATION_XP_MIN,
        Config.LOOTBOX_CONSOLATION_XP_MAX,
    )

    chance = random.randint(Config.LOOTBOX_XP_CHANCE_MIN, Config.LOOTBOX_XP_CHANCE_MAX)
    won_jackpot = random.randint(1, 100) <= chance
    if not won_jackpot:
        return LootboxRollResult(
            consolation_gold=consolation_gold,
            consolation_player_xp=consolation_player_xp,
            consolation_pet_xp=consolation_pet_xp,
            won_jackpot=False,
            jackpot_chance_percent=chance,
        )

    return LootboxRollResult(
        consolation_gold=consolation_gold,
        consolation_player_xp=consolation_player_xp,
        consolation_pet_xp=consolation_pet_xp,
        won_jackpot=True,
        jackpot_chance_percent=chance,
        jackpot_player_xp=random.randint(Config.LOOTBOX_XP_MIN, Config.LOOTBOX_XP_MAX),
        jackpot_pet_xp=random.randint(Config.LOOTBOX_XP_MIN, Config.LOOTBOX_XP_MAX),
    )


async def apply_lootbox_roll(
    bot: commands.Bot,
    member: discord.Member,
    roll: LootboxRollResult,
    *,
    channel: discord.TextChannel | discord.Thread | None = None,
) -> LootboxApplyResult:
    """Vergibt Trostpreis und optional Jackpot-XP."""
    db: Database = bot.db  # type: ignore[attr-defined]

    gold = await award_gold(db, member, roll.consolation_gold)

    player_xp = roll.consolation_player_xp
    pet_xp = roll.consolation_pet_xp
    jackpot_player_xp = 0
    jackpot_pet_xp = 0

    levels = bot.get_cog("LevelsCog")
    if levels is not None:
        await levels.award_xp(  # type: ignore[attr-defined]
            member,
            player_xp,
            channel=channel,
        )

    await award_pet_xp(
        bot,
        member,
        pet_xp,
        channel=channel,
        count_interaction=False,
        announce_evolution=True,
    )

    if roll.won_jackpot:
        jackpot_player_xp = roll.jackpot_player_xp
        jackpot_pet_xp = roll.jackpot_pet_xp
        if levels is not None:
            await levels.award_xp(  # type: ignore[attr-defined]
                member,
                jackpot_player_xp,
                channel=channel,
            )
        await award_pet_xp(
            bot,
            member,
            jackpot_pet_xp,
            channel=channel,
            count_interaction=False,
            announce_evolution=True,
        )

    return LootboxApplyResult(
        gold=gold,
        player_xp=player_xp,
        pet_xp=pet_xp,
        jackpot_player_xp=jackpot_player_xp,
        jackpot_pet_xp=jackpot_pet_xp,
    )
