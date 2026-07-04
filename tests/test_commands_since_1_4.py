"""
Tests für Slash-Commands und Logik seit Changelog 1.4.

Ab 1.4: Dungeons (ersetzt durch /zombies in 1.6), Gold in Profilen
Ab 1.5: /slots
Ab 1.6: /zombies, /shop — /lootbox buy & shop entfernt
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from discord import app_commands
from discord.ext import tasks

from config import Config
from database.database import Database
from main import COGS, DiscordBot
from utils.shop_actions import buy_lootboxes
from utils.slots import resolve_spin
from utils.zombie_combat import perform_melee, spawn_wave
from utils.zombie_content import player_max_hp, wave_zombie_list
from database.models import ZombieRunRecord, ZombieRunStatus


# ── Erwartete Befehle seit Changelog 1.4 ─────────────────────────────

COMMANDS_ADDED_SINCE_1_4: frozenset[str] = frozenset(
    {
        "slots",
        "shop",
        "zombies start",
        "zombies status",
        "zombies resume",
        "zombies profil",
        "zombies interface",
        "zombies leaderboard",
        "zombies help",
    }
)

COMMANDS_REMOVED_SINCE_1_4: frozenset[str] = frozenset(
    {
        "dungeon start",
        "dungeon status",
        "lootbox buy",
        "lootbox shop",
    }
)

LOOTBOX_COMMANDS_KEPT: frozenset[str] = frozenset({"lootbox open", "lootbox leaderboard"})


def _flatten_commands(tree: app_commands.CommandTree) -> set[str]:
    """Sammelt qualified_name aller registrierten Slash-Commands."""
    names: set[str] = set()

    def walk(parent: app_commands.CommandTree | app_commands.Group) -> None:
        if isinstance(parent, app_commands.CommandTree):
            children = parent.get_commands()
        else:
            children = parent.commands
        for cmd in children:
            if isinstance(cmd, app_commands.Group):
                walk(cmd)
            else:
                names.add(cmd.qualified_name)

    walk(tree)
    return names


@pytest_asyncio.fixture
async def bot_commands(monkeypatch: pytest.MonkeyPatch, tmp_path) -> set[str]:
    """Lädt alle Cogs ohne Discord-Sync und gibt Command-Namen zurück."""
    monkeypatch.setattr(Config, "DATABASE_PATH", tmp_path / "test_bot.db")
    monkeypatch.setattr(tasks.Loop, "start", lambda self: None)
    bot = DiscordBot()
    await bot.db.connect()
    await bot.db.initialize()
    for extension in COGS:
        await bot.load_extension(extension)
    names = _flatten_commands(bot.tree)
    await bot.db.close()
    return names


@pytest.mark.asyncio
async def test_new_commands_registered_since_1_4(bot_commands: set[str]) -> None:
    missing = COMMANDS_ADDED_SINCE_1_4 - bot_commands
    assert not missing, f"Fehlende Befehle: {sorted(missing)}"


@pytest.mark.asyncio
async def test_removed_commands_not_registered(bot_commands: set[str]) -> None:
    present = COMMANDS_REMOVED_SINCE_1_4 & bot_commands
    assert not present, f"Entfernte Befehle noch registriert: {sorted(present)}"


@pytest.mark.asyncio
async def test_lootbox_commands_kept(bot_commands: set[str]) -> None:
    missing = LOOTBOX_COMMANDS_KEPT - bot_commands
    assert not missing, f"Lootbox-Befehle fehlen: {sorted(missing)}"


# ── /slots Logik (1.5) ────────────────────────────────────────────────


def test_slots_three_of_a_kind_pays_multiplier() -> None:
    result = resolve_spin(("7️⃣", "7️⃣", "7️⃣"), bet=10)
    assert result.payout == 1000
    assert result.jackpot is True
    assert result.mega_jackpot is True


def test_slots_mega_jackpot_roll_exists() -> None:
    from utils.slots import MEGA_JACKPOT_SYMBOL, spin_reels

    assert MEGA_JACKPOT_SYMBOL == "7️⃣"
    seen_mega = False
    for _ in range(5000):
        reels = spin_reels()
        if reels == ("7️⃣", "7️⃣", "7️⃣"):
            seen_mega = True
            break
    assert seen_mega


def test_slots_two_match_returns_half_bet() -> None:
    result = resolve_spin(("🍒", "🍒", "🍋"), bet=10)
    assert result.payout == 5


def test_slots_no_match_zero_payout() -> None:
    result = resolve_spin(("🍒", "🍋", "🍊"), bet=25)
    assert result.payout == 0


def test_slot_bet_options_configured() -> None:
    assert Config.SLOT_BET_OPTIONS == (5, 10, 25, 50)


# ── /shop Logik (1.6) ─────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "DATABASE_PATH", tmp_path / "shop_test.db")
    database = Database()
    await database.connect()
    await database.initialize()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_shop_buy_lootboxes_success(db: Database) -> None:
    await db.add_player_gold(1, 42, 500)
    ok, embed, economy = await buy_lootboxes(db, 1, 42, count=1)
    assert ok is True
    assert economy is not None
    assert economy.gold == 500 - Config.LOOTBOX_PRICE
    assert economy.lootbox_count == 1
    assert embed.title is not None


@pytest.mark.asyncio
async def test_shop_buy_lootboxes_inventory_full(db: Database) -> None:
    await db.add_player_gold(1, 42, 1000)
    for _ in range(Config.LOOTBOX_INVENTORY_MAX):
        ok, _, economy = await buy_lootboxes(db, 1, 42, count=1)
        assert ok is True
        assert economy is not None
    ok2, embed, economy2 = await buy_lootboxes(db, 1, 42, count=1)
    assert ok2 is False
    assert economy2 is not None
    assert economy2.lootbox_count == Config.LOOTBOX_INVENTORY_MAX
    assert embed.title is not None


@pytest.mark.asyncio
async def test_shop_buy_lootboxes_bulk_success(db: Database) -> None:
    await db.add_player_gold(1, 42, 500)
    ok, embed, economy = await buy_lootboxes(db, 1, 42, count=3)
    assert ok is True
    assert economy is not None
    assert economy.lootbox_count == 3
    assert economy.gold == 500 - Config.LOOTBOX_PRICE * 3
    assert embed.title is not None


@pytest.mark.asyncio
async def test_shop_buy_lootboxes_bulk_over_remaining(db: Database) -> None:
    await db.add_player_gold(1, 42, 500)
    ok, _, economy = await buy_lootboxes(db, 1, 42, count=2)
    assert ok is True
    assert economy is not None
    assert economy.lootbox_count == 2
    ok2, embed, economy2 = await buy_lootboxes(db, 1, 42, count=2)
    assert ok2 is False
    assert economy2 is not None
    assert economy2.lootbox_count == 2
    assert embed.title is not None


@pytest.mark.asyncio
async def test_shop_buy_lootboxes_insufficient_gold(db: Database) -> None:
    ok, embed, economy = await buy_lootboxes(db, 1, 99, count=1)
    assert ok is False
    assert economy is not None
    assert economy.gold == 0
    assert economy.lootbox_count == 0
    assert embed.title is not None


# ── /zombies Logik (1.6, ersetzt /dungeon) ────────────────────────────


def test_zombies_wave3_boss() -> None:
    assert wave_zombie_list(3, 1) == ["seuchenbrecher"]


def test_zombies_spawn_starts_combat() -> None:
    from datetime import datetime, timezone

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
    spawn_wave(run)
    assert run.in_combat
    assert run.current_zombie_key is not None


def test_zombies_melee_damages_or_kills() -> None:
    from datetime import datetime, timezone

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
    spawn_wave(run)
    hp_before = run.current_zombie_hp
    result = perform_melee(run, player_level=5, pet=None)
    assert run.current_zombie_hp <= hp_before or result.zombie_killed


def test_zombies_player_hp_scales() -> None:
    assert player_max_hp(1) == Config.ZOMBIE_PLAYER_HP_BASE
    assert player_max_hp(5) > Config.ZOMBIE_PLAYER_HP_BASE


# Live-Verbindungstest: scripts/smoke_bot.py (Bot muss separat laufen)
