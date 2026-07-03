#!/usr/bin/env python3
"""
Einmaliges Generieren der Zombie-GIFs über die Agnes-API.

Usage:
    python scripts/generate_zombie_assets.py
    python scripts/generate_zombie_assets.py --force
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.agnes_images import AgnesImageError, agnes_configured
from utils.zombie_ai_images import ensure_zombie_asset_library, list_cached_zombie_gifs

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("generate_zombie_assets")


async def main(force: bool) -> int:
    if not agnes_configured():
        logger.error("AGNES_API_KEY fehlt in .env")
        return 1

    logger.info("Starte Zombie-GIF-Generierung (force=%s) …", force)
    try:
        paths = await ensure_zombie_asset_library(force=force)
    except AgnesImageError as exc:
        logger.error("%s", exc)
        return 1

    logger.info("Fertig — %d GIF(s):", len(paths))
    for path in paths:
        size_kb = path.stat().st_size / 1024
        logger.info("  %s (%.1f KB)", path.relative_to(ROOT), size_kb)

    cached = list_cached_zombie_gifs()
    logger.info("Gesamt im Cache: %d GIF(s)", len(cached))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Zombie-GIFs via Agnes-API generieren")
    parser.add_argument("--force", action="store_true", help="Bestehende GIFs überschreiben")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.force)))
