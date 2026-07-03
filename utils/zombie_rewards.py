"""
Zombie Survival: Belohnungen, XP und Run-Abschluss.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands

from config import Config
from database.database import Database
from database.models import ZombieCooldownType, ZombiePlayerRecord, ZombieRunRecord, ZombieRunStatus
from utils.economy_rewards import award_gold
from utils.pet_rewards import award_pet_xp


@dataclass
class RunRewards:
    """Ausgerechnete Endbelohnungen."""

    gold: int
    player_xp: int
    pet_xp: int
    luck_bonus_percent: int


def _luck_multiplier(luck_uses: int) -> float:
    pct = min(
        luck_uses * Config.ZOMBIE_LUCK_BONUS_PERCENT,
        Config.ZOMBIE_LUCK_BONUS_MAX,
    )
    return 1.0 + pct / 100.0


def calculate_victory_rewards(run: ZombieRunRecord) -> RunRewards:
    """Belohnungen bei Sieg (Boss besiegt)."""
    mult = _luck_multiplier(run.luck_bonus_uses)
    gold = int(random.randint(Config.ZOMBIE_VICTORY_GOLD_MIN, Config.ZOMBIE_VICTORY_GOLD_MAX) * mult)
    gold += run.run_gold // 4
    player_xp = int(random.randint(Config.ZOMBIE_VICTORY_XP_MIN, Config.ZOMBIE_VICTORY_XP_MAX) * mult)
    pet_xp = int(random.randint(Config.ZOMBIE_VICTORY_PET_XP_MIN, Config.ZOMBIE_VICTORY_PET_XP_MAX) * mult)
    return RunRewards(
        gold=max(1, gold),
        player_xp=max(1, player_xp),
        pet_xp=max(1, pet_xp),
        luck_bonus_percent=min(run.luck_bonus_uses * Config.ZOMBIE_LUCK_BONUS_PERCENT, Config.ZOMBIE_LUCK_BONUS_MAX),
    )


def calculate_defeat_rewards(run: ZombieRunRecord) -> RunRewards:
    """Trostbelohnungen bei Niederlage."""
    mult = _luck_multiplier(run.luck_bonus_uses)
    gold = int(random.randint(Config.ZOMBIE_DEFEAT_GOLD_MIN, Config.ZOMBIE_DEFEAT_GOLD_MAX) * mult)
    player_xp = int(random.randint(Config.ZOMBIE_DEFEAT_XP_MIN, Config.ZOMBIE_DEFEAT_XP_MAX) * mult)
    pet_xp = int(Config.ZOMBIE_DEFEAT_PET_XP * mult)
    return RunRewards(
        gold=max(1, gold),
        player_xp=max(1, player_xp),
        pet_xp=max(1, pet_xp),
        luck_bonus_percent=min(run.luck_bonus_uses * Config.ZOMBIE_LUCK_BONUS_PERCENT, Config.ZOMBIE_LUCK_BONUS_MAX),
    )


def zombie_cooldown_remaining(expires_at: datetime | None) -> int | None:
    """Verbleibende Cooldown-Sekunden."""
    if expires_at is None:
        return None
    remaining = (expires_at - datetime.now(timezone.utc)).total_seconds()
    if remaining <= 0:
        return None
    return int(remaining) + 1


async def finalize_zombie_run(
    db: Database,
    bot: commands.Bot,
    member: discord.Member,
    run: ZombieRunRecord,
    profile: ZombiePlayerRecord,
    *,
    completed: bool,
    boss_killed: bool = False,
    channel: discord.TextChannel | discord.Thread | None = None,
) -> RunRewards:
    """Schließt Run ab, vergibt Belohnungen und setzt Cooldown."""
    now = datetime.now(timezone.utc)
    run.updated_at = now

    if completed:
        run.status = ZombieRunStatus.COMPLETED.value
        rewards = calculate_victory_rewards(run)
        profile.runs_completed += 1
        profile.highest_wave = max(profile.highest_wave, run.wave)
    else:
        run.status = ZombieRunStatus.FAILED.value if run.status == ZombieRunStatus.ACTIVE.value else run.status
        rewards = calculate_defeat_rewards(run)
        profile.runs_failed += 1
        profile.highest_wave = max(profile.highest_wave, max(0, run.wave - 1))

    profile.updated_at = now

    await db.save_zombie_run(run)
    await db.save_zombie_player(profile)
    await award_gold(db, member, rewards.gold)

    levels = bot.get_cog("LevelsCog")
    if levels is not None:
        await levels.award_xp(  # type: ignore[attr-defined]
            member,
            rewards.player_xp,
            channel=channel,
            apply_pet_boost=False,
            announce_level_up=False,
        )

    await award_pet_xp(
        bot,
        member,
        rewards.pet_xp,
        channel=channel,
        count_interaction=False,
        announce_evolution=channel is not None,
    )

    expires = now + timedelta(seconds=Config.ZOMBIE_RUN_COOLDOWN)
    await db.set_zombie_cooldown(
        member.guild.id,
        member.id,
        ZombieCooldownType.RUN.value,
        expires,
    )
    return rewards


async def finalize_expired_run(
    db: Database,
    bot: commands.Bot,
    run: ZombieRunRecord,
    profile: ZombiePlayerRecord,
    *,
    member: discord.Member | None = None,
) -> RunRewards:
    """Markiert abgelaufenen Run als gescheitert und vergibt Trostbelohnung."""
    run.status = ZombieRunStatus.EXPIRED.value
    profile.runs_failed += 1
    profile.updated_at = datetime.now(timezone.utc)
    rewards = calculate_defeat_rewards(run)
    await db.save_zombie_run(run)
    await db.save_zombie_player(profile)
    await db.add_player_gold(run.guild_id, run.user_id, rewards.gold)

    if member is not None:
        levels = bot.get_cog("LevelsCog")
        if levels is not None:
            await levels.award_xp(  # type: ignore[attr-defined]
                member,
                rewards.player_xp,
                channel=None,
                apply_pet_boost=False,
                announce_level_up=False,
            )
        await award_pet_xp(
            bot,
            member,
            rewards.pet_xp,
            channel=None,
            count_interaction=False,
            announce_evolution=False,
        )

    expires = datetime.now(timezone.utc) + timedelta(seconds=Config.ZOMBIE_RUN_COOLDOWN)
    await db.set_zombie_cooldown(
        run.guild_id,
        run.user_id,
        ZombieCooldownType.RUN.value,
        expires,
    )
    return rewards
