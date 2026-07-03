"""
Professionelles Embed-System für den Discord-Bot.

Stellt einheitliche Erfolgs-, Fehler-, Warn- und Info-Embeds bereit,
sodass alle Cogs konsistente Nachrichten anzeigen.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import discord

from config import Config

BRAND_ICON_ATTACHMENT = "anarchy_icon.png"
ARTWORK_THUMBNAIL = f"attachment://{BRAND_ICON_ATTACHMENT}"
DISCORD_FIELD_VALUE_LIMIT = 1024


def spaced_lines(*parts: str) -> str:
    """Verbindet Textblöcke mit Leerzeile dazwischen."""
    cleaned = [part.strip() for part in parts if part and part.strip()]
    return "\n\n".join(cleaned)


def spaced_list(items: list[str]) -> str:
    """Formatiert eine Liste mit Leerzeilen zwischen Einträgen."""
    return spaced_lines(*items)


def split_embed_fields(
    name: str,
    entries: list[str],
    *,
    inline: bool = False,
    joiner: str = "\n\n",
    max_length: int = DISCORD_FIELD_VALUE_LIMIT,
) -> list[tuple[str, str, bool]]:
    """
    Teilt lange Eintragslisten in mehrere Embed-Felder (Discord-Limit).

    Args:
        name: Feldname (bei Fortsetzung mit „(2)“ usw.).
        entries: Einzelne Einträge.
        inline: Ob Felder inline sind.
        joiner: Trenner zwischen Einträgen im selben Feld.
        max_length: Maximale Zeichen pro Feldwert.

    Returns:
        Liste von (name, value, inline) Tupeln.
    """
    if not entries:
        return [(name, "—", inline)]

    fields: list[tuple[str, str, bool]] = []
    chunk: list[str] = []
    chunk_len = 0
    part = 1

    for raw in entries:
        entry = raw.strip()
        if not entry:
            continue
        extra = len(entry) + (len(joiner) if chunk else 0)
        if chunk and chunk_len + extra > max_length:
            label = name if part == 1 else f"{name} ({part})"
            fields.append((label, joiner.join(chunk), inline))
            chunk = [entry]
            chunk_len = len(entry)
            part += 1
        else:
            chunk.append(entry)
            chunk_len = chunk_len + extra if chunk else len(entry)

    if chunk:
        label = name if part == 1 and not fields else (name if not fields else f"{name} ({part})")
        fields.append((label, joiner.join(chunk), inline))

    return fields


def brand_name() -> str:
    """Anzeigename für Embed-Signaturen."""
    return Config.BOT_BRAND_NAME


def brand_icon_file() -> discord.File | None:
    """Liefert das Marken-Icon als Anhang, falls vorhanden."""
    path = Config.BOT_BRAND_ICON_PATH
    if not path.is_file():
        return None
    return discord.File(path, filename=BRAND_ICON_ATTACHMENT)


def _footer(*, prefix: str | None = None) -> str:
    """Standard-Footer mit Markenname und Zeitstempel."""
    now = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    if prefix:
        return f"{prefix} • {Config.BOT_BRAND_NAME} • {now}"
    return f"{Config.BOT_BRAND_NAME} • {now}"


def apply_brand_footer(embed: discord.Embed, *, prefix: str | None = None) -> discord.Embed:
    """Setzt einheitliche Footer-Signatur inkl. Marken-Icon."""
    text = _footer(prefix=prefix)
    if brand_icon_file() is not None:
        embed.set_footer(text=text, icon_url=f"attachment://{BRAND_ICON_ATTACHMENT}")
    else:
        embed.set_footer(text=text)
    return embed


def _collect_embeds(kwargs: dict[str, Any]) -> list[discord.Embed]:
    """Sammelt alle Embeds aus send/edit-Kwargs."""
    embeds: list[discord.Embed] = []
    embed = kwargs.get("embed")
    if isinstance(embed, discord.Embed):
        embeds.append(embed)
    extra = kwargs.get("embeds")
    if extra:
        embeds.extend(item for item in extra if isinstance(item, discord.Embed))
    return embeds


def inject_brand_into_send_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Fügt Marken-Icon als Anhang hinzu, wenn Embeds gesendet werden."""
    embeds = _collect_embeds(kwargs)
    if not embeds:
        return kwargs

    # Discord erlaubt nicht gleichzeitig file= und files=
    single_file = kwargs.pop("file", None)
    if single_file is not None:
        files = list(kwargs.get("files") or [])
        files.append(single_file)
        kwargs["files"] = files

    icon = brand_icon_file()
    if icon is None:
        return kwargs

    files = list(kwargs.get("files") or [])
    if any(getattr(file, "filename", None) == BRAND_ICON_ATTACHMENT for file in files):
        return kwargs

    files.append(icon)
    kwargs["files"] = files

    for embed in embeds:
        footer = embed.footer
        if footer.icon_url:
            continue
        if not footer.text:
            apply_brand_footer(embed)
        elif Config.BOT_BRAND_NAME not in footer.text:
            apply_brand_footer(embed, prefix=footer.text)
        else:
            embed.set_footer(
                text=footer.text,
                icon_url=f"attachment://{BRAND_ICON_ATTACHMENT}",
            )

    return kwargs


def inject_brand_into_edit_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Embed-Footer beim Bearbeiten — ohne files= (Message.edit nutzt attachments=)."""
    embeds = _collect_embeds(kwargs)
    if not embeds:
        return kwargs

    icon = brand_icon_file()
    if icon is None:
        return kwargs

    for embed in embeds:
        footer = embed.footer
        if footer.icon_url:
            continue
        if not footer.text:
            apply_brand_footer(embed)
        elif Config.BOT_BRAND_NAME not in footer.text:
            apply_brand_footer(embed, prefix=footer.text)
        else:
            embed.set_footer(
                text=footer.text,
                icon_url=f"attachment://{BRAND_ICON_ATTACHMENT}",
            )

    # Anhang bleibt von der ursprünglichen send()-Nachricht erhalten.
    kwargs.pop("files", None)
    kwargs.pop("file", None)
    return kwargs


def install_brand_send_hooks() -> None:
    """Hängt das Marken-Icon an alle Embed-Nachrichten (send/edit)."""
    import discord.abc
    import discord.interactions
    import discord.webhook.async_ as webhook_async

    def _wrap_send(method: Any) -> Any:
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            kwargs = inject_brand_into_send_kwargs(kwargs)
            return await method(self, *args, **kwargs)

        return wrapper

    def _wrap_edit(method: Any) -> Any:
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            kwargs = inject_brand_into_edit_kwargs(kwargs)
            return await method(self, *args, **kwargs)

        return wrapper

    discord.abc.Messageable.send = _wrap_send(discord.abc.Messageable.send)
    discord.interactions.InteractionResponse.send_message = _wrap_send(
        discord.interactions.InteractionResponse.send_message
    )
    webhook_async.Webhook.send = _wrap_send(webhook_async.Webhook.send)
    discord.Message.edit = _wrap_edit(discord.Message.edit)


def apply_artwork_thumbnail(embed: discord.Embed, *, thumbnail: str | None = None) -> discord.Embed:
    """Setzt Thumbnail — Standard ist das Marken-Icon (Artwork-Vorlage)."""
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    elif not embed.thumbnail.url and brand_icon_file() is not None:
        embed.set_thumbnail(url=ARTWORK_THUMBNAIL)
    return embed


def add_embed_fields(
    embed: discord.Embed,
    fields: list[tuple[str, str, bool]] | None,
) -> discord.Embed:
    """Fügt Felder hinzu — inline-Felder werden in Reihen à 3 gruppiert."""
    if not fields:
        return embed
    for name, value, inline in fields:
        embed.add_field(name=name, value=value, inline=inline)
    return embed


def artwork_embed(
    title: str,
    description: str | None = None,
    *,
    fields: list[tuple[str, str, bool]] | None = None,
    thumbnail: str | None = None,
    image: str | None = None,
    color: int | None = None,
) -> discord.Embed:
    """
    Einheitliches Embed nach Artwork-Vorlage: Cyan-Akzent, Thumbnail, 3-Spalten-Felder.

    Args:
        title: Überschrift ohne Emoji-Präfix.
        description: Optionaler Beschreibungstext.
        fields: Felder als (name, value, inline) — inline=True für 3er-Reihen.
        thumbnail: Optionale Thumbnail-URL (sonst Marken-Icon).
        image: Optionales Großbild.
        color: Optionale Farbe (Standard: COLOR_ARTWORK).

    Returns:
        Fertiges discord.Embed-Objekt.
    """
    embed = discord.Embed(
        title=title,
        description=description,
        color=color or Config.COLOR_ARTWORK,
        timestamp=datetime.now(timezone.utc),
    )
    apply_artwork_thumbnail(embed, thumbnail=thumbnail)
    if image:
        embed.set_image(url=image)
    add_embed_fields(embed, fields)
    apply_brand_footer(embed)
    return embed


def success_embed(
    title: str,
    description: str | None = None,
    *,
    fields: list[tuple[str, str, bool]] | None = None,
) -> discord.Embed:
    """
    Erstellt ein grünes Erfolgs-Embed.

    Args:
        title: Überschrift des Embeds.
        description: Optionaler Beschreibungstext.
        fields: Optionale Liste von (name, value, inline) Tupeln.

    Returns:
        Fertiges discord.Embed-Objekt.
    """
    return artwork_embed(title, description, fields=fields)


def error_embed(
    title: str,
    description: str | None = None,
    *,
    fields: list[tuple[str, str, bool]] | None = None,
) -> discord.Embed:
    """
    Erstellt ein Fehler-Embed im Artwork-Stil.

    Args:
        title: Überschrift des Embeds.
        description: Optionaler Beschreibungstext.
        fields: Optionale Felder.

    Returns:
        Fertiges discord.Embed-Objekt.
    """
    return artwork_embed(title, description, fields=fields)


def warning_embed(
    title: str,
    description: str | None = None,
    *,
    fields: list[tuple[str, str, bool]] | None = None,
) -> discord.Embed:
    """
    Erstellt ein Warnungs-Embed im Artwork-Stil.

    Args:
        title: Überschrift des Embeds.
        description: Optionaler Beschreibungstext.
        fields: Optionale Felder.

    Returns:
        Fertiges discord.Embed-Objekt.
    """
    return artwork_embed(title, description, fields=fields)


def info_embed(
    title: str,
    description: str | None = None,
    *,
    fields: list[tuple[str, str, bool]] | None = None,
    thumbnail: str | None = None,
    image: str | None = None,
) -> discord.Embed:
    """
    Erstellt ein Informations-Embed im Artwork-Stil.

    Args:
        title: Überschrift des Embeds.
        description: Optionaler Beschreibungstext.
        fields: Optionale Felder.
        thumbnail: Optionale Thumbnail-URL.
        image: Optionale Bild-URL.

    Returns:
        Fertiges discord.Embed-Objekt.
    """
    return artwork_embed(
        title,
        description,
        fields=fields,
        thumbnail=thumbnail,
        image=image,
    )


def warn_embed(
    target: discord.abc.User,
    moderator: discord.abc.User,
    guild: discord.Guild,
    reason: str,
    *,
    warning_id: int | None = None,
    total_warnings: int | None = None,
) -> discord.Embed:
    """
    Erstellt ein Verwarnungs-Embed mit Grund und Kontext.

    Args:
        target: Verwarntes Mitglied.
        moderator: Ausführender Moderator.
        guild: Discord-Server.
        reason: Grund der Verwarnung.
        warning_id: Optionale Warn-ID aus der Datenbank.
        total_warnings: Optionale Gesamtzahl der Warnungen.

    Returns:
        Fertiges discord.Embed-Objekt.
    """
    fields: list[tuple[str, str, bool]] = [
        ("Grund", reason, False),
        ("Moderator", f"{moderator.mention}\n`{moderator.id}`", True),
    ]
    if warning_id is not None:
        fields.append(("Warn-ID", f"**#{warning_id}**", True))
    if total_warnings is not None:
        fields.append(("Gesamt", f"**{total_warnings}** Warnung(en)", True))

    return artwork_embed(
        "Verwarnung",
        f"{target.mention} wurde auf **{guild.name}** verwarnt.",
        fields=fields,
        thumbnail=target.display_avatar.url,
    )


def moderation_embed(
    action: str,
    target: discord.abc.User,
    moderator: discord.abc.User,
    reason: str | None = None,
    *,
    color: int | None = None,
) -> discord.Embed:
    """
    Erstellt ein Moderations-Log-Embed für Aktionen wie Ban, Kick, etc.

    Args:
        action: Name der Moderationsaktion (z. B. 'Ban').
        target: Betroffener Benutzer.
        moderator: Ausführender Moderator.
        reason: Optionaler Grund.
        color: Optionale Embed-Farbe.

    Returns:
        Fertiges discord.Embed-Objekt.
    """
    return artwork_embed(
        action,
        fields=[
            ("Benutzer", f"{target.mention}\n`{target.id}`", True),
            ("Moderator", f"{moderator.mention}\n`{moderator.id}`", True),
            ("Grund", reason or "Kein Grund angegeben", True),
        ],
        thumbnail=target.display_avatar.url,
        color=color,
    )


def log_event_embed(
    event_name: str,
    description: str,
    *,
    color: int | None = None,
    fields: list[tuple[str, str, bool]] | None = None,
) -> discord.Embed:
    """
    Erstellt ein Embed für Server-Log-Ereignisse.

    Args:
        event_name: Name des Ereignisses.
        description: Beschreibung des Ereignisses.
        color: Optionale Farbe.
        fields: Optionale Zusatzfelder.

    Returns:
        Fertiges discord.Embed-Objekt.
    """
    return artwork_embed(event_name, description, fields=fields, color=color)
