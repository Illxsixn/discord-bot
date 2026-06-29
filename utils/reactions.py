"""
Hilfsfunktionen für Reaktionsrollen, Umfragen und Gewinnspiele.
"""

from __future__ import annotations

import logging
import re

import discord

from database.models import PollRecord, PollType

logger = logging.getLogger(__name__)

POLL_YES_NO_EMOJIS = ("✅", "❌")
POLL_NUMBER_EMOJIS = ("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟")
DEFAULT_GIVEAWAY_EMOJI = "🎉"
EMOJI_MENTION_PATTERN = re.compile(r"^<(?:a)?:([\w]+):(\d+)>$")


def emoji_key(emoji: discord.PartialEmoji | str) -> str:
    """
    Normalisiert ein Emoji für die Datenbank.

    Args:
        emoji: Discord-Emoji oder Unicode-String.

    Returns:
        Gespeicherter Emoji-Schlüssel.
    """
    if isinstance(emoji, str):
        return emoji
    if emoji.id:
        return f"{emoji.name}:{emoji.id}"
    return str(emoji)


def parse_emoji_input(value: str) -> str:
    """
    Parst Emoji-Eingabe aus Slash Commands.

    Args:
        value: Unicode, ``name:id`` oder ``<:name:id>`` für Custom-Emojis.

    Returns:
        Normalisierter Emoji-Schlüssel.
    """
    value = value.strip()
    match = EMOJI_MENTION_PATTERN.match(value)
    if match:
        return f"{match.group(1)}:{match.group(2)}"
    if ":" in value and value.split(":")[-1].isdigit():
        parts = value.split(":")
        if len(parts) >= 2:
            return f"{parts[-2]}:{parts[-1]}"
    return value


def emoji_display(key: str) -> str:
    """Formatiert gespeicherten Emoji-Schlüssel für Discord."""
    if ":" in key and key.split(":")[-1].isdigit():
        name, emoji_id = key.rsplit(":", 1)
        return f"<:{name}:{emoji_id}>"
    return key


async def emoji_to_partial(bot: discord.Client, guild: discord.Guild, key: str) -> str | discord.PartialEmoji:
    """Wandelt Emoji-Schlüssel in Discord-kompatibles Emoji um."""
    if ":" in key and key.split(":")[-1].isdigit():
        name, emoji_id = key.rsplit(":", 1)
        custom = discord.utils.get(guild.emojis, id=int(emoji_id))
        if custom:
            return custom
        return discord.PartialEmoji(name=name, id=int(emoji_id))
    return key


def bot_can_manage_role(guild: discord.Guild, role: discord.Role) -> tuple[bool, str | None]:
    """
    Prüft, ob der Bot eine Rolle vergeben/entfernen darf.

    Args:
        guild: Discord-Server.
        role: Zielrolle.

    Returns:
        Tuple (erlaubt, fehlermeldung).
    """
    if guild.me is None:
        return False, "Bot-Mitgliedsdaten nicht verfügbar."
    if not guild.me.guild_permissions.manage_roles:
        return False, "Mir fehlt die Berechtigung **Rollen verwalten**."
    if role.is_default():
        return False, "Die @everyone-Rolle kann nicht als Reaktionsrolle genutzt werden."
    if role.managed:
        return False, "Integrationen-/Bot-Rollen können nicht vergeben werden."
    if role >= guild.me.top_role:
        return False, "Diese Rolle liegt über meiner höchsten Rolle."
    return True, None


async def toggle_member_role(
    member: discord.Member,
    role: discord.Role,
    *,
    add: bool,
) -> tuple[bool, str | None]:
    """
    Vergibt oder entfernt eine Rolle bei einem Mitglied.

    Args:
        member: Zielmitglied.
        role: Rolle.
        add: True = hinzufügen, False = entfernen.

    Returns:
        Tuple (erfolg, fehlermeldung).
    """
    allowed, msg = bot_can_manage_role(member.guild, role)
    if not allowed:
        return False, msg

    try:
        if add:
            if role in member.roles:
                return True, None
            await member.add_roles(role, reason="Reaktionsrolle")
        else:
            if role not in member.roles:
                return True, None
            await member.remove_roles(role, reason="Reaktionsrolle entfernt")
        return True, None
    except discord.Forbidden:
        return False, "Keine Berechtigung, diese Rolle zu ändern."
    except discord.HTTPException as exc:
        logger.warning("Rollen-Toggle fehlgeschlagen: %s", exc)
        return False, "Rollenänderung fehlgeschlagen."


async def count_reaction_votes(
    message: discord.Message,
    emojis: list[str],
) -> dict[str, int]:
    """
    Zählt Stimmen anhand von Reaktionen.

    Args:
        message: Umfrage-Nachricht.
        emojis: Liste der gültigen Emoji-Schlüssel.

    Returns:
        Mapping emoji -> Stimmen (ohne Bot-Reaktionen).
    """
    counts: dict[str, int] = {key: 0 for key in emojis}
    for reaction in message.reactions:
        key = emoji_key(reaction.emoji)
        if key not in counts:
            continue
        users = [user async for user in reaction.users() if not user.bot]
        counts[key] = len(users)
    return counts


def poll_emojis_for_record(poll: PollRecord) -> list[str]:
    """Gibt gültige Umfrage-Emojis zurück."""
    if poll.poll_type == PollType.YES_NO:
        return list(POLL_YES_NO_EMOJIS)
    return list(POLL_NUMBER_EMOJIS[: len(poll.options)])


async def collect_giveaway_entrants(
    message: discord.Message,
    emoji_key_value: str,
) -> list[discord.Member]:
    """
    Sammelt gültige Gewinnspiel-Teilnehmer.

    Args:
        message: Gewinnspiel-Nachricht.
        emoji_key_value: Gespeicherter Emoji-Schlüssel.

    Returns:
        Liste aktiver Servermitglieder (ohne Bots).
    """
    if message.guild is None:
        return []

    entrants: list[discord.Member] = []
    for reaction in message.reactions:
        if emoji_key(reaction.emoji) != emoji_key_value:
            continue
        async for user in reaction.users():
            if user.bot:
                continue
            member = message.guild.get_member(user.id)
            if member is None:
                try:
                    member = await message.guild.fetch_member(user.id)
                except discord.NotFound:
                    continue
            entrants.append(member)
        break
    return entrants
