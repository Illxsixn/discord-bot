"""
Shop-Embeds — einzige Anzeige für kaufbare Produkte (Lootboxen, Perks, …).
"""

from __future__ import annotations

import discord

from config import Config
from database.models import PlayerEconomyRecord
from utils.embeds import info_embed


def build_shop_embed(economy: PlayerEconomyRecord) -> discord.Embed:
    """Zentraler Shop — Lootboxen und weitere Produkte."""
    return info_embed(
        "Shop",
        "Kaufe Lootboxen mit **Gold** — weitere Produkte folgen.",
        fields=[
            ("Dein Gold", f"**{economy.gold:,}** 🪙", True),
            ("Lootboxen", f"**{economy.lootbox_count}** 📦", True),
            ("Preis", f"**{Config.LOOTBOX_PRICE}** Gold pro Box", True),
            (
                "Lootbox",
                f"Jackpot **{Config.LOOTBOX_XP_CHANCE_MIN}–{Config.LOOTBOX_XP_CHANCE_MAX} %** · "
                f"**{Config.LOOTBOX_XP_REWARD}** XP (Spieler + Pet)",
                True,
            ),
            (
                "Zombie-Perks",
                "Glück · Fokus · Energie — **Coming soon**",
                True,
            ),
            (
                "Gold verdienen",
                f"Spielsiege **{Config.GAME_WIN_GOLD_MIN}–{Config.GAME_WIN_GOLD_MAX}** · Zombie · Slots",
                True,
            ),
        ],
    )
