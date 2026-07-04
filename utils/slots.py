"""
Slot-Maschine: Symbole, Spin-Logik und Auszahlung.

Auszahlungsquote (RTP) ist auf ca. 75 % kalibriert (Spielothek-Niveau).
Drei unabhängige Walzen — keine künstlich erzwungenen Treffer.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from config import Config

# (Emoji, Gewicht, 3×-Multiplikator) — seltene Symbole stark reduziert
_SYMBOLS: tuple[tuple[str, int, int], ...] = (
    ("🍒", 44, 4),
    ("🍋", 29, 6),
    ("🍊", 11, 8),
    ("🍇", 9, 12),
    ("🔔", 3, 20),
    ("💎", 2, 40),
    ("7️⃣", 1, 100),
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


def random_reel_display() -> tuple[str, str, str]:
    """Zufällige Walzen nur für Spin-Animation (ohne Gewinnlogik)."""
    return spin_reels()


def spin_reels() -> tuple[str, str, str]:
    """Dreht drei unabhängige Walzen."""
    return (_pick_symbol(), _pick_symbol(), _pick_symbol())


def _pair_payout(bet: int) -> int:
    """Paar-Gewinn skaliert linear mit dem Einsatz (gleiche RTP für alle Einsätze)."""
    units = bet // Config.SLOT_BET_UNIT
    return max(1, units * Config.SLOT_PAIR_PAYOUT_PER_5_GOLD)


def pair_payout_percent() -> int:
    """Anzeige-Prozentsatz für Zwei-gleiche-Auszahlung."""
    return int(
        Config.SLOT_PAIR_PAYOUT_PER_5_GOLD
        / Config.SLOT_BET_UNIT
        * 100
    )


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
        if mult >= Config.SLOT_JACKPOT_MIN_MULTIPLIER:
            msg = f"**JACKPOT!** Drei {a} — **{mult}×** Einsatz!"
            return SpinResult(reels, payout, msg, jackpot=True)
        return SpinResult(reels, payout, f"Drei {a}! **{mult}×** — du gewinnst **{payout:,}** 🪙")

    if a == b or b == c or a == c:
        payout = _pair_payout(bet)
        pct = pair_payout_percent()
        return SpinResult(
            reels,
            payout,
            f"Zwei gleiche — **{pct} %** Einsatz zurück: **+{payout:,}** 🪙",
        )

    return SpinResult(reels, 0, "Kein Treffer — vielleicht beim nächsten Mal!")


def payout_table_text() -> str:
    """Kompakte Gewinntabelle."""
    lines = [f"{emoji} {emoji} {emoji} → **{mult}×**" for emoji, _, mult in _SYMBOLS]
    pct = pair_payout_percent()
    lines.append(f"Zwei gleiche → **{pct} %** des Einsatzes zurück")
    lines.append(f"Auszahlungsquote max. **{int(Config.SLOT_TARGET_RTP * 100)} %** (Spielothek)")
    return "\n".join(lines)


def simulate_rtp(*, spins: int = 200_000, bet: int = 10, seed: int = 42) -> float:
    """Monte-Carlo-RTP für Tests und Balancing."""
    rng = random.Random(seed)
    total_payout = 0
    for _ in range(spins):
        reels = (
            rng.choices(_EMOJIS, weights=_WEIGHTS, k=1)[0],
            rng.choices(_EMOJIS, weights=_WEIGHTS, k=1)[0],
            rng.choices(_EMOJIS, weights=_WEIGHTS, k=1)[0],
        )
        total_payout += resolve_spin(reels, bet).payout
    return total_payout / (spins * bet)
