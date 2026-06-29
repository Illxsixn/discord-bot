"""
Impuls-Minispiel für /pet play.
"""

from __future__ import annotations

import random

from config import Config

# (id, emoji, Kurzlabel) — genau 3 Impulse pro Runde
PET_IMPULSES: tuple[tuple[str, str, str], ...] = (
    ("focus", "🎯", "Fokus"),
    ("energy", "⚡", "Power"),
    ("luck", "🍀", "Glück"),
)

PET_PLAY_ROUNDS = 3


def random_impulse_id() -> str:
    """Zufälliger Impuls für eine Runde."""
    return random.choice(PET_IMPULSES)[0]


def impulse_by_id(impulse_id: str) -> tuple[str, str, str] | None:
    """Impuls-Definition anhand der ID."""
    for impulse in PET_IMPULSES:
        if impulse[0] == impulse_id:
            return impulse
    return None


def pet_play_xp_for_score(score: int) -> tuple[int, int, int]:
    """
    Pet-XP für Impuls-Rush: Grund-XP + Bonus pro Treffer.

    Returns:
        (base_xp, hit_bonus, total_xp) vor Seltenheits-Bonus.
    """
    base_xp = random.randint(Config.PET_XP_PLAY_BASE_MIN, Config.PET_XP_PLAY_BASE_MAX)
    hit_bonus = score * Config.PET_XP_PLAY_HIT_BONUS
    return base_xp, hit_bonus, base_xp + hit_bonus
