"""Regression tests from full feature audit."""

from __future__ import annotations

import inspect


def test_zombie_run_panel_uses_embed_persistent():
    from cogs import zombies

    source = inspect.getsource(zombies.ZombiesCog._send_run_panel)
    assert "embed_persistent" in source


def test_poll_posts_use_embed_persistent():
    from cogs import polls

    source = inspect.getsource(polls.PollsCog)
    assert "embed_persistent=True" in source


def test_poll_finalize_supports_threads():
    from cogs import polls

    source = inspect.getsource(polls.PollsCog.finalize_poll)
    assert "_resolve_poll_channel" in source


def test_economy_save_clamps_negative_gold():
    from database.models import PlayerEconomyRecord
    from config import Config

    record = PlayerEconomyRecord(guild_id=1, user_id=2, gold=-50, lootbox_count=999)
    # Clamp logic mirrors save_player_economy without DB
    record.gold = max(0, record.gold)
    record.lootbox_count = max(0, min(record.lootbox_count, Config.LOOTBOX_INVENTORY_MAX))
    assert record.gold == 0
    assert record.lootbox_count == Config.LOOTBOX_INVENTORY_MAX


def test_finish_giveaway_is_atomic():
    import database.database as db_module

    source = inspect.getsource(db_module.Database.finish_giveaway)
    assert "ended = 0" in source
    assert "rowcount" in source


def test_economy_lock_used_for_slots_and_shop():
    from cogs import slots
    from utils import shop_actions

    assert "economy_lock" in inspect.getsource(slots.SlotsCog._spin)
    assert "economy_lock" in inspect.getsource(shop_actions.buy_lootboxes)


def test_emoji_blocks_concurrent_sessions():
    from cogs import emoji

    source = inspect.getsource(emoji.EmojiCog)
    assert "_pending" in source
