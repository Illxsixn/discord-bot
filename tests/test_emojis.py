"""Tests für Server-Emoji-Hilfsfunktionen."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock


from utils.emojis import (
    animated_emoji_limit,
    derive_emoji_name_from_filename,
    emoji_slot_error,
    parse_custom_emoji,
    validate_attachment,
    validate_emoji_name,
)


def test_parse_custom_emoji_from_mention() -> None:
    parsed = parse_custom_emoji("<:pepe:123456789012345678>")
    assert parsed is not None
    assert parsed.name == "pepe"
    assert parsed.emoji_id == 123456789012345678
    assert parsed.animated is False


def test_parse_custom_emoji_from_animated_mention() -> None:
    parsed = parse_custom_emoji("<a:dance:987654321098765432>")
    assert parsed is not None
    assert parsed.name == "dance"
    assert parsed.animated is True


def test_parse_custom_emoji_rejects_unicode() -> None:
    assert parse_custom_emoji("😀") is None


def test_validate_emoji_name() -> None:
    assert validate_emoji_name("ok_name") is None
    assert validate_emoji_name("a") is not None


def test_derive_emoji_name_from_filename() -> None:
    assert derive_emoji_name_from_filename("Cool-Pet.gif") == "cool_pet"
    assert derive_emoji_name_from_filename("x.png") == "emoji_upload"
    assert len(derive_emoji_name_from_filename("a" * 40 + ".png")) <= 32


def test_validate_attachment_uses_filename_when_content_type_missing() -> None:
    attachment = SimpleNamespace(content_type=None, filename="icon.png", size=1024)
    assert validate_attachment(attachment) is None  # type: ignore[arg-type]


def test_validate_attachment_rejects_webp() -> None:
    attachment = SimpleNamespace(content_type="image/webp", filename="icon.webp", size=1024)
    assert validate_attachment(attachment) is not None  # type: ignore[arg-type]


def test_animated_emoji_limit_without_boost() -> None:
    guild = MagicMock()
    guild.premium_tier = 0
    assert animated_emoji_limit(guild) == 0


def test_emoji_slot_error_blocks_animated_without_boost() -> None:
    guild = MagicMock()
    guild.premium_tier = 0
    guild.emojis = []
    guild.emoji_limit = 50
    assert emoji_slot_error(guild, animated=True) is not None
