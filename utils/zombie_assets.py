"""
Zombie Survival: GIF-Auswahl und Embed-Bilder.

Priorität: Agnes-generierte lokale GIFs → Giphy-Fallback nur ohne lokale Dateien.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import TYPE_CHECKING

import discord

from config import Config
from utils.agnes_images import agnes_configured
from utils.zombie_content import ZOMBIE_TYPE_BOSS, ZOMBIE_TYPE_RASENDER, ZOMBIE_TYPE_STREUNER

if TYPE_CHECKING:
    from database.models import ZombieRunRecord

logger = logging.getLogger(__name__)

MAX_GIF_BYTES = 8 * 1024 * 1024

# Nur wenn keine lokalen Agnes-GIFs in assets/zombies/ liegen
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


def _asset_folder(zombie_type: str, *, is_boss: bool = False) -> str:
    if is_boss:
        return "boss"
    return ZOMBIE_ASSET_MAP.get(zombie_type, "common")


def _pick_local_gif(folder: str) -> Path | None:
    """Wählt zufällige lokale GIF-Datei (Agnes-Cache)."""
    directory = _asset_dir(folder)
    if not directory.is_dir():
        return None
    files = [p for p in directory.glob("*.gif") if p.is_file() and p.stat().st_size <= MAX_GIF_BYTES]
    if not files:
        files = [p for p in directory.glob("*.png") if p.is_file()]
    return random.choice(files) if files else None


def is_agnes_zombie_asset_configured() -> bool:
    """True wenn Agnes für die Zombie-GIF-Bibliothek konfiguriert ist."""
    return agnes_configured()


def has_local_zombie_gif(zombie_type: str, *, is_boss: bool = False) -> bool:
    """True wenn ein Agnes-GIF für diesen Typ im Asset-Ordner liegt."""
    return _pick_local_gif(_asset_folder(zombie_type, is_boss=is_boss)) is not None


def _fallback_gif_url(zombie_type: str, *, is_boss: bool = False) -> str:
    folder = _asset_folder(zombie_type, is_boss=is_boss)
    urls = FALLBACK_GIFS.get(folder, FALLBACK_GIFS["common"])
    return random.choice(urls)


def random_zombie_gif(zombie_type: str) -> str | Path | None:
    """Lokales Agnes-GIF oder Giphy-Fallback-URL."""
    local = _pick_local_gif(_asset_folder(zombie_type))
    if local:
        return local
    return random.choice(FALLBACK_GIFS.get(_asset_folder(zombie_type), FALLBACK_GIFS["common"]))


def boss_zombie_gif() -> str | Path | None:
    """Boss-GIF — lokal oder Fallback."""
    local = _pick_local_gif("boss")
    if local:
        return local
    return random.choice(FALLBACK_GIFS["boss"])


def pick_zombie_visual_url(zombie_type: str, *, is_boss: bool = False) -> str:
    """HTTP-URL nur für Fallback (keine lokale Datei)."""
    if has_local_zombie_gif(zombie_type, is_boss=is_boss):
        return ""
    return _fallback_gif_url(zombie_type, is_boss=is_boss)


def ensure_run_combat_image(
    run: ZombieRunRecord,
    zombie_type: str,
    *,
    is_boss: bool = False,
    refresh: bool = False,
) -> str:
    """Liefert die stabile Kampf-GIF-URL (nur bei Giphy-Fallback)."""
    if refresh:
        run.current_zombie_image_url = ""
    if run.current_zombie_image_url:
        return run.current_zombie_image_url
    if has_local_zombie_gif(zombie_type, is_boss=is_boss):
        return ""
    url = _fallback_gif_url(zombie_type, is_boss=is_boss)
    run.current_zombie_image_url = url
    return url


def apply_zombie_visual(
    embed: discord.Embed,
    run: ZombieRunRecord,
    zombie_type: str,
    *,
    is_boss: bool = False,
    use_attachment: bool = True,
    refresh_visual: bool = False,
) -> discord.File | None:
    """
    Setzt das Zombie-Bild im Embed.

    Lokale Agnes-GIFs werden als Attachment gesetzt; CDN-URL wird nach dem Senden gespeichert.
    """
    if refresh_visual:
        run.current_zombie_image_url = ""

    if run.current_zombie_image_url:
        embed.set_image(url=run.current_zombie_image_url)
        return None

    if use_attachment:
        file = attach_zombie_visual(embed, zombie_type, is_boss=is_boss)
        if file is not None:
            return file

    source = boss_zombie_gif() if is_boss else random_zombie_gif(zombie_type)
    if isinstance(source, Path):
        return None

    url = str(source) if source else _fallback_gif_url(zombie_type, is_boss=is_boss)
    run.current_zombie_image_url = url
    embed.set_image(url=url)
    return None


def attach_zombie_visual(
    embed: discord.Embed,
    zombie_type: str,
    *,
    is_boss: bool = False,
) -> discord.File | None:
    """
    Hängt ein lokales Agnes-Zombie-GIF an.

    Returns:
        discord.File wenn Attachment nötig, sonst None (URL-Fallback bereits gesetzt).
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
