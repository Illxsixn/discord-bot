"""
Shop-Aktionen — gemeinsame Kauf-Logik für /shop.
"""

from __future__ import annotations

import discord

from config import Config
from database.database import Database
from database.models import PlayerEconomyRecord
from utils.embeds import error_embed, spaced_lines, success_embed


async def buy_lootboxes(
    db: Database,
    guild_id: int,
    user_id: int,
    count: int,
) -> tuple[bool, discord.Embed, PlayerEconomyRecord | None]:
    """
    Kauft Lootboxen mit Gold.

    Returns:
        (success, embed, economy)
    """
    economy = await db.get_player_economy(guild_id, user_id)
    remaining = Config.LOOTBOX_INVENTORY_MAX - economy.lootbox_count

    if remaining <= 0:
        embed = error_embed(
            "Inventar voll",
            spaced_lines(
                f"Du kannst maximal **{Config.LOOTBOX_INVENTORY_MAX}** Lootboxen gleichzeitig besitzen.",
                "Öffne zuerst Boxen mit **`/lootbox open`**, bevor du neue kaufst.",
            ),
        )
        return False, embed, economy

    if count < 1 or count > Config.LOOTBOX_INVENTORY_MAX:
        embed = error_embed(
            "Ungültige Anzahl",
            f"Pro Kauf sind **1–{Config.LOOTBOX_INVENTORY_MAX}** Lootboxen möglich.",
        )
        return False, embed, economy

    if count > remaining:
        embed = error_embed(
            "Zu viele Lootboxen",
            spaced_lines(
                f"Du hast **{economy.lootbox_count}** 📦 — es passen noch **{remaining}**.",
                f"Kaufe höchstens **{remaining}** Box(en) auf einmal.",
            ),
        )
        return False, embed, economy

    total_cost = Config.LOOTBOX_PRICE * count

    if economy.gold < total_cost:
        embed = error_embed(
            "Nicht genug Gold",
            spaced_lines(
                f"Du brauchst **{total_cost:,}** Gold, hast aber nur **{economy.gold:,}** 🪙.",
                f"Gold z. B. durch **`/zombies`**, Spielsiege "
                f"(**{Config.GAME_WIN_GOLD_MIN}–{Config.GAME_WIN_GOLD_MAX}**) oder **`/slots`**.",
            ),
        )
        return False, embed, economy

    economy.gold -= total_cost
    economy.lootbox_count += count
    await db.save_player_economy(economy)

    embed = success_embed(
        "Lootboxen gekauft",
        spaced_lines(
            f"**{count}** Lootbox(en) für **{total_cost:,}** Gold.",
            "Öffne sie mit **`/lootbox open`**.",
        ),
        fields=[
            ("Gekauft", f"**{count}** 📦", True),
            ("Gold übrig", f"**{economy.gold:,}** 🪙", True),
            ("Inventar", f"**{economy.lootbox_count}** 📦", True),
        ],
    )
    return True, embed, economy
