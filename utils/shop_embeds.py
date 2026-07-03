"""
Shop-Embeds — einzige Anzeige für kaufbare Produkte (Lootboxen, Perks, …).
"""

from __future__ import annotations

import discord

from config import Config
from database.models import PlayerEconomyRecord
from utils.embeds import info_embed, spaced_lines


def build_shop_embed(economy: PlayerEconomyRecord) -> discord.Embed:
    """Zentraler Shop — Lootboxen und weitere Produkte."""
    return info_embed(
        "🏪 Shop",
        "Kaufe Lootboxen mit **Gold** — weitere Produkte folgen.",
        fields=[
            ("Dein Gold", f"**{economy.gold:,}** 🪙", True),
            ("Lootboxen", f"**{economy.lootbox_count}** 📦", True),
            ("Preis", f"**{Config.LOOTBOX_PRICE}** Gold pro Box", True),
            (
                "📦 Lootbox",
                spaced_lines(
                    f"Max. **{Config.LOOTBOX_INVENTORY_MAX}** Boxen im Inventar · "
                    f"**{Config.LOOTBOX_PRICE}** Gold",
                    f"Trostpreis: **{Config.LOOTBOX_CONSOLATION_GOLD_MIN}–{Config.LOOTBOX_CONSOLATION_GOLD_MAX}** Gold · "
                    f"**{Config.LOOTBOX_CONSOLATION_XP_MIN}–{Config.LOOTBOX_CONSOLATION_XP_MAX}** Spieler-XP "
                    f"**+** Pet-XP (je Zufall)",
                    f"Jackpot: **{Config.LOOTBOX_XP_CHANCE_MIN}–{Config.LOOTBOX_XP_CHANCE_MAX} %** · "
                    f"extra **{Config.LOOTBOX_XP_MIN}–{Config.LOOTBOX_XP_MAX}** XP",
                ),
                False,
            ),
            (
                "🧟 Zombie-Perks",
                "Glück · Fokus · Energie — **Coming soon**",
                False,
            ),
            (
                "Gold verdienen",
                f"Spielsiege: **{Config.GAME_WIN_GOLD_MIN}–{Config.GAME_WIN_GOLD_MAX}** · "
                f"Zombie Survival · Slots",
                False,
            ),
        ],
    )
