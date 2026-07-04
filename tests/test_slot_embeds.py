"""Tests für Slot-Embed-Darstellung."""

from __future__ import annotations

from utils.slot_embeds import format_idle_reel_strip, format_reel_strip


def test_format_reel_strip_idle_placeholder() -> None:
    assert "🎰" in format_idle_reel_strip()
    assert format_idle_reel_strip().startswith("▸")


def test_format_reel_strip_normal() -> None:
    line = format_reel_strip(("🍒", "🍋", "🍊"))
    assert line.startswith("▸")
    assert line.endswith("◂")
    assert "**[ 🍒 ]**" in line


def test_format_reel_strip_win() -> None:
    line = format_reel_strip(("7️⃣", "7️⃣", "7️⃣"), won=True)
    assert line.startswith("★")
    assert line.endswith("★")
