"""
Slot-Maschinen-Embeds.
"""

from __future__ import annotations

import discord

from utils.embeds import artwork_embed, spaced_lines
from utils.slots import payout_table_text

_INVISIBLE_FIELD = "\u200b"
_REEL_GAP = "  "


def _reel_window(symbol: str) -> str:
    """Einzelnes Walzenfenster — ohne Fettdruck (Emojis bleiben sichtbar)."""
    return f"[ {symbol} ]"


def format_reel_strip(
    reels: tuple[str, str, str],
    *,
    won: bool = False,
) -> str:
    """Horizontale Walzenzeile — Variante B (▸ [ 🍒 ]  [ 🍋 ]  [ 🍊 ] ◂)."""
    windows = _REEL_GAP.join(_reel_window(symbol) for symbol in reels)
    if won:
        return f"★ {windows} ★"
    return f"▸ {windows} ◂"


def format_idle_reel_strip() -> str:
    """Platzhalter vor dem ersten Spin."""
    windows = _REEL_GAP.join(_reel_window("🎰") for _ in range(3))
    return f"▸ {windows} ◂"


def format_spinning_reel_strip(reels: tuple[str, str, str] | None = None) -> str:
    """Walzen während der Dreh-Animation."""
    if reels is None:
        windows = _REEL_GAP.join(_reel_window("·") for _ in range(3))
    else:
        windows = _REEL_GAP.join(_reel_window(symbol) for symbol in reels)
    return f"⏳ {windows} ⏳"


def _stats_line(*, bet: int, gold: int) -> str:
    return f"🪙 Einsatz **{bet:,}** · Kontostand **{gold:,}**"


def build_slots_embed(
    *,
    gold: int,
    bet: int,
    reels: tuple[str, str, str] | None = None,
    result_line: str | None = None,
    won: bool | None = None,
    jackpot: bool = False,
    mega_jackpot: bool = False,
    spinning: bool = False,
) -> discord.Embed:
    """Slot-Maschinen-Embed mit Walzen-Streifen, Ergebnis und optionaler Tabelle."""
    description_parts = [_stats_line(bet=bet, gold=gold)]
    if reels is None and not spinning:
        description_parts.extend(
            [
                "",
                "Wähle deinen **Einsatz** und drücke **Drehen**!",
                "",
                payout_table_text(),
            ]
        )

    description = spaced_lines(*description_parts)
    footer = "Wähle Einsatz unten · /zombies & Spiele bringen Gold"

    if spinning:
        strip = format_spinning_reel_strip(reels)
    elif reels is None:
        strip = format_idle_reel_strip()
    else:
        strip = format_reel_strip(reels, won=won is True)

    fields: list[tuple[str, str, bool]] = [(_INVISIBLE_FIELD, strip, False)]
    if reels is not None and result_line and not spinning:
        fields.append(("Ergebnis", result_line, False))

    if mega_jackpot:
        return artwork_embed(
            "🎰 MEGA-JACKPOT!",
            description,
            fields=fields,
            footer_prefix=footer,
        )
    if jackpot:
        return artwork_embed(
            "🎰 Jackpot!",
            description,
            fields=fields,
            footer_prefix=footer,
        )
    if won is True:
        return artwork_embed(
            "🎰 Gewonnen!",
            description,
            fields=fields,
            footer_prefix=footer,
        )
    return artwork_embed(
        "🎰 Gold Slots",
        description,
        fields=fields,
        footer_prefix=footer,
    )
