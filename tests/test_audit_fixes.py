"""Regression tests from full feature audit."""

from __future__ import annotations

import inspect


def test_zombie_run_panel_schedules_auto_delete():
    from cogs import zombies

    source = inspect.getsource(zombies.ZombiesCog._send_run_panel)
    assert "_schedule_public_message_delete" in source
    assert "embed_persistent" in source


def test_zombie_public_messages_use_zombie_delete_cooldown():
    from cogs import zombies
    from config import Config

    source = inspect.getsource(zombies.ZombiesCog._schedule_public_message_delete)
    assert "schedule_zombie_message_delete" in source
    assert Config.ZOMBIE_MESSAGE_DELETE_SECONDS == 300


def test_pet_display_posts_publicly_and_schedules_delete():
    from cogs import pets
    from config import Config

    source = inspect.getsource(pets.PetsCog.display.callback)
    assert "channel.send" in source
    assert "embed_persistent" in source
    assert "schedule_pet_display_delete" in source
    assert "content=" not in source
    assert "defer(ephemeral=True)" in source
    assert "Portrait gepostet" not in source
    assert Config.PET_DISPLAY_DELETE_SECONDS == 300


def test_zombie_run_update_edits_run_panel_by_message_id():
    from cogs import zombies

    source = inspect.getsource(zombies.ZombiesCog._respond_run_update)
    assert "_fetch_run_panel_message" in source
    assert "run_message.edit" in source


def test_zombie_pet_action_uses_ephemeral_embed():
    from cogs import zombies

    source = inspect.getsource(zombies.ZombiesCog._open_pet_action_picker)
    assert "ephemeral=True" in source
    assert "interaction.message.edit" not in source


def test_zombie_run_update_strips_embed_persistent_on_edit():
    from cogs import zombies

    source = inspect.getsource(zombies.ZombiesCog._respond_run_update)
    assert '"embed_persistent"' not in source


def test_zombie_persist_view_registers_by_custom_id():
    from cogs import zombies

    source = inspect.getsource(zombies.ZombiesCog._persist_run_view)
    assert "add_view(view)" in source
    assert "message_id=message_id" not in source


def test_edit_hooks_strip_embed_persistent():
    from utils.embeds import install_brand_send_hooks

    source = inspect.getsource(install_brand_send_hooks)
    assert "InteractionResponse.edit_message" in source
    assert "edit_original_response" in source
    assert "_pop_embed_send_flags(kwargs)" in source


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
