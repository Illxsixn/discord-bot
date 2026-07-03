"""
Level-System Cog.

Vergibt XP für Nachrichten, erkennt Levelaufstiege und bietet
Rankings sowie Admin-Konfiguration unter /levels.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from config import Config
from database.database import Database
from utils.embeds import error_embed, info_embed, spaced_lines, spaced_list, success_embed
from utils.economy_display import format_gold_line, format_zombie_stat_line, get_profile_economy
from utils.levels import level_from_xp, progress_bar, xp_progress
from utils.permissions import bot_can_use_channel, is_admin
from utils.pets import apply_pet_xp_boost

logger = logging.getLogger(__name__)


class LevelsCog(commands.GroupCog, group_name="levels", group_description="Level-System, XP und Rankings"):
    """XP-System, Level-Befehle und Admin-Konfiguration."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Fängt Level-Befehlsfehler ab und antwortet mit Embed."""
        if isinstance(error, app_commands.CheckFailure):
            return
        logger.exception("Level-Befehl Fehler: %s", error)
        embed = error_embed("Level-Befehl fehlgeschlagen", str(error))
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass

    async def _build_level_embed(
        self,
        guild: discord.Guild,
        member: discord.Member,
    ) -> discord.Embed:
        """Erstellt Level-Embed für ein Mitglied."""
        record = await self.db.get_user_level(guild.id, member.id)
        rank = await self.db.get_user_rank(guild.id, member.id)
        current, needed, percent = xp_progress(record.xp, record.level)
        next_level = record.level + 1
        economy = await get_profile_economy(self.db, guild.id, member.id, record.level)
        zombie_line = await format_zombie_stat_line(self.db, guild.id, member.id)

        embed = info_embed(
            f"Level — {member.display_name}",
            member.mention,
            fields=[
                (
                    "📊 Übersicht",
                    spaced_lines(
                        f"**Level:** {record.level}",
                        f"**Rang:** #{rank}",
                        f"**XP gesamt:** {record.xp:,}",
                        f"**Gold:** {economy.gold:,} 🪙",
                        f"**Zombie Survival:** {zombie_line}",
                    ),
                    False,
                ),
                (
                    "Fortschritt",
                    spaced_lines(
                        f"`{progress_bar(percent)}` **{percent}%**",
                        f"**{current:,}** / **{needed:,}** XP bis Level **{next_level}**",
                    ),
                    False,
                ),
                (
                    "XP pro Nachricht",
                    f"**{Config.XP_PER_MESSAGE} XP** (Cooldown: **{Config.LEVEL_XP_COOLDOWN}s**)",
                    False,
                ),
            ],
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        return embed

    async def _announce_level_up(
        self,
        member: discord.Member,
        old_level: int,
        new_level: int,
        channel: discord.TextChannel | discord.Thread | None,
    ) -> None:
        """Sendet Level-Up Embed."""
        settings = await self.db.get_guild_settings(member.guild.id)
        if not settings.levels_announce_enabled:
            return

        if channel is None:
            return

        target = channel
        if settings.levels_announce_channel_id:
            ch = member.guild.get_channel(settings.levels_announce_channel_id)
            if isinstance(ch, (discord.TextChannel, discord.Thread)):
                target = ch

        if target is None:
            return

        allowed, _ = bot_can_use_channel(target, send=True, embed_links=True)
        if not allowed:
            logger.warning("Level-Up Kanal nicht beschreibbar (Guild %s).", member.guild.id)
            return

        embed = success_embed(
            "Level-Up!",
            f"🎉 {member.mention} ist aufgestiegen!\nAktuelles Level: **{new_level}**",
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        try:
            await target.send(embed=embed, embed_persistent=True)
        except discord.Forbidden:
            logger.warning("Level-Up Nachricht konnte nicht gesendet werden (Guild %s).", member.guild.id)

    async def _boosted_player_xp(self, member: discord.Member, amount: int) -> int:
        """Wendet den Seltenheits-Bonus des aktiven Pets auf Spieler-XP an."""
        pet = await self.db.get_active_pet(member.guild.id, member.id)
        if pet is None:
            return amount
        return apply_pet_xp_boost(amount, species_name=pet.species)

    async def award_xp(
        self,
        member: discord.Member,
        amount: int,
        *,
        channel: discord.TextChannel | discord.Thread | None = None,
        apply_pet_boost: bool = True,
        announce_level_up: bool = True,
    ) -> bool:
        """
        Vergibt XP an ein Mitglied (z. B. durch Spiele oder Aufgaben).

        Returns:
            True wenn XP vergeben wurde.
        """
        if amount <= 0 or member.bot:
            return False

        settings = await self.db.get_guild_settings(member.guild.id)
        if not settings.levels_enabled:
            return False

        amount = await self._boosted_player_xp(member, amount) if apply_pet_boost else amount
        record = await self.db.get_user_level(member.guild.id, member.id)
        old_level = record.level
        record.xp += amount
        record.level = level_from_xp(record.xp)
        await self.db.save_user_level(record)

        if record.level > old_level and announce_level_up:
            await self._announce_level_up(member, old_level, record.level, channel)

        return True

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Vergibt XP für Nachrichten (mit Cooldown)."""
        if message.author.bot or message.guild is None or not isinstance(message.author, discord.Member):
            return

        try:
            settings = await self.db.get_guild_settings(message.guild.id)
            if not settings.levels_enabled:
                return

            record = await self.db.get_user_level(message.guild.id, message.author.id)
            now = datetime.now(timezone.utc)
            if record.last_xp_at is not None:
                elapsed = (now - record.last_xp_at).total_seconds()
                if elapsed < Config.LEVEL_XP_COOLDOWN:
                    return

            old_level = record.level
            xp_amount = await self._boosted_player_xp(message.author, Config.XP_PER_MESSAGE)
            record.xp += xp_amount
            record.level = level_from_xp(record.xp)
            record.last_xp_at = now
            await self.db.save_user_level(record)

            if record.level > old_level:
                channel = message.channel if isinstance(message.channel, (discord.TextChannel, discord.Thread)) else None
                await self._announce_level_up(message.author, old_level, record.level, channel)

            pets = self.bot.get_cog("PetsCog")
            if pets is not None:
                channel = message.channel if isinstance(message.channel, (discord.TextChannel, discord.Thread)) else None
                await pets.award_pet_activity_xp(message.author, channel=channel)  # type: ignore[attr-defined]

        except Exception as exc:
            logger.exception("Level-XP Vergabe fehlgeschlagen: %s", exc)

    async def _show_level(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None = None,
    ) -> None:
        """Zeigt Level-Informationen für ein Mitglied."""
        await interaction.response.defer(ephemeral=True)
        if interaction.guild is None:
            await interaction.followup.send(
                embed=error_embed("Fehler", "Dieser Befehl ist nur auf Servern verfügbar."),
                ephemeral=True,
            )
            return

        target = user or interaction.user
        if not isinstance(target, discord.Member):
            member = interaction.guild.get_member(target.id)
            if member is None:
                await interaction.followup.send(
                    embed=error_embed("Fehler", "Mitglied nicht auf diesem Server gefunden."),
                    ephemeral=True,
                )
                return
            target = member

        embed = await self._build_level_embed(interaction.guild, target)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="level", description="Zeigt Level und XP eines Mitglieds.")
    @app_commands.guild_only()
    @app_commands.describe(user="Mitglied (Standard: du selbst)")
    async def level(self, interaction: discord.Interaction, user: discord.Member | None = None) -> None:
        """Zeigt Level-Informationen."""
        await self._show_level(interaction, user)

    @app_commands.command(name="rank", description="Alias für /levels level — zeigt Level und XP.")
    @app_commands.guild_only()
    @app_commands.describe(user="Mitglied (Standard: du selbst)")
    async def rank(self, interaction: discord.Interaction, user: discord.Member | None = None) -> None:
        """Alias für Level-Anzeige."""
        await self._show_level(interaction, user)

    @app_commands.command(name="leaderboard", description="Zeigt das Server-Level-Ranking.")
    @app_commands.guild_only()
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        """Zeigt Top-N Ranking."""
        await interaction.response.defer(ephemeral=True)

        records = await self.db.get_level_leaderboard(
            interaction.guild.id,  # type: ignore[union-attr]
            limit=Config.LEVEL_LEADERBOARD_LIMIT,
        )
        if not records:
            await interaction.followup.send(
                embed=info_embed("Leaderboard", "Noch keine XP-Daten vorhanden."),
                ephemeral=True,
            )
            return

        lines = []
        medals = ("🥇", "🥈", "🥉")
        for index, record in enumerate(records, start=1):
            member = interaction.guild.get_member(record.user_id)  # type: ignore[union-attr]
            name = member.display_name if member else f"User `{record.user_id}`"
            prefix = medals[index - 1] if index <= 3 else f"**{index}.**"
            lines.append(
                spaced_lines(
                    f"{prefix} **{name}**",
                    f"Level **{record.level}** · **{record.xp:,}** XP",
                )
            )

        embed = info_embed(
            f"Leaderboard — {interaction.guild.name}",  # type: ignore[union-attr]
            f"Top **{len(records)}** aktivste Mitglieder",
            fields=[("Rangliste", spaced_list(lines), False)],
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="enable", description="Aktiviert das Level-System.")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    async def enable(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        if interaction.guild is None:
            return
        settings = await self.db.get_guild_settings(interaction.guild.id)
        if settings.levels_enabled:
            await interaction.followup.send(
                embed=error_embed("Bereits aktiv", "Das Level-System ist bereits aktiviert."),
                ephemeral=True,
            )
            return
        await self.db.update_guild_settings(interaction.guild.id, levels_enabled=True)  # type: ignore[union-attr]
        await interaction.followup.send(
            embed=success_embed(
                "Level-System aktiv",
                f"Mitglieder erhalten jetzt **{Config.XP_PER_MESSAGE} XP** pro Nachricht "
                f"(Cooldown: **{Config.LEVEL_XP_COOLDOWN} Sekunden**).",
            ),
            ephemeral=True,
        )

    @app_commands.command(name="disable", description="Deaktiviert das Level-System.")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    async def disable(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await self.db.update_guild_settings(interaction.guild.id, levels_enabled=False)  # type: ignore[union-attr]
        await interaction.followup.send(
            embed=success_embed("Level-System aus", "Keine XP-Vergabe mehr."),
            ephemeral=True,
        )

    @app_commands.command(name="announce", description="Setzt den Kanal für Level-Up Nachrichten.")
    @app_commands.describe(channel="Kanal (leer = Nachrichtenkanal)", enabled="Level-Up Nachrichten an/aus")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    async def announce(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        enabled: bool = True,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        if channel is not None:
            allowed, msg = bot_can_use_channel(channel, send=True, embed_links=True)
            if not allowed:
                await interaction.followup.send(embed=error_embed("Kanal nicht nutzbar", msg), ephemeral=True)
                return
        await self.db.update_guild_settings(
            interaction.guild.id,  # type: ignore[union-attr]
            levels_announce_channel_id=channel.id if channel else None,
            levels_announce_enabled=enabled,
        )
        ch_text = channel.mention if channel else "Nachrichtenkanal"
        status = "aktiv" if enabled else "deaktiviert"
        await interaction.followup.send(
            embed=success_embed("Level-Up Ankündigung", f"Kanal: {ch_text} • Status: **{status}**"),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    """Lädt Level-Cog."""
    db: Database = bot.db  # type: ignore[attr-defined]
    await bot.add_cog(LevelsCog(bot, db))
