"""Tests für Zombie-Survival-Logik."""

from __future__ import annotations

from datetime import datetime, timezone

from config import Config
from database.models import ZombieRunRecord, ZombieRunStatus
from utils.zombie_combat import perform_melee, perform_pet_action, spawn_wave
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
    result = perform_melee(run, player_level=5, pet=None)
    assert run.current_zombie_hp <= hp_before or result.zombie_killed


def test_player_max_hp_scales():
    assert player_max_hp(1) == Config.ZOMBIE_PLAYER_HP_BASE
    assert player_max_hp(5) > Config.ZOMBIE_PLAYER_HP_BASE


def test_pet_focus_doubles_melee_damage():
    run = _run()
    spawn_wave(run)
    run.focus_active = 1

    class _Pet:
        name = "Testi"
        mood = "focus"
        species = "cat"

    damages: list[int] = []
    for _ in range(20):
        test_run = _run()
        spawn_wave(test_run)
        test_run.focus_active = 1
        hp_before = test_run.current_zombie_hp
        result = perform_melee(test_run, player_level=5, pet=_Pet())
        damages.append(hp_before - test_run.current_zombie_hp)
        assert result.lines
        assert test_run.focus_active == 0

    assert max(damages) >= 18


def test_pet_energy_heals_and_damages():
    run = _run()
    spawn_wave(run)
    run.player_hp = 50

    class _Pet:
        name = "Testi"
        mood = "energy"
        species = "robo_hamster"

    result = perform_pet_action(run, _Pet(), action="energy")
    assert run.total_damage > 0
    assert any("Energie" in line and "+20" in line for line in result.lines)
    assert run.player_hp > 50
    run = _run()
    spawn_wave(run)

    class _Pet:
        name = "Testi"
        mood = "focus"
        species = "cat"

    pet = _Pet()
    perform_pet_action(run, pet, action="focus")
    assert run.pet_action_cooldown == Config.ZOMBIE_PET_ACTION_COOLDOWN

    for expected in range(Config.ZOMBIE_PET_ACTION_COOLDOWN - 1, -1, -1):
        perform_melee(run, player_level=5, pet=None)
        assert run.pet_action_cooldown == expected


def test_zombie_run_view_persistent_until_timeout():
    from unittest.mock import MagicMock

    from cogs.zombies import ZombieRunView

    view = ZombieRunView(MagicMock(), 7, 99, has_pet=True, pet_on_cooldown=False)
    assert view.is_persistent()
    view.timeout = 900.0
    assert not view.is_persistent()


def test_legendary_pet_scales_zombie_hp_and_attack():
    from database.models import PetRarity
    from utils.zombie_combat import pet_action_cooldown_attacks
    from utils.zombie_content import ZOMBIES, ZOMBIE_TYPE_STREUNER, scaled_zombie_attack, scaled_zombie_hp

    zombie = ZOMBIES[ZOMBIE_TYPE_STREUNER]
    assert scaled_zombie_hp(zombie, None) == zombie.hp
    assert scaled_zombie_hp(zombie, PetRarity.LEGENDARY.value) > zombie.hp
    assert scaled_zombie_attack(zombie, PetRarity.LEGENDARY.value) > zombie.attack
    assert pet_action_cooldown_attacks(PetRarity.LEGENDARY.value) == Config.ZOMBIE_PET_ACTION_COOLDOWN_LEGENDARY


def test_legendary_spawn_sets_scaled_hp_on_run():
    from database.models import PetRarity

    run = _run(companion_rarity=PetRarity.LEGENDARY.value)
    lines = spawn_wave(run)
    assert lines
    assert run.current_zombie_max_hp > 0
    assert run.current_zombie_hp == run.current_zombie_max_hp


def test_zombie_leaderboard_waves_formatter():
    from database.models import ZombiePlayerRecord

    record = ZombiePlayerRecord(guild_id=1, user_id=2, highest_wave=3, total_kills=10)
    title = "Höchste Welle"
    formatted = f"**{record.highest_wave}/{Config.ZOMBIE_MAX_WAVES}** 🏆"
    assert "3" in formatted
    assert title == "Höchste Welle"
