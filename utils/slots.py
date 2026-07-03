"""
Slot-Maschine: Symbole, Spin-Logik und Auszahlung.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

# (Emoji, Gewicht, 3×-Multiplikator)
_SYMBOLS: tuple[tuple[str, int, int], ...] = (
    ("🍒", 28, 2),
    ("🍋", 24, 3),
    ("🍊", 20, 4),
    ("🍇", 14, 6),
    ("🔔", 9, 10),
    ("💎", 4, 20),
    ("7️⃣", 1, 50),
)

_WEIGHTS: list[int] = [s[1] for s in _SYMBOLS]
_EMOJIS: list[str] = [s[0] for s in _SYMBOLS]
_PAYOUTS: dict[str, int] = {s[0]: s[2] for s in _SYMBOLS}


@dataclass
class SpinResult:
    """Ergebnis eines Spins."""

    reels: tuple[str, str, str]
    payout: int
    message: str
    jackpot: bool = False


def spin_reels() -> tuple[str, str, str]:
    """Dreht drei Walzen (unabhängig gewichtet)."""
    return tuple(random.choices(_EMOJIS, weights=_WEIGHTS, k=3))  # type: ignore[return-value]


def format_reels(reels: tuple[str, str, str]) -> str:
    """Walzen-Anzeige für Embeds (Emoji-getrennt, ohne ASCII-Rahmen)."""
    a, b, c = reels
    return f"**{a}** · **{b}** · **{c}**"


def resolve_spin(reels: tuple[str, str, str], bet: int) -> SpinResult:
    """Berechnet Auszahlung für drei Walzen."""
    a, b, c = reels
    if a == b == c:
        mult = _PAYOUTS[a]
        payout = bet * mult
        if mult >= 20:
            msg = f"**JACKPOT!** Drei {a} — **{mult}×** Einsatz!"
            return SpinResult(reels, payout, msg, jackpot=mult >= 20)
        return SpinResult(reels, payout, f"Drei {a}! **{mult}×** — du gewinnst **{payout:,}** 🪙")

    if a == b or b == c or a == c:
        payout = max(1, bet // 2)
        return SpinResult(reels, payout, f"Zwei gleiche — kleiner Trost: **+{payout:,}** 🪙")

    return SpinResult(reels, 0, "Kein Treffer — vielleicht beim nächsten Mal!")


def payout_table_text() -> str:
    """Kompakte Gewinntabelle."""
    lines = [f"{emoji} {emoji} {emoji} → **{mult}×**" for emoji, _, mult in _SYMBOLS]
    lines.append(f"Zwei gleiche → **50 %** des Einsatzes zurück")
    return "\n".join(lines)
