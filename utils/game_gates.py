"""
Spielmodus-Freischaltungen — Kopplung zwischen Features.
"""

from __future__ import annotations

from database.database import Database


async def is_zombie_mode_active(db: Database, guild_id: int) -> bool:
    """Zombie Survival ist aktiv, wenn das Level-System auf dem Server aktiv ist."""
    settings = await db.get_guild_settings(guild_id)
    return settings.levels_enabled
