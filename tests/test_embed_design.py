"""Tests für Shop-, Profil- und Run-Embed-Layout (ohne Perks-Segmente)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from config import Config
from database.models import PetRecord, PlayerEconomyRecord, ZombiePlayerRecord, ZombieRunRecord, ZombieRunStatus
from utils.shop_embeds import build_shop_embed
from utils.zombie_embeds import build_profile_embed, build_run_embed


def _economy(**kwargs) -> PlayerEconomyRecord:
    defaults = dict(guild_id=1, user_id=2, gold=1250, lootbox_count=2)
    defaults.update(kwargs)
    return PlayerEconomyRecord(**defaults)


def _profile(**kwargs) -> ZombiePlayerRecord:
    defaults = dict(
        guild_id=1,
        user_id=2,
        highest_wave=3,
        total_kills=47,
        boss_kills=2,
        runs_completed=5,
        runs_failed=1,
    )
    defaults.update(kwargs)
    return ZombiePlayerRecord(**defaults)


def _run(**kwargs) -> ZombieRunRecord:
    now = datetime.now(timezone.utc)
    defaults = dict(
        id=1,
        guild_id=1,
        user_id=2,
        status=ZombieRunStatus.ACTIVE.value,
        wave=2,
        max_waves=3,
        player_hp=78,
        player_max_hp=100,
        run_gold=45,
        current_zombie_key="rasender",
        current_zombie_hp=34,
        zombies_remaining=1,
        last_action_text="Du triffst den Rasender für 12 Schaden.",
        created_at=now,
        updated_at=now,
    )
    defaults.update(kwargs)
    return ZombieRunRecord(**defaults)


def _pet() -> PetRecord:
    return PetRecord(
        id=1,
        owner_id=2,
        guild_id=1,
        name="Shadow",
        species="Wolf",
    )


def _field_names(embed) -> list[str]:
    return [field.name for field in embed.fields]


def _embed_text(embed) -> str:
    parts = [embed.title or "", embed.description or ""]
    for field in embed.fields:
        parts.extend([field.name, field.value])
    parts.append(embed.footer.text or "")
    return "\n".join(parts)


def test_shop_embed_matches_mockup_layout():
    embed = build_shop_embed(_economy())

    assert embed.title == "ℹ️ 🏪 Shop"
    assert "Kaufe Lootboxen mit **Gold**" in (embed.description or "")
    assert _field_names(embed) == [
        "Dein Gold",
        "Lootboxen",
        "Preis",
        "📦 Lootbox",
        "Gold verdienen",
    ]
    assert "1,250" in embed.fields[0].value
    assert str(Config.LOOTBOX_PRICE) in embed.fields[2].value
    assert "Perk" not in _embed_text(embed)
    assert "Coming soon" not in _embed_text(embed)


def test_profile_embed_matches_mockup_layout():
    member = MagicMock()
    member.display_name = "MaxMustermann"
    member.mention = "<@123>"
    member.display_avatar.url = "https://cdn.discordapp.com/avatars/123/abc.png"

    embed = build_profile_embed(_profile(), _economy(), _pet(), member)

    assert embed.title == "ℹ️ Zombie Survival — MaxMustermann"
    assert embed.description == "<@123>"
    assert embed.thumbnail.url == member.display_avatar.url
    assert _field_names(embed) == ["Profil", "Statistik", "Aktives Pet"]
    assert "Shadow" in embed.fields[2].value
    assert "Wolf" in embed.fields[2].value
    assert "Perk" not in _embed_text(embed)
    assert "Spieler-Level weiterhin unter /levels level" in embed.footer.text


def test_run_embed_matches_mockup_layout():
    embed = build_run_embed(
        _run(),
        pet=_pet(),
        economy=_economy(),
        player_level=5,
    )

    assert "Welle 2/3" in (embed.title or "")
    assert "Eingestürzter Korridor" in (embed.title or "")
    assert _field_names(embed) == ["Spieler", "Gegner", "🐾 Shadow", "Letzte Aktion"]

    spieler = embed.fields[0].value
    assert "❤️ HP:" in spieler
    assert "1,250" in spieler
    assert "Run-Punkte: **45**" in spieler
    assert "⚔️ Nahkampf:" in spieler
    assert "Upgrade" not in spieler
    assert "Coming soon" not in spieler

    gegner = embed.fields[1].value
    assert "Rasender" in gegner
    assert "Doppelangriff möglich" in gegner

    assert "Fokus" in embed.fields[2].value
    assert "12 Schaden" in embed.fields[3].value
    assert "Kein Abbrechen" in embed.footer.text
