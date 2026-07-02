"""
Slot-Maschinen-Embeds.
"""

from __future__ import annotations

import discord

from config import Config
from utils.embeds import apply_brand_footer
from utils.slots import format_reels, payout_table_text


def build_slots_embed(
    *,
    gold: int,
    bet: int,
    reels: tuple[str, str, str] | None = None,
    result_line: str | None = None,
    won: bool | None = None,
) -> discord.Embed:
    """Slot-Maschinen-Embed mit Walzen und Einsatz."""
    if won is True:
        color = Config.COLOR_SUCCESS
        title = "🎰 Gewonnen!"
    elif won is False:
        color = Config.COLOR_WARNING
        title = "🎰 Slot-Maschine"
    else:
        color = Config.COLOR_INFO
        title = "🎰 Slot-Maschine"

    if reels:
        body = format_reels(reels)
        if result_line:
            body += f"\n{result_line}"
    else:
        body = (
            "Setze deinen **Einsatz** und drücke **Drehen**!\n\n"
            f"{payout_table_text()}"
        )

    embed = discord.Embed(
        title=title,
        description=body,
        color=color,
    )
    embed.add_field(name="Einsatz", value=f"**{bet:,}** 🪙", inline=True)
    embed.add_field(name="Dein Gold", value=f"**{gold:,}** 🪙", inline=True)
    embed.set_footer(text="Wähle Einsatz unten · Dungeons & Spiele bringen Gold")
    apply_brand_footer(embed)
    embed.set_image(url="https://media.tenor.com/m/koF9C6Zc0pAAAAAd/coins.gif")
    return embed
