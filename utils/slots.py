"""
Slot-Maschine: Symbole, Spin-Logik und Auszahlung.

Auszahlungsquote (RTP) ist auf ca. 75 % kalibriert (Spielothek-Niveau).
10 % der Spins sind garantierte Jackpot-Dreier (🍒/🍋/🍊/🍇); übrige Spins
ohne Dreier — Paar-Gewinne nur auf den restlichen 90 %.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from config import Config

# (Emoji, Gewicht, 3×-Multiplikator) — Normalwalzen (ohne erzwungene Jackpots)
_SYMBOLS: tuple[tuple[str, int, int], ...] = (
    ("🍒", 8, 4),
    ("🍋", 5, 6),
    ("🍊", 3, 8),
    ("🍇", 2, 12),
    ("🔔", 2, 20),
    ("💎", 1, 40),
    ("7️⃣", 1, 100),
)

# Gewichtete Jackpot-Dreier bei SLOT_JACKPOT_CHANCE (ohne 7️⃣ — RTP sonst zu hoch)
_JACKPOT_POOL: tuple[tuple[str, int], ...] = (
    ("🍒", 45),
    ("🍋", 35),
    ("🍊", 15),
    ("🍇", 5),
)

_WEIGHTS: list[int] = [s[1] for s in _SYMBOLS]
_EMOJIS: list[str] = [s[0] for s in _SYMBOLS]
_PAYOUTS: dict[str, int] = {s[0]: s[2] for s in _SYMBOLS}
_JACKPOT_EMOJIS: list[str] = [s[0] for s in _JACKPOT_POOL]
_JACKPOT_WEIGHTS: list[int] = [s[1] for s in _JACKPOT_POOL]
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


def _pick_jackpot_symbol() -> str:
    return random.choices(_JACKPOT_EMOJIS, weights=_JACKPOT_WEIGHTS, k=1)[0]


def _is_triple(reels: tuple[str, str, str]) -> bool:
    return reels[0] == reels[1] == reels[2]


def random_reel_display() -> tuple[str, str, str]:
    """Zufällige Walzen nur für Spin-Animation (ohne Gewinnlogik)."""
    return (_pick_symbol(), _pick_symbol(), _pick_symbol())


def spin_reels() -> tuple[tuple[str, str, str], bool]:
    """
    Dreht drei Walzen.

    Returns:
        (Walzen, jackpot_spin) — bei jackpot_spin=True ist es ein Jackpot-Dreier.
    """
    if random.random() < Config.SLOT_JACKPOT_CHANCE:
        symbol = _pick_jackpot_symbol()
        return (symbol, symbol, symbol), True

    while True:
        reels = (_pick_symbol(), _pick_symbol(), _pick_symbol())
        if not _is_triple(reels):
            return reels, False


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


def resolve_spin(
    reels: tuple[str, str, str],
    bet: int,
    *,
    jackpot_spin: bool = False,
) -> SpinResult:
    """Berechnet Auszahlung für drei Walzen."""
    a, b, c = reels
    if a == b == c:
        mult = _PAYOUTS[a]
        payout = bet * mult
        mega = a == MEGA_JACKPOT_SYMBOL
        is_jackpot = jackpot_spin or mult >= Config.SLOT_JACKPOT_MIN_MULTIPLIER
        if mega:
            msg = f"**MEGA-JACKPOT!** Drei Siebenen — **{mult}×** Einsatz!"
            return SpinResult(reels, payout, msg, jackpot=True, mega_jackpot=True)
        if is_jackpot:
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
    lines.append(
        f"Jackpot-Chance: **{int(Config.SLOT_JACKPOT_CHANCE * 100)} %** "
        f"(Dreier aus 🍒 · 🍋 · 🍊 · 🍇)"
    )
    lines.append(f"Auszahlungsquote max. **{int(Config.SLOT_TARGET_RTP * 100)} %** (Spielothek)")
    return "\n".join(lines)


def simulate_rtp(*, spins: int = 200_000, bet: int = 10, seed: int = 42) -> float:
    """Monte-Carlo-RTP für Tests und Balancing."""
    rng = random.Random(seed)
    total_payout = 0
    for _ in range(spins):
        reels, jackpot_spin = _spin_reels_seeded(rng)
        total_payout += resolve_spin(reels, bet, jackpot_spin=jackpot_spin).payout
    return total_payout / (spins * bet)


def _spin_reels_seeded(rng: random.Random) -> tuple[tuple[str, str, str], bool]:
    """Wie spin_reels, aber mit vorgegebenem RNG (für Simulationen)."""
    if rng.random() < Config.SLOT_JACKPOT_CHANCE:
        symbol = rng.choices(_JACKPOT_EMOJIS, weights=_JACKPOT_WEIGHTS, k=1)[0]
        return (symbol, symbol, symbol), True
    while True:
        reels = (
            rng.choices(_EMOJIS, weights=_WEIGHTS, k=1)[0],
            rng.choices(_EMOJIS, weights=_WEIGHTS, k=1)[0],
            rng.choices(_EMOJIS, weights=_WEIGHTS, k=1)[0],
        )
        if not _is_triple(reels):
            return reels, False


def simulate_jackpot_rate(*, spins: int = 200_000, seed: int = 42) -> float:
    """Anteil der Spins mit Jackpot-Flag."""
    rng = random.Random(seed)
    jackpots = 0
    for _ in range(spins):
        reels, jackpot_spin = _spin_reels_seeded(rng)
        if resolve_spin(reels, 10, jackpot_spin=jackpot_spin).jackpot:
            jackpots += 1
    return jackpots / spins
