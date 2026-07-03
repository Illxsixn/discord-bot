"""Tests für Zombie-Survival-Logik."""

from __future__ import annotations

from datetime import datetime, timezone

from config import Config
from database.models import ZombieRunRecord, ZombieRunStatus
from utils.zombie_combat import perform_melee, spawn_wave
from utils.zombie_content import player_max_hp, wave_zombie_list


def _run(**kwargs) -> ZombieRunRecord:
    now = datetime.now(timezone.utc)
    defaults = dict(
        id=42,
        guild_id=1,
        user_id=2,
        status=ZombieRunStatus.ACTIVE.value,
        wave=1,
        max_waves=3,
        player_hp=100,
        player_max_hp=100,
        created_at=now,
        updated_at=now,
    )
    defaults.update(kwargs)
    return ZombieRunRecord(**defaults)


def test_wave_zombie_list_wave3_is_boss():
    zombies = wave_zombie_list(3, 99)
    assert zombies == ["seuchenbrecher"]


def test_spawn_wave_sets_combat():
    run = _run()
    spawn_wave(run)
    assert run.in_combat
    assert run.current_zombie_key is not None
    assert run.current_zombie_hp > 0


def test_melee_reduces_zombie_hp():
    run = _run()
    spawn_wave(run)
    hp_before = run.current_zombie_hp
    result = perform_melee(run, player_level=5, zombie_level=1, pet=None)
    assert run.current_zombie_hp <= hp_before or result.zombie_killed


def test_player_max_hp_scales():
    assert player_max_hp(1, 1) == Config.ZOMBIE_PLAYER_HP_BASE
    assert player_max_hp(5, 3) > Config.ZOMBIE_PLAYER_HP_BASE
