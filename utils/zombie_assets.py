"""
Zombie Survival: GIF-Auswahl und Embed-Bilder.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path

import discord

from config import Config
from utils.zombie_content import ZOMBIE_TYPE_BOSS, ZOMBIE_TYPE_RASENDER, ZOMBIE_TYPE_STREUNER

logger = logging.getLogger(__name__)

MAX_GIF_BYTES = 8 * 1024 * 1024

# Freie Fallback-GIFs (kein CoD, generische Zombie-Optik)
FALLBACK_GIFS: dict[str, list[str]] = {
    "common": [
        "https://media.tenor.com/m/5h0XqJqJqJAAAAAd/zombie-walk.gif",
        "https://media.tenor.com/m/8tIUv8X9x0AAAAAd/zombie.gif",
    ],
    "fast": [
        "https://media.tenor.com/m/2Rk8X9X9x0AAAAAd/running-zombie.gif",
        "https://media.tenor.com/m/9X9X9X9X9XAAAAAd/zombie-run.gif",
    ],
    "boss": [
        "https://media.tenor.com/m/3ov6Q2xXyQAAAAAd/monster.gif",
    ],
}

ZOMBIE_ASSET_MAP: dict[str, str] = {
    ZOMBIE_TYPE_STREUNER: "common",
    ZOMBIE_TYPE_RASENDER: "fast",
    ZOMBIE_TYPE_BOSS: "boss",
}


def _asset_dir(folder: str) -> Path:
    return Config.ZOMBIE_ASSETS_DIR / folder


def _pick_local_gif(folder: str) -> Path | None:
    """Wählt zufällige lokale GIF-Datei."""
    directory = _asset_dir(folder)
    if not directory.is_dir():
        return None
    files = [p for p in directory.glob("*.gif") if p.is_file() and p.stat().st_size <= MAX_GIF_BYTES]
    if not files:
        files = [p for p in directory.glob("*.png") if p.is_file()]
    return random.choice(files) if files else None


def random_zombie_gif(zombie_type: str) -> str | Path | None:
    """Zufälliges GIF für normalen Zombie."""
    folder = ZOMBIE_ASSET_MAP.get(zombie_type, "common")
    local = _pick_local_gif(folder)
    if local:
        return local
    urls = FALLBACK_GIFS.get(folder, FALLBACK_GIFS["common"])
    return random.choice(urls)


def boss_zombie_gif() -> str | Path | None:
    """Boss-GIF."""
    local = _pick_local_gif("boss")
    if local:
        return local
    return random.choice(FALLBACK_GIFS["boss"])


def attach_zombie_visual(
    embed: discord.Embed,
    zombie_type: str,
    *,
    is_boss: bool = False,
) -> discord.File | None:
    """
    Hängt Zombie-Bild an Embed an.

    Returns:
        discord.File wenn Attachment nötig, sonst None (URL bereits gesetzt).
    """
    try:
        source = boss_zombie_gif() if is_boss else random_zombie_gif(zombie_type)
        if source is None:
            return None
        if isinstance(source, Path):
            if not source.exists():
                return None
            if source.suffix.lower() == ".gif" and source.stat().st_size > MAX_GIF_BYTES:
                logger.warning("Zombie-GIF zu groß: %s", source)
                return None
            filename = source.name
            embed.set_image(url=f"attachment://{filename}")
            return discord.File(str(source), filename=filename)
        embed.set_image(url=str(source))
        return None
    except OSError as exc:
        logger.warning("Zombie-Asset Fehler: %s", exc)
        return None
