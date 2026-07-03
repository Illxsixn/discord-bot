"""
Shop-Cog: zentraler Marktplatz für Lootboxen und künftige Produkte.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from config import Config
from database.database import Database
from utils.embeds import info_embed
from utils.shop_actions import buy_lootboxes
from utils.shop_embeds import build_shop_embed

logger = logging.getLogger(__name__)


class ShopView(discord.ui.View):
    """Kauf-Buttons für den zentralen Shop."""

    def __init__(self, cog: "ShopCog", owner_id: int, *, lootbox_count: int = 0) -> None:
        super().__init__(timeout=180.0)
        self.cog = cog
        self.owner_id = owner_id
        self._add_buttons(lootbox_count)

    def _add_buttons(self, lootbox_count: int) -> None:
        remaining = Config.LOOTBOX_INVENTORY_MAX - lootbox_count
        if remaining <= 0:
            buy_btn = discord.ui.Button(
                label="Inventar voll",
                style=discord.ButtonStyle.secondary,
                emoji="📦",
                disabled=True,
            )
            buy_btn.callback = self._inventory_full
            self.add_item(buy_btn)
        else:
            for amount in (1, 2, 3):
                if amount > remaining:
                    continue
                btn = discord.ui.Button(
                    label=f"{amount}× kaufen",
                    style=discord.ButtonStyle.success if amount == 1 else discord.ButtonStyle.primary,
                    emoji="📦",
                )
                btn.callback = self._make_buy_callback(amount)
                self.add_item(btn)

        open_btn = discord.ui.Button(label="Öffnen", style=discord.ButtonStyle.secondary, emoji="🎁")
        open_btn.callback = self._open_hint
        self.add_item(open_btn)

    def _make_buy_callback(self, count: int):
        async def callback(interaction: discord.Interaction) -> None:
            await self.cog._purchase(interaction, count=count)

        return callback

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                embed=info_embed("Shop", "Nutze **`/shop`** für deinen eigenen Shop."),
                ephemeral=True,
            )
            return False
        return True

    async def _inventory_full(self, interaction: discord.Interaction) -> None:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

    async def _open_hint(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            embed=info_embed(
                "Lootbox öffnen",
                f"Nutze **`/lootbox open`** (1–{Config.LOOTBOX_BATCH_MAX} Boxen, max. "
                f"**{Config.LOOTBOX_INVENTORY_MAX}** im Inventar).",
            ),
            ephemeral=True,
        )


class ShopCog(commands.Cog):
    """Zentraler Shop — einzige Anzeige für kaufbare Produkte."""

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
        logger.exception("Shop-Befehl Fehler: %s", error)

    async def send_shop(
        self,
        interaction: discord.Interaction,
        *,
        ephemeral: bool = True,
    ) -> None:
        """Shop-Embed senden (auch für andere Cogs nutzbar)."""
        assert interaction.guild is not None
        economy = await self.db.get_player_economy(interaction.guild.id, interaction.user.id)
        embed = build_shop_embed(economy)
        view = ShopView(self, interaction.user.id, lootbox_count=economy.lootbox_count)
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, view=view, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=ephemeral)

    async def _purchase(self, interaction: discord.Interaction, *, count: int) -> None:
        assert interaction.guild is not None
        _, embed, _ = await buy_lootboxes(
            self.db,
            interaction.guild.id,
            interaction.user.id,
            count,
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="shop", description="Shop — Lootboxen und kaufbare Produkte")
    @app_commands.guild_only()
    async def shop(self, interaction: discord.Interaction) -> None:
        await self.send_shop(interaction)


async def setup(bot: commands.Bot) -> None:
    db: Database = bot.db  # type: ignore[attr-defined]
    await bot.add_cog(ShopCog(bot, db))
