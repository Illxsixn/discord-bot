"""
Professionelles Embed-System für den Discord-Bot.

Stellt einheitliche Erfolgs-, Fehler-, Warn- und Info-Embeds bereit,
sodass alle Cogs konsistente Nachrichten anzeigen.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import discord

from config import Config

BRAND_ICON_ATTACHMENT = "anarchy_icon.png"
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


def apply_brand_footer(
    embed: discord.Embed,
    *,
    prefix: str | None = None,
    with_icon: bool = True,
) -> discord.Embed:
    """Setzt einheitliche Footer-Signatur, optional mit Marken-Icon."""
    text = _footer(prefix=prefix)
    if with_icon and brand_icon_file() is not None:
        embed.set_footer(text=text, icon_url=f"attachment://{BRAND_ICON_ATTACHMENT}")
    else:
        embed.set_footer(text=text)
    return embed


def _embed_uses_attachment_image(embed: discord.Embed) -> bool:
    """True wenn das Embed-Bild aus einem Anhang kommt."""
    return bool(
        embed.image
        and embed.image.url
        and embed.image.url.startswith("attachment://")
    )


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

    uses_attachment_image = any(_embed_uses_attachment_image(embed) for embed in embeds)
    if uses_attachment_image:
        for embed in embeds:
            footer = embed.footer
            if footer.text and Config.BOT_BRAND_NAME in footer.text:
                continue
            if footer.text:
                apply_brand_footer(embed, prefix=footer.text, with_icon=False)
            else:
                apply_brand_footer(embed, with_icon=False)
        return kwargs

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


def _pop_embed_send_flags(kwargs: dict[str, Any]) -> bool:
    """
    Entfernt Bot-interne Send-Flags und gibt zurück, ob Auto-Löschung geplant werden soll.
    """
    persistent = bool(kwargs.pop("embed_persistent", False))
    kwargs.pop("embed_no_autodelete", None)
    if persistent or Config.EMBED_AUTO_DELETE_SECONDS <= 0:
        return False
    if kwargs.get("ephemeral"):
        return False
    return bool(_collect_embeds(kwargs))


def schedule_embed_message_delete(message: discord.Message) -> None:
    """Löscht eine Embed-Nachricht nach der konfigurierten Wartezeit."""
    delay = Config.EMBED_AUTO_DELETE_SECONDS

    async def _worker() -> None:
        await asyncio.sleep(delay)
        try:
            await message.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    asyncio.create_task(_worker())


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
            schedule_delete = _pop_embed_send_flags(kwargs)
            kwargs = inject_brand_into_send_kwargs(kwargs)
            message = await method(self, *args, **kwargs)
            if schedule_delete and isinstance(message, discord.Message):
                schedule_embed_message_delete(message)
            return message

        return wrapper

    def _wrap_edit(method: Any) -> Any:
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            _pop_embed_send_flags(kwargs)
            kwargs = inject_brand_into_edit_kwargs(kwargs)
            return await method(self, *args, **kwargs)

        return wrapper

    discord.abc.Messageable.send = _wrap_send(discord.abc.Messageable.send)
    discord.interactions.InteractionResponse.send_message = _wrap_send(
        discord.interactions.InteractionResponse.send_message
    )
    discord.interactions.InteractionResponse.edit_message = _wrap_edit(
        discord.interactions.InteractionResponse.edit_message
    )
    discord.interactions.Interaction.edit_original_response = _wrap_edit(
        discord.interactions.Interaction.edit_original_response
    )
    webhook_async.Webhook.send = _wrap_send(webhook_async.Webhook.send)
    discord.Message.edit = _wrap_edit(discord.Message.edit)


def artwork_embed(
    title: str,
    description: str | None = None,
    *,
    fields: list[tuple[str, str, bool]] | None = None,
    thumbnail: str | None = None,
    image: str | None = None,
    footer_prefix: str | None = None,
    author_name: str | None = None,
    author_icon_url: str | None = None,
    with_icon: bool = True,
) -> discord.Embed:
    """
    Erstellt ein neutrales Inhalts-Embed in der Markenfarbe (dunkel-lila).

    Args:
        title: Überschrift des Embeds.
        description: Optionaler Beschreibungstext.
        fields: Optionale Felder.
        thumbnail: Optionale Thumbnail-URL.
        image: Optionale Bild-URL.
        footer_prefix: Optionaler Text vor der Marken-Signatur im Footer.
        author_name: Optionaler Autor-Name über dem Embed.
        author_icon_url: Optionale Autor-Icon-URL.
        with_icon: Ob das Marken-Icon im Footer erscheint.

    Returns:
        Fertiges discord.Embed-Objekt.
    """
    embed = discord.Embed(
        title=title,
        description=description,
        color=Config.COLOR_ARTWORK,
        timestamp=datetime.now(timezone.utc),
    )
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if image:
        embed.set_image(url=image)
    if author_name:
        embed.set_author(name=author_name, icon_url=author_icon_url)
    apply_brand_footer(embed, prefix=footer_prefix, with_icon=with_icon)
    return embed


def success_embed(
    title: str,
    description: str | None = None,
    *,
    fields: list[tuple[str, str, bool]] | None = None,
    thumbnail: str | None = None,
    image: str | None = None,
    footer_prefix: str | None = None,
    with_icon: bool = True,
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
    embed = discord.Embed(
        title=f"✅ {title}",
        description=description,
        color=Config.COLOR_SUCCESS,
        timestamp=datetime.now(timezone.utc),
    )
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if image:
        embed.set_image(url=image)
    apply_brand_footer(embed, prefix=footer_prefix, with_icon=with_icon)
    return embed


def error_embed(
    title: str,
    description: str | None = None,
    *,
    fields: list[tuple[str, str, bool]] | None = None,
    thumbnail: str | None = None,
    image: str | None = None,
    footer_prefix: str | None = None,
    with_icon: bool = True,
) -> discord.Embed:
    """
    Erstellt ein rotes Fehler-Embed.

    Args:
        title: Überschrift des Embeds.
        description: Optionaler Beschreibungstext.
        fields: Optionale Felder.

    Returns:
        Fertiges discord.Embed-Objekt.
    """
    embed = discord.Embed(
        title=f"❌ {title}",
        description=description,
        color=Config.COLOR_ERROR,
        timestamp=datetime.now(timezone.utc),
    )
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if image:
        embed.set_image(url=image)
    apply_brand_footer(embed, prefix=footer_prefix, with_icon=with_icon)
    return embed


def warning_embed(
    title: str,
    description: str | None = None,
    *,
    fields: list[tuple[str, str, bool]] | None = None,
    thumbnail: str | None = None,
    image: str | None = None,
    footer_prefix: str | None = None,
    with_icon: bool = True,
) -> discord.Embed:
    """
    Erstellt ein gelbes Warnungs-Embed.

    Args:
        title: Überschrift des Embeds.
        description: Optionaler Beschreibungstext.
        fields: Optionale Felder.

    Returns:
        Fertiges discord.Embed-Objekt.
    """
    embed = discord.Embed(
        title=f"⚠️ {title}",
        description=description,
        color=Config.COLOR_WARNING,
        timestamp=datetime.now(timezone.utc),
    )
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if image:
        embed.set_image(url=image)
    apply_brand_footer(embed, prefix=footer_prefix, with_icon=with_icon)
    return embed


def info_embed(
    title: str,
    description: str | None = None,
    *,
    fields: list[tuple[str, str, bool]] | None = None,
    thumbnail: str | None = None,
    image: str | None = None,
    footer_prefix: str | None = None,
    author_name: str | None = None,
    author_icon_url: str | None = None,
    with_icon: bool = True,
) -> discord.Embed:
    """
    Erstellt ein Informations-Embed in der Markenfarbe (dunkel-lila).

    Layout wie ``artwork_embed``: Titel, Beschreibung, optionale Felder (gern inline).
    """
    return artwork_embed(
        f"ℹ️ {title}",
        description,
        fields=fields,
        thumbnail=thumbnail,
        image=image,
        footer_prefix=footer_prefix,
        author_name=author_name,
        author_icon_url=author_icon_url,
        with_icon=with_icon,
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
    """Erstellt ein Verwarnungs-Embed mit Grund und Kontext."""
    fields: list[tuple[str, str, bool]] = [
        ("Grund", reason, False),
        (
            "Moderator",
            spaced_lines(f"{moderator.mention}", f"`{moderator.id}`"),
            True,
        ),
    ]
    if warning_id is not None:
        fields.append(("Warn-ID", f"**#{warning_id}**", True))
    if total_warnings is not None:
        fields.append(("Gesamt", f"**{total_warnings}** Warnung(en)", True))

    return warning_embed(
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
    fields: list[tuple[str, str, bool]] | None = None,
) -> discord.Embed:
    """Erstellt ein Moderations-Log-Embed für Aktionen wie Ban, Kick, etc."""
    base_fields: list[tuple[str, str, bool]] = [
        (
            "Benutzer",
            spaced_lines(f"{target.mention}", f"`{target.id}`"),
            True,
        ),
        (
            "Moderator",
            spaced_lines(f"{moderator.mention}", f"`{moderator.id}`"),
            True,
        ),
        ("Aktion", f"**{action}**", True),
        ("Grund", reason or "Kein Grund angegeben", False),
    ]
    if fields:
        base_fields.extend(fields)

    return log_event_embed(
        action,
        description="",
        color=color or Config.COLOR_ARTWORK,
        fields=base_fields,
        thumbnail=target.display_avatar.url,
    )


def log_event_embed(
    event_name: str,
    description: str,
    *,
    color: int | None = None,
    fields: list[tuple[str, str, bool]] | None = None,
    thumbnail: str | None = None,
    footer_prefix: str | None = None,
    with_icon: bool = True,
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
    embed = discord.Embed(
        title=f"📋 {event_name}",
        description=description,
        color=color or Config.COLOR_ARTWORK,
        timestamp=datetime.now(timezone.utc),
    )
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    apply_brand_footer(embed, prefix=footer_prefix, with_icon=with_icon)
    return embed
