"""
Anzeige-Hilfen für Gold und Dungeon-HP in Profil-Embeds.
"""

from __future__ import annotations

from database.database import Database
from database.models import PlayerEconomyRecord
from utils.dungeons import apply_hp_regen, player_hp_max


async def get_profile_economy(
    db: Database,
    guild_id: int,
    user_id: int,
    player_level: int,
) -> PlayerEconomyRecord:
    """Lädt Economy-Daten inkl. HP-Regen für Profil-Anzeige."""
    economy = await db.get_player_economy(guild_id, user_id)
    hp_max = player_hp_max(player_level)
    return apply_hp_regen(economy, hp_max)


def format_gold_line(economy: PlayerEconomyRecord) -> str:
    """Gold-Zeile für Embeds."""
    return f"**{economy.gold:,}** 🪙"


def format_dungeon_hp_line(economy: PlayerEconomyRecord, hp_max: int) -> str:
    """Dungeon-HP-Zeile für Embeds."""
    from utils.dungeon_embeds import format_hp_bar

    return format_hp_bar(economy.player_hp, hp_max)
