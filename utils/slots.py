"""
Slot-Maschine: Symbole, Spin-Logik und Auszahlung.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from config import Config

# (Emoji, Gewicht, 3×-Multiplikator)
_SYMBOLS: tuple[tuple[str, int, int], ...] = (
    ("🍒", 28, 4),
    ("🍋", 24, 6),
    ("🍊", 20, 8),
    ("🍇", 14, 12),
    ("🔔", 9, 20),
    ("💎", 4, 40),
    ("7️⃣", 1, 100),
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


def _pick_symbol() -> str:
    return random.choices(_EMOJIS, weights=_WEIGHTS, k=1)[0]


def _pick_other_symbol(exclude: str) -> str:
    pool = [emoji for emoji in _EMOJIS if emoji != exclude] or _EMOJIS
    weights = [_WEIGHTS[_EMOJIS.index(emoji)] for emoji in pool]
    return random.choices(pool, weights=weights, k=1)[0]


def spin_reels() -> tuple[str, str, str]:
    """
    Dreht drei Walzen mit erhöhter Trefferquote.

    ~10 % Dreier · ~28 % Doppel · sonst unabhängiger Spin.
    """
    roll = random.random()
    symbol = _pick_symbol()

    if roll < Config.SLOT_TRIPLE_CHANCE:
        return (symbol, symbol, symbol)

    if roll < Config.SLOT_TRIPLE_CHANCE + Config.SLOT_DOUBLE_CHANCE:
        other = _pick_other_symbol(symbol)
        patterns = (
            (symbol, symbol, other),
            (symbol, other, symbol),
            (other, symbol, symbol),
        )
        return random.choice(patterns)

    return tuple(random.choices(_EMOJIS, weights=_WEIGHTS, k=3))  # type: ignore[return-value]


def format_reels(reels: tuple[str, str, str]) -> str:
    """Kompakte Walzen-Zeile (ohne Codeblock — Discord-Emoji-sicher)."""
    return " · ".join(reels)


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
