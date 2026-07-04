"""
Slot-Maschinen-Embeds.
"""

from __future__ import annotations

import discord

from utils.embeds import apply_brand_footer, artwork_embed, spaced_lines, success_embed
from utils.slots import payout_table_text

_INVISIBLE_FIELD = "\u200b"
_REEL_GAP = "  "


def _reel_window(symbol: str) -> str:
    return f"**[ {symbol} ]**"


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
) -> discord.Embed:
    """Slot-Maschinen-Embed mit Walzen-Streifen und Einsatz."""
    stats = _stats_line(bet=bet, gold=gold)
    if reels is None:
        description = spaced_lines(
            stats,
            "Wähle deinen **Einsatz** und drücke **Drehen**!",
            payout_table_text(),
        )
    else:
        description = spaced_lines(stats, result_line or " ")

    strip = format_reel_strip(reels, won=won is True) if reels else format_idle_reel_strip()
    fields: list[tuple[str, str, bool]] = [(_INVISIBLE_FIELD, strip, False)]

    if jackpot:
        embed = success_embed("🎰 MEGA-JACKPOT!", description, fields=fields)
    elif won is True:
        embed = success_embed("🎰 Gewonnen!", description, fields=fields)
    else:
        embed = artwork_embed("🎰 Gold Slots", description, fields=fields)

    apply_brand_footer(embed, prefix="Wähle Einsatz unten · /zombies & Spiele bringen Gold")
    return embed
