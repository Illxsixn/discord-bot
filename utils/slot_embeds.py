"""
Slot-Maschinen-Embeds.
"""

from __future__ import annotations

from utils.embeds import apply_brand_footer, artwork_embed
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
    title = "Gewonnen!" if won is True else "Slot-Maschine"

    if reels:
        body = format_reels(reels)
        if result_line:
            body += f"\n{result_line}"
    else:
        body = (
            "Setze deinen **Einsatz** und drücke **Drehen**!\n\n"
            f"{payout_table_text()}"
        )

    status = "Jackpot!" if won is True else ("Break-even" if won is None else "Kein Treffer")

    embed = artwork_embed(
        title,
        body,
        fields=[
            ("Einsatz", f"**{bet:,}** 🪙", True),
            ("Dein Gold", f"**{gold:,}** 🪙", True),
            ("Status", status, True),
        ],
    )
    apply_brand_footer(embed, prefix="Wähle Einsatz unten · /zombies & Spiele bringen Gold")
    return embed
