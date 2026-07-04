"""
Slot-Maschinen-Embeds.
"""

from __future__ import annotations

import discord

from utils.embeds import artwork_embed, spaced_lines
from utils.slots import format_reels, payout_table_text, slot_symbols_preview


def format_reel_strip(
    reels: tuple[str, str, str],
    *,
    won: bool = False,
) -> str:
    """Horizontale Walzenzeile — ohne Fettdruck (Emojis bleiben sichtbar)."""
    line = format_reels(reels)
    if won:
        return f"★  {line}  ★"
    return f"▸  {line}  ◂"


def format_idle_reel_strip() -> str:
    """Vorschau mit echten Symbolen vor dem ersten Spin."""
    return format_reel_strip(slot_symbols_preview())


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
    """Slot-Maschinen-Embed mit Walzen-Streifen und Einsatz."""
    stats = _stats_line(bet=bet, gold=gold)
    if reels is None:
        reel_line = format_idle_reel_strip()
    else:
        reel_line = format_reel_strip(reels, won=won is True)

    if spinning:
        reel_line = f"⏳  {format_reels(reels) if reels else '···   ···   ···'}  ⏳"

    parts = [stats, reel_line]
    if result_line:
        parts.append(result_line)
    parts.append(payout_table_text())
    description = spaced_lines(*parts)
    footer = "Wähle Einsatz unten · /zombies & Spiele bringen Gold"

    if mega_jackpot:
        return artwork_embed("🎰 MEGA-JACKPOT!", description, footer_prefix=footer)
    if jackpot:
        return artwork_embed("🎰 Jackpot!", description, footer_prefix=footer)
    if won is True:
        return artwork_embed("🎰 Gewonnen!", description, footer_prefix=footer)
    return artwork_embed("🎰 Gold Slots", description, footer_prefix=footer)
