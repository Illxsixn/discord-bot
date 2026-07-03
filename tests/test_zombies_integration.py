"""Integrationstests für Zombie Survival (DB + Kampflogik)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio

from config import Config
from database.database import Database
from database.models import PetRecord, ZombieRunRecord, ZombieRunStatus
from utils.zombie_combat import advance_to_next_wave, perform_melee, perform_pet_action, spawn_wave
from utils.zombie_content import wave_zombie_list


@pytest_asyncio.fixture
async def db(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "DATABASE_PATH", tmp_path / "zombie_integration.db")
    database = Database()
    await database.connect()
    await database.initialize()
    yield database
    await database.close()


def _new_run(db_id: int = 0, **kwargs) -> ZombieRunRecord:
    now = datetime.now(timezone.utc)
    defaults = dict(
        id=db_id,
        guild_id=100,
        user_id=200,
        status=ZombieRunStatus.ACTIVE.value,
        wave=1,
        max_waves=Config.ZOMBIE_MAX_WAVES,
        player_hp=120,
        player_max_hp=120,
        created_at=now,
        updated_at=now,
    )
    defaults.update(kwargs)
    return ZombieRunRecord(**defaults)


@pytest.mark.asyncio
async def test_save_and_load_zombie_run(db: Database) -> None:
    run = await db.save_zombie_run(_new_run())
    spawn_wave(run)
    run = await db.save_zombie_run(run)

    loaded = await db.get_zombie_run(run.id)
    assert loaded is not None
    assert loaded.in_combat
    assert loaded.current_zombie_key is not None

    active = await db.get_active_zombie_run(100, 200)
    assert active is not None
    assert active.id == run.id


@pytest.mark.asyncio
async def test_wave_clear_then_advance(db: Database) -> None:
    run = await db.save_zombie_run(_new_run())
    spawn_wave(run)

    # Ersten Zombie besiegen
    while run.in_combat and run.player_hp > 0:
        result = perform_melee(run, player_level=5, zombie_level=1, pet=None)
        if result.run_failed:
            break
        if result.wave_cleared and not run.in_combat:
            break
        if result.zombie_killed and run.in_combat:
            continue

    assert run.between_waves or run.wave >= 1
    if run.between_waves:
        advance = advance_to_next_wave(run)
        assert advance.lines
        assert run.wave == 2
        assert run.in_combat


@pytest.mark.asyncio
async def test_pet_focus_then_melee_bonus(db: Database) -> None:
    run = await db.save_zombie_run(_new_run())
    spawn_wave(run)
    pet = PetRecord(id=1, owner_id=200, guild_id=100, name="Buddy", species="robo_hamster")

    focus = perform_pet_action(run, pet, ability="focus")
    assert run.focus_active == 1
    assert not focus.run_failed

    melee = perform_melee(run, player_level=5, zombie_level=1, pet=pet)
    assert run.focus_active == 0
    assert any("Fokus" in line or "triffst" in line.lower() for line in melee.lines)


@pytest.mark.asyncio
async def test_pet_cooldown_blocks_second_use(db: Database) -> None:
    run = await db.save_zombie_run(_new_run())
    spawn_wave(run)
    pet = PetRecord(id=1, owner_id=200, guild_id=100, name="Buddy", species="robo_hamster")

    perform_pet_action(run, pet, ability="energy")
    assert run.pet_action_cooldown > 0

    blocked = perform_pet_action(run, pet, ability="luck")
    assert "Cooldown" in blocked.lines[0]


@pytest.mark.asyncio
async def test_simulate_full_run_to_boss(db: Database) -> None:
    """Simuliert einen kompletten Run bis zum Boss-Sieg (deterministisch genug)."""
    run = await db.save_zombie_run(_new_run(player_hp=500, player_max_hp=500))
    spawn_wave(run)
    pet = PetRecord(id=1, owner_id=200, guild_id=100, name="Buddy", species="mini_drache")
    completed = False
    steps = 0
    max_steps = 200

    while steps < max_steps and run.status == ZombieRunStatus.ACTIVE.value:
        steps += 1
        if run.in_combat:
            if run.pet_action_cooldown == 0 and run.current_zombie_hp > 30:
                perform_pet_action(run, pet, ability="energy")
            result = perform_melee(run, player_level=10, zombie_level=5, pet=pet)
            if result.run_completed:
                completed = True
                break
            if result.run_failed:
                pytest.fail(f"Run failed unexpectedly at wave {run.wave}: {result.lines}")
            continue

        if run.between_waves:
            advance_to_next_wave(run)
            continue

        break

    assert completed, f"Boss not killed after {steps} steps (wave={run.wave}, hp={run.player_hp})"


@pytest.mark.asyncio
async def test_zombie_player_profile_roundtrip(db: Database) -> None:
    profile = await db.get_zombie_player(100, 200)
    profile.total_kills = 5
    profile.level = 2
    profile.xp = 150
    await db.save_zombie_player(profile)

    loaded = await db.get_zombie_player(100, 200)
    assert loaded.total_kills == 5
    assert loaded.level == 2


def test_wave_lists_are_consistent() -> None:
    for wave in range(1, Config.ZOMBIE_MAX_WAVES):
        zombies = wave_zombie_list(wave, run_id=12345)
        assert len(zombies) >= 1
        assert "seuchenbrecher" not in zombies
    assert wave_zombie_list(Config.ZOMBIE_MAX_WAVES, 12345) == ["seuchenbrecher"]
