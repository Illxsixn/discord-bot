"""
Anzeige-Hilfen für Gold und Zombie-Survival in Profil-Embeds.
"""

from __future__ import annotations

from database.database import Database
from database.models import PlayerEconomyRecord


async def get_profile_economy(
    db: Database,
    guild_id: int,
    user_id: int,
    player_level: int,
) -> PlayerEconomyRecord:
    """Lädt Economy-Daten für Profil-Anzeige."""
    return await db.get_player_economy(guild_id, user_id)


def format_gold_line(economy: PlayerEconomyRecord) -> str:
    """Gold-Zeile für Embeds."""
    return f"**{economy.gold:,}** 🪙"


async def format_zombie_stat_line(db: Database, guild_id: int, user_id: int) -> str:
    """Kurzzeile Zombie-Survival für Profil-Embeds (Level über /levels)."""
    profile = await db.get_zombie_player(guild_id, user_id)
    level = (await db.get_user_level(guild_id, user_id)).level
    return (
        f"Level **{level}** (/levels) · Welle **{profile.highest_wave}** · "
        f"**{profile.total_kills}** Kills"
    )
