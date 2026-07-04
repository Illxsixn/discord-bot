"""
Reaktionsrollen-Cog.

Ermöglicht Administratoren das Erstellen und Verwalten von Rollen,
die per Emoji-Reaktion vergeben werden.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from database.database import Database
from utils.embeds import error_embed, info_embed, spaced_lines, split_embed_fields, success_embed
from utils.permissions import bot_can_use_channel, is_admin
from utils.reactions import (
    bot_can_manage_role,
    emoji_display,
    emoji_key,
    emoji_to_partial,
    parse_emoji_input,
    toggle_member_role,
)

logger = logging.getLogger(__name__)


@app_commands.default_permissions(administrator=True)
class ReactionRolesCog(commands.GroupCog, group_name="reactionrole", group_description="Reaktionsrollen verwalten"):
    """Reaktionsrollen-System."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db

    async def _fetch_message(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        message_id: int,
    ) -> discord.Message | None:
        """Lädt eine Nachricht sicher."""
        try:
            return await channel.fetch_message(message_id)
        except discord.NotFound:
            return None
        except discord.Forbidden:
            return None

    @app_commands.command(name="add", description="Fügt eine Reaktionsrolle zu einer Nachricht hinzu.")
    @app_commands.describe(
        channel="Kanal der Nachricht",
        message_id="ID der Nachricht",
        emoji="Emoji (Unicode oder Custom)",
        role="Rolle, die vergeben wird",
    )
    @is_admin()
    async def add(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message_id: str,
        emoji: str,
        role: discord.Role,
    ) -> None:
        """Erstellt eine Reaktionsrolle."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return

            if not message_id.isdigit():
                await interaction.followup.send(embed=error_embed("Fehler", "Ungültige Nachrichten-ID."), ephemeral=True)
                return

            allowed, msg = bot_can_use_channel(
                channel,
                read_history=True,
                add_reactions=True,
            )
            if not allowed:
                await interaction.followup.send(embed=error_embed("Kanal nicht nutzbar", msg), ephemeral=True)
                return

            allowed, msg = bot_can_manage_role(interaction.guild, role)
            if not allowed:
                await interaction.followup.send(embed=error_embed("Rolle nicht nutzbar", msg), ephemeral=True)
                return

            message = await self._fetch_message(interaction.guild, channel, int(message_id))
            if message is None:
                await interaction.followup.send(
                    embed=error_embed("Fehler", "Nachricht nicht gefunden oder kein Zugriff."),
                    ephemeral=True,
                )
                return

            emoji_value = parse_emoji_input(emoji)
            existing = await self.db.get_reaction_role(message.id, emoji_value)
            if existing:
                await interaction.followup.send(
                    embed=error_embed("Fehler", "Für dieses Emoji existiert bereits eine Reaktionsrolle."),
                    ephemeral=True,
                )
                return

            record = await self.db.add_reaction_role(
                interaction.guild.id,
                channel.id,
                message.id,
                emoji_value,
                role.id,
            )

            reaction_emoji = await emoji_to_partial(self.bot, interaction.guild, emoji_value)
            try:
                await message.add_reaction(reaction_emoji)
            except discord.HTTPException:
                await self.db.remove_reaction_role(record.id, interaction.guild.id)
                await interaction.followup.send(
                    embed=error_embed("Fehler", "Emoji konnte nicht zur Nachricht hinzugefügt werden."),
                    ephemeral=True,
                )
                return

            await interaction.followup.send(
                embed=success_embed(
                    "Reaktionsrolle erstellt",
                    f"{emoji_display(emoji_value)} → {role.mention}\n"
                    f"Nachricht: {message.jump_url}",
                ),
                ephemeral=True,
            )
        except Exception as exc:
            logger.exception("Reactionrole add fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="list", description="Listet alle Reaktionsrollen auf.")
    @is_admin()
    async def list_roles(self, interaction: discord.Interaction) -> None:
        """Zeigt alle Reaktionsrollen."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return

            records = await self.db.get_reaction_roles_for_guild(interaction.guild.id)
            if not records:
                await interaction.followup.send(
                    embed=info_embed("Reaktionsrollen", "Keine Reaktionsrollen konfiguriert."),
                    ephemeral=True,
                )
                return

            lines = []
            for record in records[:25]:
                role = interaction.guild.get_role(record.role_id)
                role_text = role.mention if role else f"`{record.role_id}` (gelöscht)"
                lines.append(
                    spaced_lines(
                        f"**#{record.id}** · {emoji_display(record.emoji)} → {role_text}",
                        f"Nachricht `{record.message_id}` in <#{record.channel_id}>",
                    )
                )

            embed = info_embed(
                "Reaktionsrollen",
                f"**{len(records)}** Eintrag/Einträge",
                fields=split_embed_fields("Übersicht", lines),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as exc:
            logger.exception("Reactionrole list fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="remove", description="Entfernt eine Reaktionsrolle.")
    @app_commands.describe(reaction_role_id="ID aus /reactionrole list")
    @is_admin()
    async def remove(self, interaction: discord.Interaction, reaction_role_id: int) -> None:
        """Entfernt Reaktionsrolle aus DB."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return

            removed = await self.db.remove_reaction_role(reaction_role_id, interaction.guild.id)
            if removed:
                await interaction.followup.send(
                    embed=success_embed("Entfernt", f"Reaktionsrolle **#{reaction_role_id}** gelöscht."),
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    embed=error_embed("Nicht gefunden", f"Keine Reaktionsrolle mit ID **#{reaction_role_id}**."),
                    ephemeral=True,
                )
        except Exception as exc:
            logger.exception("Reactionrole remove fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """Vergibt Rolle bei Reaktion."""
        if payload.guild_id is None or payload.user_id == self.bot.user.id:
            return

        try:
            record = await self.db.get_reaction_role(payload.message_id, emoji_key(payload.emoji))
            if record is None:
                return

            guild = self.bot.get_guild(payload.guild_id)
            if guild is None:
                return

            member = guild.get_member(payload.user_id)
            if member is None:
                try:
                    member = await guild.fetch_member(payload.user_id)
                except discord.NotFound:
                    return

            role = guild.get_role(record.role_id)
            if role is None:
                return

            success, msg = await toggle_member_role(member, role, add=True)
            if not success and msg:
                logger.warning("Reaktionsrolle add fehlgeschlagen (%s): %s", payload.user_id, msg)
        except Exception as exc:
            logger.exception("on_raw_reaction_add Reaktionsrolle: %s", exc)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        """Entfernt Rolle wenn Reaktion entfernt wird."""
        if payload.guild_id is None or payload.user_id == self.bot.user.id:
            return

        try:
            record = await self.db.get_reaction_role(payload.message_id, emoji_key(payload.emoji))
            if record is None:
                return

            guild = self.bot.get_guild(payload.guild_id)
            if guild is None:
                return

            member = guild.get_member(payload.user_id)
            if member is None:
                return

            role = guild.get_role(record.role_id)
            if role is None:
                return

            await toggle_member_role(member, role, add=False)
        except Exception as exc:
            logger.exception("on_raw_reaction_remove Reaktionsrolle: %s", exc)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        """Bereinigt Reaktionsrollen gelöschter Nachrichten."""
        try:
            await self.db.remove_reaction_roles_for_message(payload.message_id)
        except Exception as exc:
            logger.exception("Reaktionsrollen Cleanup fehlgeschlagen: %s", exc)


async def setup(bot: commands.Bot) -> None:
    """Lädt Reaktionsrollen-Cog."""
    db: Database = bot.db  # type: ignore[attr-defined]
    await bot.add_cog(ReactionRolesCog(bot, db))
