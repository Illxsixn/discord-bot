"""Tests für Pet-Skills."""

from __future__ import annotations

from utils.pet_skills import pet_skill_fields, pet_skill_level, pet_skills_summary


def test_pet_skill_level_matches_player_level() -> None:
    assert pet_skill_level(1) == 1
    assert pet_skill_level(12) == 12
    assert pet_skill_level(0) == 1


def test_pet_skill_fields_three_skills() -> None:
    fields = pet_skill_fields(5)
    assert len(fields) == 3
    assert all("Level **5**" in value for _name, value, _inline in fields)
    assert fields[0][0].startswith("🎯")
    assert fields[1][0].startswith("⚡")
    assert fields[2][0].startswith("🍀")


def test_pet_skills_summary_lists_all() -> None:
    summary = pet_skills_summary(3)
    assert "Fokus" in summary
    assert "Power" in summary
    assert "Glück" in summary
    assert "**3**" in summary
