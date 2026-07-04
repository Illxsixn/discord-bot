"""
Gemeinsame asyncio-Locks für Spielzüge (Race-Condition-Schutz).

Locks sind nach Scope getrennt (z. B. zombie vs. slots), damit parallele
Spiele sich nicht gegenseitig blockieren.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict

_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def game_lock(scope: str, game_id: int) -> asyncio.Lock:
    """Gibt eine Lock-Instanz pro Scope und Spiel-ID zurück."""
    return _locks[f"{scope}:{game_id}"]
