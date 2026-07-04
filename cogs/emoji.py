"""
Server-Emoji-Verwaltung: Emojis kopieren oder per Bild hochladen.
"""

from __future__ import annotations

import asyncio
import logging
import time

import discord
from discord import app_commands
from discord.ext import commands

from config import Config
from utils.embeds import error_embed, info_embed, spaced_lines, success_embed
from utils.emojis import (
    derive_emoji_name_from_filename,
    fetch_emoji_bytes,
    first_valid_image_attachment,
    is_animated_image,
    parse_first_custom_emoji_from_content,
    read_attachment_bytes,
    validate_emoji_name,
    emoji_slot_error,
)

logger = logging.getLogger(__name__)


class EmojiCog(commands.Cog):
    """Slash-Command zum Hinzufügen von Server-Emojis."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._last_use: dict[tuple[int, int], float] = {}
        self._pending: set[tuple[int, int]] = set()

    @app_commands.command(
        name="emoji",
        description="Fügt ein Server-Emoji hinzu — kopieren oder eigenes Bild hochladen.",
    )
    @app_commands.guild_only()
    async def emoji(self, interaction: discord.Interaction) -> None:
        """Wartet auf eine Nachricht mit Custom-Emoji oder Bild und erstellt ein Server-Emoji."""
        if interaction.guild is None or interaction.channel is None:
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Dieser Befehl funktioniert nur in Server-Kanälen."),
                ephemeral=True,
            )
            return

        session_key = (interaction.guild.id, interaction.user.id)
        if session_key in self._pending:
            await interaction.response.send_message(
                embed=error_embed(
                    "Bereits aktiv",
                    "Du hast bereits ein Emoji hinzufügen laufen. Sende zuerst deine Nachricht oder warte auf das Timeout.",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        key = session_key
        now = time.monotonic()
        elapsed = now - self._last_use.get(key, 0.0)
        if elapsed < Config.EMOJI_USER_COOLDOWN:
            wait = int(Config.EMOJI_USER_COOLDOWN - elapsed) + 1
            await interaction.followup.send(
                embed=error_embed(
                    "Cooldown",
                    f"Bitte **{wait} s** warten, bevor du erneut ein Emoji hinzufügst.",
                ),
                ephemeral=True,
            )
            return

        if interaction.guild.me is None or not interaction.guild.me.guild_permissions.manage_emojis_and_stickers:
            await interaction.followup.send(
                embed=error_embed(
                    "Bot-Berechtigung fehlt",
                    "Mir fehlt die Berechtigung **Emojis verwalten** auf diesem Server.",
                ),
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            embed=info_embed(
                "Emoji senden",
                spaced_lines(
                    "Schick **jetzt in diesen Kanal** eine Nachricht mit:",
                    "• einem **Custom-Emoji** von einem anderen Server, oder",
                    "• einem **Bild** (PNG, JPG, GIF · max. 256 KB)",
                    "Der Name wird automatisch übernommen.",
                ),
            ),
            ephemeral=True,
        )

        self._pending.add(session_key)
        try:
            def message_from_user(message: discord.Message) -> bool:
                return (
                    message.author.id == interaction.user.id
                    and message.channel.id == interaction.channel.id
                    and not message.author.bot
                )

            try:
                message = await self.bot.wait_for(
                    "message",
                    check=message_from_user,
                    timeout=Config.EMOJI_RESPONSE_TIMEOUT,
                )
            except asyncio.TimeoutError:
                await interaction.followup.send(
                    embed=error_embed(
                        "Zeit abgelaufen",
                        "Keine Nachricht erhalten. Führe **`/emoji`** erneut aus und sende dann dein Emoji oder Bild.",
                    ),
                    ephemeral=True,
                )
                return

            image_data: bytes
            animated = False
            source_label = "Bild-Upload"
            emoji_name = ""

            try:
                parsed = parse_first_custom_emoji_from_content(message.content)
                if parsed is not None:
                    emoji_name = parsed.name
                    image_data = await fetch_emoji_bytes(parsed)
                    animated = parsed.animated or is_animated_image(image_data)
                    source_label = (
                        f"Kopie von {discord.PartialEmoji(name=parsed.name, id=parsed.emoji_id, animated=parsed.animated)}"
                    )
                else:
                    attachment = first_valid_image_attachment(list(message.attachments))
                    if attachment is None:
                        await interaction.followup.send(
                            embed=error_embed(
                                "Keine gültige Eingabe",
                                spaced_lines(
                                    "Die Nachricht enthält weder ein **Custom-Emoji** noch ein gültiges Bild.",
                                    "Erlaubt: PNG, JPG, GIF (max. **256 KB**).",
                                    "Führe **`/emoji`** erneut aus und versuche es noch einmal.",
                                ),
                            ),
                            ephemeral=True,
                        )
                        return

                    emoji_name = derive_emoji_name_from_filename(attachment.filename or "emoji")
                    image_data = await read_attachment_bytes(attachment)
                    animated = is_animated_image(image_data)
                    source_label = f"Upload: `{attachment.filename}`"
            except ValueError as exc:
                await interaction.followup.send(embed=error_embed("Ungültige Datei", str(exc)), ephemeral=True)
                return
            except discord.HTTPException as exc:
                logger.warning("Emoji-Download fehlgeschlagen: %s", exc)
                await interaction.followup.send(
                    embed=error_embed(
                        "Download fehlgeschlagen",
                        "Das Emoji konnte nicht geladen werden. Prüfe die Eingabe und versuche es erneut.",
                    ),
                    ephemeral=True,
                )
                return

            name_error = validate_emoji_name(emoji_name)
            if name_error:
                await interaction.followup.send(
                    embed=error_embed(
                        "Ungültiger Name",
                        spaced_lines(
                            f"Der abgeleitete Name **`{emoji_name}`** ist ungültig.",
                            name_error,
                        ),
                    ),
                    ephemeral=True,
                )
                return

            slot_error = emoji_slot_error(interaction.guild, animated=animated)
            if slot_error:
                await interaction.followup.send(embed=error_embed("Emoji-Limit", slot_error), ephemeral=True)
                return

            try:
                created = await interaction.guild.create_emoji(
                    name=emoji_name,
                    image=image_data,
                    reason=f"/emoji von {interaction.user} ({interaction.user.id})",
                )
            except discord.HTTPException as exc:
                logger.warning("Emoji-Erstellung fehlgeschlagen: %s", exc)
                message_text = "Das Emoji konnte nicht erstellt werden."
                if exc.status == 400:
                    message_text = "Discord hat das Bild oder den Namen abgelehnt. Prüfe Format und Größe."
                elif exc.status == 403:
                    message_text = "Keine Berechtigung, Emojis auf diesem Server zu erstellen."
                await interaction.followup.send(embed=error_embed("Erstellung fehlgeschlagen", message_text), ephemeral=True)
                return

            self._last_use[key] = time.monotonic()
            emoji_type = "Animiert" if created.animated else "Statisch"
            await interaction.followup.send(
                embed=success_embed(
                    "Emoji hinzugefügt",
                    spaced_lines(
                        f"{created} **`{created.name}`**",
                        f"**Typ:** {emoji_type}",
                        f"**Quelle:** {source_label}",
                        f"**Slots:** {len(interaction.guild.emojis)}/{interaction.guild.emoji_limit}",
                    ),
                ),
                ephemeral=True,
            )
        finally:
            self._pending.discard(session_key)


async def setup(bot: commands.Bot) -> None:
    """Lädt den Emoji-Cog."""
    await bot.add_cog(EmojiCog(bot))
