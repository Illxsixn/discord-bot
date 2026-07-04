"""
Slot-Maschinen-Embeds.
"""

from __future__ import annotations

import discord

from config import Config
from utils.embeds import apply_brand_footer
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
) -> discord.Embed:
    """Slot-Maschinen-Embed mit Walzen-Streifen und Einsatz."""
    if won is True:
        color = Config.COLOR_SUCCESS
        title = "🎰 Gewonnen!"
    else:
        color = Config.COLOR_ARTWORK
        title = "🎰 Gold Slots"

    description_parts = [_stats_line(bet=bet, gold=gold)]
    if reels is None:
        description_parts.extend(
            [
                "",
                "Wähle deinen **Einsatz** und drücke **Drehen**!",
                "",
                payout_table_text(),
            ]
        )

    embed = discord.Embed(
        title=title,
        description="\n".join(description_parts),
        color=color,
    )

    strip = format_reel_strip(reels, won=won is True) if reels else format_idle_reel_strip()
    embed.add_field(name=_INVISIBLE_FIELD, value=strip, inline=False)

    if reels and result_line:
        embed.add_field(name="Ergebnis", value=result_line, inline=False)

    apply_brand_footer(embed, prefix="Wähle Einsatz unten · /zombies & Spiele bringen Gold")
    return embed
