"""
Server-Emoji-Verwaltung: Emojis kopieren oder per Bild hochladen.
"""

from __future__ import annotations

import logging
import time

import discord
from discord import app_commands
from discord.ext import commands

from config import Config
from utils.embeds import error_embed, spaced_lines, success_embed
from utils.emojis import (
    derive_emoji_name_from_filename,
    fetch_emoji_bytes,
    is_animated_image,
    parse_custom_emoji,
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

    @app_commands.command(
        name="emoji",
        description="Fügt ein Server-Emoji hinzu — kopieren oder eigenes Bild hochladen.",
    )
    @app_commands.describe(
        emoji="Emoji von einem anderen Server (<:name:id> oder Emoji-Picker)",
        bild="Eigenes Bild hochladen (PNG, JPG, GIF · max. 256 KB)",
    )
    @app_commands.guild_only()
    async def emoji(
        self,
        interaction: discord.Interaction,
        emoji: str | None = None,
        bild: discord.Attachment | None = None,
    ) -> None:
        """Kopiert ein Custom-Emoji oder lädt ein Bild als Server-Emoji hoch."""
        await interaction.response.defer(ephemeral=True)
        if interaction.guild is None:
            return

        key = (interaction.guild.id, interaction.user.id)
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

        if emoji and bild:
            await interaction.followup.send(
                embed=error_embed(
                    "Zu viele Eingaben",
                    "Gib entweder **emoji** (kopieren) **oder** **bild** (hochladen) an — nicht beides.",
                ),
                ephemeral=True,
            )
            return

        if not emoji and not bild:
            await interaction.followup.send(
                embed=error_embed(
                    "Eingabe fehlt",
                    spaced_lines(
                        "**Option 1 — Kopieren:** `emoji` mit einem Custom-Emoji von einem anderen Server",
                        "**Option 2 — Hochladen:** `bild` mit PNG, JPG oder GIF (max. 256 KB)",
                        "Der Name wird automatisch vom Emoji bzw. Dateinamen übernommen.",
                    ),
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

        image_data: bytes
        animated = False
        source_label = "Bild-Upload"
        emoji_name = ""

        try:
            if emoji:
                parsed = parse_custom_emoji(emoji)
                if parsed is None:
                    await interaction.followup.send(
                        embed=error_embed(
                            "Kein Custom-Emoji",
                            "Nur **Custom-Emojis** können kopiert werden "
                            "(z. B. `<:name:123456789>` oder über den Emoji-Picker).",
                        ),
                        ephemeral=True,
                    )
                    return

                emoji_name = parsed.name
                image_data = await fetch_emoji_bytes(parsed)
                animated = parsed.animated or is_animated_image(image_data)
                source_label = f"Kopie von {discord.PartialEmoji(name=parsed.name, id=parsed.emoji_id, animated=parsed.animated)}"
            else:
                assert bild is not None
                emoji_name = derive_emoji_name_from_filename(bild.filename or "emoji")
                image_data = await read_attachment_bytes(bild)
                animated = is_animated_image(image_data)
                source_label = f"Upload: `{bild.filename}`"
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
            message = "Das Emoji konnte nicht erstellt werden."
            if exc.status == 400:
                message = "Discord hat das Bild oder den Namen abgelehnt. Prüfe Format und Größe."
            elif exc.status == 403:
                message = "Keine Berechtigung, Emojis auf diesem Server zu erstellen."
            await interaction.followup.send(embed=error_embed("Erstellung fehlgeschlagen", message), ephemeral=True)
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


async def setup(bot: commands.Bot) -> None:
    """Lädt den Emoji-Cog."""
    await bot.add_cog(EmojiCog(bot))
