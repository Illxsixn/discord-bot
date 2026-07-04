"""
Slot-Maschine: Symbole, Spin-Logik und Auszahlung.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from config import Config

# (Emoji, Gewicht, 3×-Multiplikator)
_SYMBOLS: tuple[tuple[str, int, int], ...] = (
    ("🍒", 26, 4),
    ("🍋", 22, 6),
    ("🍊", 18, 8),
    ("🍇", 14, 12),
    ("🔔", 10, 20),
    ("💎", 7, 40),
    ("7️⃣", 6, 100),
)

_WEIGHTS: list[int] = [s[1] for s in _SYMBOLS]
_EMOJIS: list[str] = [s[0] for s in _SYMBOLS]
_PAYOUTS: dict[str, int] = {s[0]: s[2] for s in _SYMBOLS}
MEGA_JACKPOT_SYMBOL = "7️⃣"


@dataclass
class SpinResult:
    """Ergebnis eines Spins."""

    reels: tuple[str, str, str]
    payout: int
    message: str
    jackpot: bool = False
    mega_jackpot: bool = False


def slot_symbols() -> tuple[str, ...]:
    """Alle Walzen-Symbole in Anzeige-Reihenfolge."""
    return _EMOJIS


def slot_symbols_preview() -> tuple[str, str, str]:
    """Standard-Vorschau vor dem ersten Spin."""
    return ("🍒", "🍋", "🍊")


def _pick_symbol() -> str:
    return random.choices(_EMOJIS, weights=_WEIGHTS, k=1)[0]


def _pick_other_symbol(exclude: str) -> str:
    pool = [emoji for emoji in _EMOJIS if emoji != exclude] or _EMOJIS
    weights = [_WEIGHTS[_EMOJIS.index(emoji)] for emoji in pool]
    return random.choices(pool, weights=weights, k=1)[0]


def random_reel_display() -> tuple[str, str, str]:
    """Zufällige Walzen nur für Spin-Animation (ohne Gewinnlogik)."""
    return tuple(random.choices(_EMOJIS, weights=_WEIGHTS, k=3))  # type: ignore[return-value]


def spin_reels() -> tuple[str, str, str]:
    """
    Dreht drei Walzen mit erhöhter Trefferquote.

    ~13 % Dreier · ~28 % Doppel · 1 % Mega-Jackpot (777) · sonst Zufall.
    """
    if random.random() < Config.SLOT_MEGA_JACKPOT_CHANCE:
        return (MEGA_JACKPOT_SYMBOL, MEGA_JACKPOT_SYMBOL, MEGA_JACKPOT_SYMBOL)

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
    """Kompakte Walzen-Zeile (ohne Markdown — Discord-Emoji-sicher)."""
    return "   ".join(reels)


def resolve_spin(reels: tuple[str, str, str], bet: int) -> SpinResult:
    """Berechnet Auszahlung für drei Walzen."""
    a, b, c = reels
    if a == b == c:
        mult = _PAYOUTS[a]
        payout = bet * mult
        mega = a == MEGA_JACKPOT_SYMBOL
        if mega:
            msg = f"**MEGA-JACKPOT!** Drei Siebenen — **{mult}×** Einsatz!"
            return SpinResult(reels, payout, msg, jackpot=True, mega_jackpot=True)
        if mult >= 20:
            msg = f"**JACKPOT!** Drei {a} — **{mult}×** Einsatz!"
            return SpinResult(reels, payout, msg, jackpot=True)
        return SpinResult(reels, payout, f"Drei {a}! **{mult}×** — du gewinnst **{payout:,}** 🪙")

    if a == b or b == c or a == c:
        payout = max(1, bet // 2)
        return SpinResult(reels, payout, f"Zwei gleiche — kleiner Trost: **+{payout:,}** 🪙")

    return SpinResult(reels, 0, "Kein Treffer — vielleicht beim nächsten Mal!")


def payout_table_text() -> str:
    """Kompakte Gewinntabelle."""
    lines = [f"{emoji} {emoji} {emoji} → **{mult}×**" for emoji, _, mult in _SYMBOLS]
    lines.append("Zwei gleiche → **50 %** des Einsatzes zurück")
    return "\n".join(lines)
