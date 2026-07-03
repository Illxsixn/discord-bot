"""
Lootbox-Kauf — gemeinsame Kauf-Logik für /lootbox buy.
"""

from __future__ import annotations

import discord

from config import Config
from database.database import Database
from database.models import PlayerEconomyRecord
from utils.embeds import error_embed, success_embed


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
    total_cost = Config.LOOTBOX_PRICE * count
    economy = await db.get_player_economy(guild_id, user_id)

    if economy.gold < total_cost:
        embed = error_embed(
            "Nicht genug Gold",
            f"Du brauchst **{total_cost:,}** Gold, hast aber nur **{economy.gold:,}** 🪙.\n"
            f"Gold z. B. durch **`/zombies`**, Spielsiege "
            f"(**{Config.GAME_WIN_GOLD_MIN}–{Config.GAME_WIN_GOLD_MAX}**) oder **`/slots`**.",
        )
        return False, embed, economy

    economy.gold -= total_cost
    economy.lootbox_count += count
    await db.save_player_economy(economy)

    embed = success_embed(
        "Lootboxen gekauft",
        f"**{count}** Lootbox(en) für **{total_cost:,}** Gold.\n"
        f"Inventar: **{economy.lootbox_count}** 📦 · Gold: **{economy.gold:,}** 🪙\n\n"
        "Öffne sie mit **`/lootbox open`**.",
    )
    return True, embed, economy
