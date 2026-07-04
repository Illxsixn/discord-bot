"""
Slot-Maschinen-Embeds.
"""

from __future__ import annotations

import discord

from config import Config
from utils.embeds import apply_brand_footer, artwork_embed, spaced_lines, success_embed
from utils.slots import payout_table_text


def build_slots_embed(
    *,
    gold: int,
    bet: int,
    reels: tuple[str, str, str] | None = None,
    result_line: str | None = None,
    won: bool | None = None,
    jackpot: bool = False,
) -> discord.Embed:
    """Slot-Maschinen-Embed mit Walzen und Einsatz."""
    if reels:
        description = result_line or " "
    else:
        description = spaced_lines(
            "Setze deinen **Einsatz** und drücke **Drehen**!",
            payout_table_text(),
        )

    fields: list[tuple[str, str, bool]] = []
    if reels:
        a, b, c = reels
        fields.extend(
            [
                ("Walze 1", a, True),
                ("Walze 2", b, True),
                ("Walze 3", c, True),
            ]
        )
    fields.extend(
        [
            ("Einsatz", f"**{bet:,}** 🪙", True),
            ("Dein Gold", f"**{gold:,}** 🪙", True),
        ]
    )

    if jackpot:
        embed = success_embed("🎰 MEGA-JACKPOT!", description, fields=fields)
    elif won is True:
        embed = success_embed("🎰 Gewonnen!", description, fields=fields)
    else:
        embed = artwork_embed("🎰 Slot-Maschine", description, fields=fields)

    apply_brand_footer(embed, prefix="Wähle Einsatz unten · /zombies & Spiele bringen Gold")
    embed.set_image(url="https://media.tenor.com/m/koF9C6Zc0pAAAAAd/coins.gif")
    return embed
