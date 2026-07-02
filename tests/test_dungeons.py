"""Kurze Logik-Tests für Dungeons (ohne Discord)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import datetime, timezone

from database.models import DungeonRunRecord, DungeonRunStatus, PlayerEconomyRecord
from utils.dungeons import (
    apply_hp_regen,
    generate_events,
    player_hp_max,
    resolve_room,
)


def test_player_hp_max_scales_with_level() -> None:
    assert player_hp_max(1) == 100
    assert player_hp_max(5) == 108


def test_regen_does_not_full_heal_from_zero_instantly() -> None:
    economy = PlayerEconomyRecord(
        guild_id=1,
        user_id=2,
        player_hp=0,
        player_hp_max=100,
        last_hp_regen_at=datetime.now(timezone.utc),
    )
    result = apply_hp_regen(economy, 100)
    assert result.player_hp == 0


def test_regen_ticks_add_hp() -> None:
    from datetime import timedelta

    from config import Config

    economy = PlayerEconomyRecord(
        guild_id=1,
        user_id=2,
        player_hp=50,
        player_hp_max=100,
        last_hp_regen_at=datetime.now(timezone.utc) - timedelta(seconds=Config.DUNGEON_HP_REGEN_INTERVAL * 2),
    )
    result = apply_hp_regen(economy, 100)
    assert result.player_hp == 50 + Config.DUNGEON_HP_REGEN_AMOUNT * 2


def test_first_time_player_gets_full_hp() -> None:
    economy = PlayerEconomyRecord(guild_id=1, user_id=2)
    result = apply_hp_regen(economy, 100)
    assert result.player_hp == 100
    assert result.player_hp_max == 100


def test_generate_events_count_in_range() -> None:
    from config import Config

    for _ in range(20):
        events = generate_events()
        assert Config.DUNGEON_ROOM_MIN <= len(events) <= Config.DUNGEON_ROOM_MAX


def test_resolve_room_completes_on_last_room() -> None:
    run = DungeonRunRecord(
        guild_id=1,
        user_id=2,
        pet_id=3,
        status=DungeonRunStatus.ACTIVE.value,
        current_room=2,
        total_rooms=3,
        player_hp=80,
        player_hp_max=100,
        pet_hp=60,
        pet_hp_max=80,
        events=["gold", "gold", "gold"],
        started_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    outcome = resolve_room(run)
    assert outcome.completed
    assert run.rooms_cleared == 3


if __name__ == "__main__":
    test_player_hp_max_scales_with_level()
    test_regen_does_not_full_heal_from_zero_instantly()
    test_regen_ticks_add_hp()
    test_first_time_player_gets_full_hp()
    test_generate_events_count_in_range()
    test_resolve_room_completes_on_last_room()
    print("ok")
