"""
Zombie Survival: GIF-Auswahl und Embed-Bilder.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import TYPE_CHECKING

import discord

from config import Config
from utils.zombie_content import ZOMBIE_TYPE_BOSS, ZOMBIE_TYPE_RASENDER, ZOMBIE_TYPE_STREUNER

if TYPE_CHECKING:
    from database.models import ZombieRunRecord

logger = logging.getLogger(__name__)

MAX_GIF_BYTES = 8 * 1024 * 1024

# Freie Fallback-GIFs (Giphy-CDN — Tenor-Links waren 404)
FALLBACK_GIFS: dict[str, list[str]] = {
    "common": [
        "https://media.giphy.com/media/3o7btPCcdNniyf0ArS/giphy.gif",
        "https://media.giphy.com/media/l0MYt5jPR6QX5pnqM/giphy.gif",
    ],
    "fast": [
        "https://media.giphy.com/media/xT9IgG50Fb7Mi0prBC/giphy.gif",
        "https://media.giphy.com/media/3o7aD2saalBwwftBIY/giphy.gif",
    ],
    "boss": [
        "https://media.giphy.com/media/3o7btPCcdNniyf0ArS/giphy.gif",
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


def pick_zombie_visual_url(zombie_type: str, *, is_boss: bool = False) -> str:
    """Wählt eine HTTP-Bild-URL für Embed-Updates ohne Datei-Anhang."""
    source = boss_zombie_gif() if is_boss else random_zombie_gif(zombie_type)
    if isinstance(source, Path):
        folder = "boss" if is_boss else ZOMBIE_ASSET_MAP.get(zombie_type, "common")
        urls = FALLBACK_GIFS.get(folder, FALLBACK_GIFS["common"])
        return random.choice(urls)
    return str(source)


def ensure_run_combat_image(
    run: ZombieRunRecord,
    zombie_type: str,
    *,
    is_boss: bool = False,
    refresh: bool = False,
) -> str:
    """Liefert die stabile Kampf-GIF-URL für diesen Zombie (pro Spawn)."""
    if refresh:
        run.current_zombie_image_url = ""
    if run.current_zombie_image_url:
        return run.current_zombie_image_url
    url = pick_zombie_visual_url(zombie_type, is_boss=is_boss)
    run.current_zombie_image_url = url
    return url


def apply_zombie_visual(
    embed: discord.Embed,
    run: ZombieRunRecord,
    zombie_type: str,
    *,
    is_boss: bool = False,
    use_attachment: bool = False,
    refresh_visual: bool = False,
) -> discord.File | None:
    """
    Setzt das Zombie-Bild im Embed.

    Hält die Bild-URL pro Zombie stabil über Nachrichten-Edits hinweg.
    """
    if refresh_visual:
        run.current_zombie_image_url = ""

    url = ensure_run_combat_image(run, zombie_type, is_boss=is_boss)
    embed.set_image(url=url)

    if use_attachment:
        file = attach_zombie_visual(embed, zombie_type, is_boss=is_boss)
        image = embed.image
        if image and image.url and not image.url.startswith("attachment://"):
            run.current_zombie_image_url = image.url
        return file

    return None


def set_zombie_visual_url(
    embed: discord.Embed,
    zombie_type: str,
    *,
    is_boss: bool = False,
) -> None:
    """Setzt Zombie-GIF per URL (für Embed-Updates ohne Datei-Anhang)."""
    folder = "boss" if is_boss else ZOMBIE_ASSET_MAP.get(zombie_type, "common")
    urls = FALLBACK_GIFS.get(folder, FALLBACK_GIFS["common"])
    embed.set_image(url=random.choice(urls))


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
