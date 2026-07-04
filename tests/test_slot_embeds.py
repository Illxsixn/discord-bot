"""Tests für Slot-Embed-Darstellung."""

from __future__ import annotations

from utils.slot_embeds import build_slots_embed, format_idle_reel_strip, format_reel_strip


def test_format_reel_strip_idle_placeholder() -> None:
    line = format_idle_reel_strip()
    assert "🍒" in line
    assert "🍋" in line
    assert "🍊" in line
    assert line.startswith("▸")
    assert "**" not in line


def test_format_reel_strip_normal() -> None:
    line = format_reel_strip(("🍒", "🍋", "🍊"))
    assert line.startswith("▸")
    assert line.endswith("◂")
    assert "🍒" in line and "🍋" in line and "🍊" in line
    assert "**" not in line


def test_format_reel_strip_win() -> None:
    line = format_reel_strip(("7️⃣", "7️⃣", "7️⃣"), won=True)
    assert line.startswith("★")
    assert line.endswith("★")
    assert "7️⃣" in line
    assert "**" not in line


def test_slots_embed_shows_reels_and_table_in_description() -> None:
    embed = build_slots_embed(gold=500, bet=10, reels=("🍇", "🍇", "🍇"), result_line="Gewonnen!")
    assert embed.description
    assert "🍇" in embed.description
    assert "4×" in embed.description or "12×" in embed.description
    assert not embed.fields


def test_slots_embed_win_uses_artwork_title() -> None:
    embed = build_slots_embed(gold=500, bet=10, reels=("🍒", "🍒", "🍋"), won=True, result_line="Gewonnen!")
    assert embed.title == "🎰 Gewonnen!"
    assert not (embed.title or "").startswith("✅")
