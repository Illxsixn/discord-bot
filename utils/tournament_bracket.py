"""
Hilfsfunktionen für Turnier-Paarungen und Map-Verteilung.
"""

from __future__ import annotations

import logging
import random
from typing import Sequence

import aiohttp

logger = logging.getLogger(__name__)


async def fetch_shuffle_seed() -> int | None:
    """
    Versucht einen Zufallswert von random.org zu holen.

    Returns:
        Seed oder None bei Fehler.
    """
    url = (
        "https://www.random.org/integers/"
        "?num=1&min=1&max=1000000&col=1&base=10&format=plain&rnd=new"
    )
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    text = (await resp.text()).strip()
                    return int(text)
    except (aiohttp.ClientError, ValueError, TimeoutError):
        logger.debug("Externe Zufalls-API nicht erreichbar, lokaler Fallback.")
    return None


def shuffle_team_ids(team_ids: Sequence[int], *, seed: int | None = None) -> list[int]:
    """Mischt Team-IDs zufällig (optional mit Seed von externer API)."""
    shuffled = list(team_ids)
    rng = random.Random(seed) if seed is not None else random
    rng.shuffle(shuffled)
    return shuffled


def create_pairings(team_ids: Sequence[int]) -> list[tuple[int | None, int | None]]:
    """
    Erzeugt Paarungen aus Team-IDs.

    Bei ungerader Anzahl erhält das letzte Team ein Freilos (team2 = None).
    """
    shuffled = shuffle_team_ids(team_ids)
    pairings: list[tuple[int | None, int | None]] = []
    index = 0
    while index < len(shuffled):
        if index + 1 < len(shuffled):
            pairings.append((shuffled[index], shuffled[index + 1]))
            index += 2
        else:
            pairings.append((shuffled[index], None))
            index += 1
    return pairings


async def create_round_one_pairings(
    team_ids: Sequence[int],
) -> list[tuple[int | None, int | None]]:
    """Erzeugt Runde-1-Paarungen mit optionalem API-Seed."""
    seed = await fetch_shuffle_seed()
    shuffled = shuffle_team_ids(team_ids, seed=seed)
    pairings: list[tuple[int | None, int | None]] = []
    index = 0
    while index < len(shuffled):
        if index + 1 < len(shuffled):
            pairings.append((shuffled[index], shuffled[index + 1]))
            index += 2
        else:
            pairings.append((shuffled[index], None))
            index += 1
    return pairings


def distribute_maps(maps: Sequence[str], match_count: int) -> list[str]:
    """Verteilt Maps gleichmäßig (Round-Robin) auf Matches."""
    if match_count <= 0:
        return []
    if not maps:
        return [""] * match_count
    return [maps[i % len(maps)] for i in range(match_count)]
