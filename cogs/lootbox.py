"""
Lootbox-Cog: Gold, Kauf und Öffnen von Lootboxen.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from config import Config
from database.database import Database
from utils.embeds import error_embed, info_embed, success_embed
from utils.lootboxes import apply_lootbox_roll, roll_lootbox
from utils.shop_actions import buy_lootboxes

logger = logging.getLogger(__name__)


class LootboxCog(commands.GroupCog, group_name="lootbox", group_description="Lootboxen öffnen und Gold-Rangliste"):
    """Lootbox-Inventar öffnen und Gold-Rangliste."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.CheckFailure):
            return
        logger.exception("Lootbox-Befehl Fehler: %s", error)
        embed = error_embed("Lootbox-Befehl fehlgeschlagen", str(error))
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass

    def _channel(self, interaction: discord.Interaction) -> discord.TextChannel | discord.Thread | None:
        if isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
            return interaction.channel
        return None

    @app_commands.command(name="open", description="Öffnet Lootboxen aus deinem Inventar")
    @app_commands.guild_only()
    @app_commands.describe(anzahl="Anzahl zu öffnender Lootboxen (1–10)")
    async def open_boxes(
        self,
        interaction: discord.Interaction,
        anzahl: app_commands.Range[int, 1, Config.LOOTBOX_BATCH_MAX],
    ) -> None:
        """Lootboxen öffnen."""
        assert interaction.guild is not None
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Nur Server-Mitglieder können Lootboxen öffnen."),
                ephemeral=True,
            )
            return

        count = int(anzahl)
        economy = await self.db.get_player_economy(interaction.guild.id, interaction.user.id)

        if economy.lootbox_count < count:
            embed = error_embed(
                "Keine Lootboxen",
                f"Du hast nur **{economy.lootbox_count}** Lootbox(en).\n"
                f"Kaufe welche mit **`/lootbox buy`** (**{Config.LOOTBOX_PRICE}** Gold pro Stück).",
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        channel = self._channel(interaction)
        wins = 0
        lines: list[str] = []

        for i in range(count):
            roll = roll_lootbox()
            if roll.won_xp:
                player_ok, pet_ok = await apply_lootbox_roll(
                    self.bot,
                    interaction.user,
                    roll,
                    channel=channel,
                )
                wins += 1
                parts: list[str] = []
                if player_ok:
                    parts.append(f"**{roll.player_xp}** Spieler-XP")
                if pet_ok:
                    parts.append(f"**{roll.pet_xp}** Pet-XP")
                if not parts:
                    parts.append("Jackpot — XP-Systeme nicht verfügbar")
                lines.append(f"📦 **{i + 1}:** 🎉 **{', '.join(parts)}** ({roll.chance_percent} % Chance)")
            else:
                lines.append(f"📦 **{i + 1}:** Kein Jackpot ({roll.chance_percent} % Chance)")

        economy.lootbox_count -= count
        await self.db.save_player_economy(economy)

        summary = (
            f"**{count}** Lootbox(en) geöffnet · **{wins}** Jackpot(s)\n"
            f"Verbleibend: **{economy.lootbox_count}** 📦"
        )
        body = summary + "\n\n" + "\n".join(lines)
        if wins:
            embed = success_embed("Lootbox geöffnet", body)
        else:
            embed = info_embed("Lootbox geöffnet", body)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="buy", description="Kauft Lootboxen mit Gold")
    @app_commands.guild_only()
    @app_commands.describe(anzahl="Anzahl Lootboxen (1–10)")
    async def buy(
        self,
        interaction: discord.Interaction,
        anzahl: app_commands.Range[int, 1, Config.LOOTBOX_BATCH_MAX],
    ) -> None:
        """Lootboxen mit Gold kaufen."""
        assert interaction.guild is not None
        _, embed, _ = await buy_lootboxes(
            self.db,
            interaction.guild.id,
            interaction.user.id,
            int(anzahl),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="leaderboard", description="Gold-Rangliste des Servers")
    @app_commands.guild_only()
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        """Top-Spieler nach Gold."""
        assert interaction.guild is not None
        rows = await self.db.get_gold_leaderboard(
            interaction.guild.id,
            limit=Config.LOOTBOX_LEADERBOARD_LIMIT,
        )
        if not rows:
            await interaction.response.send_message(
                embed=info_embed("Gold-Rangliste", "Noch niemand hat Gold gesammelt."),
                ephemeral=True,
            )
            return

        lines: list[str] = []
        for rank, record in enumerate(rows, start=1):
            member = interaction.guild.get_member(record.user_id)
            name = member.display_name if member else f"User {record.user_id}"
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"**{rank}.**")
            lines.append(f"{medal} {name} — **{record.gold:,}** 🪙")

        embed = info_embed("Gold-Rangliste", "\n".join(lines))
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Lädt Lootbox-Cog."""
    db: Database = bot.db  # type: ignore[attr-defined]
    await bot.add_cog(LootboxCog(bot, db))
