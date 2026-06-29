"""
Gemeinsame asyncio-Locks für Spielzüge (Race-Condition-Schutz).
"""

from __future__ import annotations

import asyncio
from collections import defaultdict

_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def game_lock(game_id: int) -> asyncio.Lock:
    """Gibt eine Lock-Instanz pro Spiel-ID zurück."""
    return _locks[game_id]
