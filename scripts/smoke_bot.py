#!/usr/bin/env python3
"""Kurzer Live-Smoke-Test: Bot starten, Cogs & neue Befehle prüfen, wieder beenden."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import Config  # noqa: E402
from main import COGS, DiscordBot  # noqa: E402
from tests.test_commands_since_1_4 import (  # noqa: E402
    COMMANDS_ADDED_SINCE_1_4,
    COMMANDS_REMOVED_SINCE_1_4,
    LOOTBOX_COMMANDS_KEPT,
    _flatten_commands,
)


async def main() -> int:
    try:
        Config.validate()
    except ValueError as exc:
        print(f"SKIP: {exc}")
        return 0

    bot = DiscordBot()
    ready = asyncio.Event()

    async def patched_setup_hook() -> None:
        from utils.embeds import install_brand_send_hooks

        install_brand_send_hooks()
        await bot.db.connect()
        await bot.db.initialize()
        for extension in COGS:
            await bot.load_extension(extension)

    @bot.event
    async def on_ready() -> None:
        ready.set()

    bot.setup_hook = patched_setup_hook  # type: ignore[method-assign]

    connect_task = asyncio.create_task(bot.start(Config.DISCORD_TOKEN))
    try:
        await asyncio.wait_for(ready.wait(), timeout=45.0)
        assert bot.user is not None
        print(f"Bot online: {bot.user} (ID {bot.user.id})")
        print(f"Guilds: {len(bot.guilds)}")

        names = _flatten_commands(bot.tree)
        missing = COMMANDS_ADDED_SINCE_1_4 - names
        removed_still = COMMANDS_REMOVED_SINCE_1_4 & names
        lootbox_missing = LOOTBOX_COMMANDS_KEPT - names

        if missing:
            print(f"FAIL: fehlende Befehle: {sorted(missing)}")
            return 1
        if removed_still:
            print(f"FAIL: entfernte Befehle noch da: {sorted(removed_still)}")
            return 1
        if lootbox_missing:
            print(f"FAIL: Lootbox-Befehle fehlen: {sorted(lootbox_missing)}")
            return 1

        print("OK: Alle Befehle seit Changelog 1.4 korrekt registriert.")
        print(f"  Neu: {', '.join(sorted(COMMANDS_ADDED_SINCE_1_4))}")
        print(f"  Entfernt: {', '.join(sorted(COMMANDS_REMOVED_SINCE_1_4))}")
        return 0
    except asyncio.TimeoutError:
        print("FAIL: Bot nicht innerhalb von 45s bereit.")
        return 1
    finally:
        if not bot.is_closed():
            await bot.close()
        await connect_task


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
