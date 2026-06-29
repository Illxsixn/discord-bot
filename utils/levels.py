"""
Level-System Hilfsfunktionen für XP-Berechnung und Fortschritt.
"""

from __future__ import annotations


def xp_required_for_level(level: int) -> int:
    """
    Gesamt-XP, die für ein bestimmtes Level benötigt wird.

    Args:
        level: Ziel-Level (mindestens 1).

    Returns:
        Benötigte Gesamt-XP.
    """
    if level <= 1:
        return 0
    return 100 * (level - 1) ** 2


def level_from_xp(xp: int) -> int:
    """
    Ermittelt das Level anhand der Gesamt-XP.

    Args:
        xp: Gesammelte Erfahrungspunkte.

    Returns:
        Aktuelles Level.
    """
    level = 1
    while xp >= xp_required_for_level(level + 1):
        level += 1
    return level


def xp_progress(xp: int, level: int) -> tuple[int, int, int]:
    """
    Berechnet XP-Fortschritt im aktuellen Level.

    Args:
        xp: Gesamt-XP.
        level: Aktuelles Level.

    Returns:
        Tuple (xp_im_level, xp_benoetigt_fuer_naechstes, prozent).
    """
    current_floor = xp_required_for_level(level)
    next_floor = xp_required_for_level(level + 1)
    needed = max(next_floor - current_floor, 1)
    current = max(xp - current_floor, 0)
    percent = min(int((current / needed) * 100), 100)
    return current, needed, percent


def progress_bar(percent: int, length: int = 12) -> str:
    """Erstellt einen einfachen Text-Fortschrittsbalken."""
    filled = int((percent / 100) * length)
    return "█" * filled + "░" * (length - filled)
