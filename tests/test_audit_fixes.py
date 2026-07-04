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
