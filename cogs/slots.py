"""
Slot-Maschine: Embed mit Einsatz-Buttons und Dreh-Funktion.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from config import Config
from database.database import Database
from utils.embeds import error_embed
from utils.slot_embeds import build_slots_embed
from utils.slots import resolve_spin, spin_reels

logger = logging.getLogger(__name__)


class SlotsView(discord.ui.View):
    """Interaktive Slot-Maschine mit Einsatzwahl."""

    def __init__(self, cog: "SlotsCog", owner_id: int, guild_id: int, *, bet: int) -> None:
        super().__init__(timeout=Config.SLOT_VIEW_TIMEOUT)
        self.cog = cog
        self.owner_id = owner_id
        self.guild_id = guild_id
        self.bet = bet
        self._spinning = False
        self._spin_btn: discord.ui.Button | None = None
        self._build_bet_buttons()

    def _build_bet_buttons(self) -> None:
        """Einsatz-Buttons dynamisch erzeugen."""
        for amount in Config.SLOT_BET_OPTIONS:
            style = (
                discord.ButtonStyle.primary
                if amount == self.bet
                else discord.ButtonStyle.secondary
            )
            btn = discord.ui.Button(
                label=f"{amount} 🪙",
                style=style,
                custom_id=f"slot_bet_{amount}",
            )
            btn.callback = self._make_bet_callback(amount)
            self.add_item(btn)

        spin_btn = discord.ui.Button(
            label="Drehen",
            style=discord.ButtonStyle.success,
            emoji="🎰",
            row=1,
            custom_id="slot_spin",
        )
        spin_btn.callback = self._spin_callback
        self._spin_btn = spin_btn
        self.add_item(spin_btn)

    def _set_spin_disabled(self, disabled: bool) -> None:
        if self._spin_btn is not None:
            self._spin_btn.disabled = disabled

    def _sync_spin_disabled(self) -> None:
        """Spin-Button während laufender Drehung deaktivieren."""
        self._set_spin_disabled(self._spinning)

    def _make_bet_callback(self, amount: int):
        async def callback(interaction: discord.Interaction) -> None:
            await self.cog._set_bet(interaction, self, amount)

        return callback

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                embed=error_embed("Nicht deine Maschine", "Starte mit `/slots`."),
                ephemeral=True,
            )
            return False
        return True

    async def _spin_callback(self, interaction: discord.Interaction) -> None:
        await self.cog._spin(interaction, self)


class SlotsCog(commands.Cog):
    """Gold-Slot-Maschine."""

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
        logger.exception("Slots-Fehler: %s", error)

    async def _refresh_view(self, interaction: discord.Interaction, view: SlotsView) -> None:
        economy = await self.db.get_player_economy(view.guild_id, view.owner_id)
        embed = build_slots_embed(gold=economy.gold, bet=view.bet)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _set_bet(self, interaction: discord.Interaction, view: SlotsView, amount: int) -> None:
        view.bet = amount
        view.clear_items()
        view._build_bet_buttons()
        view._sync_spin_disabled()
        await self._refresh_view(interaction, view)

    async def _spin(self, interaction: discord.Interaction, view: SlotsView) -> None:
        if view._spinning:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
            return

        economy = await self.db.get_player_economy(view.guild_id, view.owner_id)
        if economy.gold < view.bet:
            await interaction.response.send_message(
                embed=error_embed(
                    "Nicht genug Gold",
                    f"Du brauchst **{view.bet:,}** 🪙, hast **{economy.gold:,}**.\n"
                    "Gold durch /zombies, Spiele oder Minigames.",
                ),
                ephemeral=True,
            )
            return

        view._spinning = True
        view._set_spin_disabled(True)
        await interaction.response.defer()

        economy.gold -= view.bet
        reels = spin_reels()
        result = resolve_spin(reels, view.bet)
        economy.gold += result.payout
        await self.db.save_player_economy(economy)

        net = result.payout - view.bet
        if net > 0:
            result_line = f"{result.message}\n**Netto: +{net:,}** 🪙"
            won = True
        elif net == 0:
            result_line = f"{result.message}\n**Break-even** — Einsatz zurück."
            won = None
        else:
            result_line = f"{result.message}\n**−{view.bet:,}** 🪙"
            won = False

        embed = build_slots_embed(
            gold=economy.gold,
            bet=view.bet,
            reels=reels,
            result_line=result_line,
            won=won,
            jackpot=result.jackpot,
        )

        view._spinning = False
        view._sync_spin_disabled()
        await interaction.edit_original_response(embed=embed, view=view)

    @app_commands.command(name="slots", description="Öffnet die Gold-Slot-Maschine")
    @app_commands.guild_only()
    async def slots(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        economy = await self.db.get_player_economy(interaction.guild.id, interaction.user.id)
        bet = Config.SLOT_DEFAULT_BET
        embed = build_slots_embed(gold=economy.gold, bet=bet)
        view = SlotsView(self, interaction.user.id, interaction.guild.id, bet=bet)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    db: Database = bot.db  # type: ignore[attr-defined]
    await bot.add_cog(SlotsCog(bot, db))
