"""
Hilfsfunktionen zum Hinzufügen von Server-Emojis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import aiohttp
import discord

from utils.reactions import parse_emoji_input

EMOJI_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]{2,32}$")
MAX_EMOJI_BYTES = 256 * 1024
ALLOWED_IMAGE_TYPES = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/gif",
        "image/webp",
    }
)


@dataclass(frozen=True)
class ParsedCustomEmoji:
    """Geparstes Custom-Emoji aus Slash-Command-Eingabe."""

    name: str
    emoji_id: int
    animated: bool


def validate_emoji_name(name: str) -> str | None:
    """
    Prüft den Emoji-Namen für Discord.

    Returns:
        Fehlermeldung oder None wenn gültig.
    """
    cleaned = name.strip()
    if not EMOJI_NAME_PATTERN.match(cleaned):
        return (
            "Der Name muss **2–32 Zeichen** lang sein und darf nur "
            "**Buchstaben, Zahlen und Unterstriche** enthalten."
        )
    return None


def parse_custom_emoji(value: str) -> ParsedCustomEmoji | None:
    """Extrahiert Custom-Emoji-Daten aus Mention oder ``name:id``."""
    raw = value.strip()
    mention = re.match(r"^<(a?):([\w]+):(\d+)>$", raw)
    if mention:
        return ParsedCustomEmoji(
            name=mention.group(2),
            emoji_id=int(mention.group(3)),
            animated=mention.group(1) == "a",
        )

    key = parse_emoji_input(raw)
    if ":" in key and key.split(":")[-1].isdigit():
        source_name, emoji_id_str = key.rsplit(":", 1)
        return ParsedCustomEmoji(
            name=source_name,
            emoji_id=int(emoji_id_str),
            animated=False,
        )
    return None


def emoji_cdn_url(emoji_id: int, *, animated: bool) -> str:
    """CDN-URL für ein Custom-Emoji."""
    extension = "gif" if animated else "png"
    return f"https://cdn.discordapp.com/emojis/{emoji_id}.{extension}"


async def fetch_emoji_bytes(emoji: ParsedCustomEmoji) -> bytes:
    """Lädt Emoji-Bilddaten von Discords CDN."""
    candidates = [emoji_cdn_url(emoji.emoji_id, animated=emoji.animated)]
    if not emoji.animated:
        candidates.append(emoji_cdn_url(emoji.emoji_id, animated=True))

    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for url in candidates:
            try:
                async with session.get(url) as response:
                    if response.status != 200:
                        continue
                    data = await response.read()
                    if len(data) > MAX_EMOJI_BYTES:
                        raise ValueError("Das Emoji-Bild ist größer als **256 KB**.")
                    return data
            except aiohttp.ClientError:
                continue

    raise ValueError("Das Emoji konnte nicht von Discord geladen werden.")


def validate_attachment(attachment: discord.Attachment) -> str | None:
    """Prüft ein hochgeladenes Bild für Server-Emojis."""
    if attachment.content_type not in ALLOWED_IMAGE_TYPES:
        return "Erlaubt sind **PNG, JPG, GIF und WebP**."
    if attachment.size > MAX_EMOJI_BYTES:
        return "Die Datei darf maximal **256 KB** groß sein."
    return None


async def read_attachment_bytes(attachment: discord.Attachment) -> bytes:
    """Liest und validiert Emoji-Bild aus einem Anhang."""
    error = validate_attachment(attachment)
    if error:
        raise ValueError(error)
    data = await attachment.read()
    if len(data) > MAX_EMOJI_BYTES:
        raise ValueError("Die Datei darf maximal **256 KB** groß sein.")
    return data


def emoji_slot_error(guild: discord.Guild, *, animated: bool) -> str | None:
    """Prüft, ob noch Emoji-Slots frei sind."""
    if animated:
        animated_count = sum(1 for item in guild.emojis if item.animated)
        if animated_count >= guild.emoji_limit:
            return "Das Limit für **animierte Emojis** auf diesem Server ist erreicht."
        return None

    static_count = sum(1 for item in guild.emojis if not item.animated)
    if static_count >= guild.emoji_limit:
        return "Das Limit für **statische Emojis** auf diesem Server ist erreicht."
    return None


def is_animated_image(data: bytes) -> bool:
    """Erkennt GIF anhand des Headers (für Uploads)."""
    return data.startswith((b"GIF87a", b"GIF89a"))
