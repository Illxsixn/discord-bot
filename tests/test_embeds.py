"""Tests für einheitliches Embed-Artwork."""

from __future__ import annotations

from datetime import datetime, timezone

from config import Config
from database.models import (
    PetRecord,
    PlayerEconomyRecord,
    ZombieRunRecord,
    ZombieRunStatus,
)
from utils.embeds import artwork_embed, error_embed, info_embed, success_embed, warning_embed
from utils.shop_embeds import build_shop_embed
from utils.slot_embeds import build_slots_embed
from utils.zombie_embeds import build_help_embed, build_run_embed


def test_all_typed_embeds_use_dark_purple() -> None:
    for builder in (
        lambda: success_embed("OK", "Test"),
        lambda: error_embed("Fehler", "Test"),
        lambda: warning_embed("Warnung", "Test"),
        lambda: info_embed("Info", "Test"),
        lambda: artwork_embed("Artwork", "Test"),
    ):
        embed = builder()
        assert embed.color.value == Config.COLOR_ARTWORK


def test_domain_embeds_use_dark_purple() -> None:
    now = datetime.now(timezone.utc)
    run = ZombieRunRecord(
        id=1,
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
    economy = PlayerEconomyRecord(guild_id=1, user_id=2, gold=100, lootbox_count=0)
    pet = PetRecord(
        id=1,
        owner_id=2,
        guild_id=1,
        species="Testling",
        name="Rex",
    )

    embeds = [
        build_slots_embed(gold=100, bet=10),
        build_shop_embed(economy),
        build_help_embed(),
        build_run_embed(run, pet=pet, economy=economy, player_level=5),
    ]
    for embed in embeds:
        assert embed.color.value == Config.COLOR_ARTWORK
