"""
Allgemeine Hilfsfunktionen für Nachrichten, Platzhalter und Bilder.

Enthält Utilities für Welcome/Leave-Nachrichten, Cooldown-Tracking
und optionale Welcome-Bilder mit Pillow.
"""

from __future__ import annotations

import io
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord
from PIL import Image, ImageDraw

from config import Config
from utils.embeds import spaced_lines

if TYPE_CHECKING:
    from database.models import GuildSettings

logger = logging.getLogger(__name__)

# Regex für Discord-Einladungen und allgemeine URLs
DISCORD_INVITE_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?"
    r"(?:discord\.(?:gg|io|me|li)|discordapp\.com/invite|discord\.com/invite)/[a-zA-Z0-9-]+",
    re.IGNORECASE,
)

URL_PATTERN = re.compile(
    r"https?://[^\s<>\"']+|www\.[^\s<>\"']+",
    re.IGNORECASE,
)

# Einfacher Spam-Tracker: user_id -> Liste der letzten Nachrichten-Zeitstempel
_spam_tracker: dict[int, list[float]] = defaultdict(list)
SPAM_MESSAGE_LIMIT = 5
SPAM_TIME_WINDOW = 5.0  # Sekunden


def format_placeholders(
    template: str,
    member: discord.Member,
    guild: discord.Guild,
) -> str:
    """
    Ersetzt Platzhalter in Welcome-/Leave-Nachrichten.

    Unterstützte Platzhalter:
        {user}, {username}, {userid}, {server}, {membercount}

    Args:
        template: Nachrichtenvorlage mit Platzhaltern.
        member: Discord-Mitglied.
        guild: Discord-Server.

    Returns:
        Formatierter Text.
    """
    replacements = {
        "{user}": member.mention,
        "{username}": member.display_name,
        "{userid}": str(member.id),
        "{server}": guild.name,
        "{membercount}": str(guild.member_count or len(guild.members)),
    }
    result = template
    for key, value in replacements.items():
        result = result.replace(key, value)
    return result


def truncate_text(text: str, max_length: int = 1024) -> str:
    """
    Kürzt Text auf eine maximale Länge (Discord-Embed-Limit).

    Args:
        text: Eingabetext.
        max_length: Maximale Zeichenanzahl.

    Returns:
        Gekürzter Text mit Ellipsis falls nötig.
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def parse_duration_minutes(minutes: int) -> datetime.timedelta:
    """
    Wandelt Minuten in ein timedelta-Objekt um.

    Args:
        minutes: Anzahl Minuten.

    Returns:
        timedelta-Objekt.
    """
    import datetime as dt

    return dt.timedelta(minutes=max(1, min(minutes, 40320)))


def contains_discord_invite(content: str) -> bool:
    """Prüft, ob der Text eine Discord-Einladung enthält."""
    return DISCORD_INVITE_PATTERN.search(content) is not None


def contains_link(content: str) -> bool:
    """Prüft, ob der Text eine URL enthält."""
    return URL_PATTERN.search(content) is not None


def contains_bad_word(content: str, bad_words: list[str]) -> str | None:
    """
    Prüft auf verbotene Wörter (case-insensitive).

    Args:
        content: Nachrichtentext.
        bad_words: Liste verbotener Wörter.

    Returns:
        Gefundenes Wort oder None.
    """
    lowered = content.lower()
    for word in bad_words:
        if word.strip() and word.lower() in lowered:
            return word
    return None


def is_spam(user_id: int) -> bool:
    """
    Einfacher Spam-Schutz: zu viele Nachrichten in kurzer Zeit.

    Args:
        user_id: Discord-User-ID.

    Returns:
        True wenn Spam erkannt wurde.
    """
    import time

    now = time.monotonic()
    timestamps = _spam_tracker[user_id]
    # Alte Einträge entfernen
    timestamps[:] = [t for t in timestamps if now - t <= SPAM_TIME_WINDOW]
    timestamps.append(now)
    return len(timestamps) > SPAM_MESSAGE_LIMIT


def clear_spam_tracker(user_id: int) -> None:
    """Setzt den Spam-Tracker für einen User zurück."""
    _spam_tracker.pop(user_id, None)


async def generate_welcome_image(member: discord.Member) -> discord.File | None:
    """
    Erstellt ein optionales Welcome-Bild mit Pillow.

    Args:
        member: Neues Servermitglied.

    Returns:
        discord.File mit PNG oder None bei Fehler.
    """
    try:
        width, height = 800, 300
        image = Image.new("RGB", (width, height), color=(32, 34, 37))
        draw = ImageDraw.Draw(image)

        # Einfache Willkommens-Grafik
        draw.rectangle([(0, 0), (width, 80)], fill=(88, 101, 242))
        draw.text((30, 25), "Willkommen!", fill=(255, 255, 255))

        # Avatar laden (falls möglich)
        avatar_bytes = await member.display_avatar.read()
        avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
        avatar = avatar.resize((120, 120))
        image.paste(avatar, (30, 100), avatar)

        username = truncate_text(member.display_name, 40)
        draw.text((170, 120), username, fill=(255, 255, 255))
        draw.text((170, 160), f"Mitglied #{member.guild.member_count}", fill=(185, 187, 190))

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        return discord.File(buffer, filename="welcome.png")
    except Exception as exc:
        logger.exception("Welcome-Bild konnte nicht erstellt werden: %s", exc)
        return None


def guild_settings_to_fields(settings: "GuildSettings") -> list[tuple[str, str, bool]]:
    """
    Wandelt GuildSettings in Embed-Felder für /settings view um.

    Args:
        settings: Server-Einstellungen.

    Returns:
        Liste von (name, value, inline) Tupeln.
    """
    def ch(channel_id: int | None) -> str:
        return f"<#{channel_id}>" if channel_id else "— Nicht gesetzt"

    def onoff(enabled: bool) -> str:
        return "✅ Aktiv" if enabled else "❌ Inaktiv"

    return [
        (
            "👋 Welcome & Leave",
            spaced_lines(
                f"**Welcome:** {onoff(settings.welcome_enabled)}",
                f"**Welcome-Kanal:** {ch(settings.welcome_channel_id)}",
                f"**Leave:** {onoff(settings.leave_enabled)}",
                f"**Leave-Kanal:** {ch(settings.leave_channel_id)}",
            ),
            False,
        ),
        (
            "📋 Logs",
            spaced_lines(
                f"**Logs:** {onoff(settings.logs_enabled)}",
                f"**Log-Kanal:** {ch(settings.logs_channel_id)}",
            ),
            False,
        ),
        (
            "🤖 AutoMod",
            spaced_lines(
                f"**AutoMod:** {onoff(settings.automod_enabled)}",
                f"**Spam-Schutz:** {'✅' if settings.spam_protection else '❌'}",
                f"**Invite-Blocker:** {'✅' if settings.invite_blocker else '❌'}",
                f"**Link-Blocker:** {'✅' if settings.link_blocker else '❌'}",
                f"**Bad-Word-Filter:** {'✅' if settings.bad_word_filter else '❌'}",
                f"**Strafe:** {settings.automod_punishment.value.title()}",
                f"**Mute-Rolle:** {f'<@&{settings.mute_role_id}>' if settings.mute_role_id else '— Nicht gesetzt'}",
            ),
            False,
        ),
        (
            "📈 Level-System",
            spaced_lines(
                f"**Level-System:** {onoff(settings.levels_enabled)}",
                f"**XP pro Nachricht:** {Config.XP_PER_MESSAGE}",
                (
                    f"**Level-Up Kanal:** <#{settings.levels_announce_channel_id}>"
                    if settings.levels_announce_channel_id
                    else "**Level-Up Kanal:** Nachrichtenkanal"
                ),
            ),
            False,
        ),
    ]


def format_join_date(member: discord.Member) -> str:
    """Formatiert das Beitrittsdatum eines Mitglieds."""
    joined = member.joined_at or datetime.now(timezone.utc)
    return discord.utils.format_dt(joined, style="F")
