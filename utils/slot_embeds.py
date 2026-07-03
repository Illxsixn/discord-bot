"""

Slot-Maschinen-Embeds.

"""



from __future__ import annotations



import discord



from config import Config

from utils.embeds import apply_brand_footer

from utils.slots import payout_table_text





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

    else:

        color = Config.COLOR_ARTWORK

        title = "🎰 Slot-Maschine"



    if reels:

        description = result_line or " "

    else:

        description = (

            "Setze deinen **Einsatz** und drücke **Drehen**!\n\n"

            f"{payout_table_text()}"

        )



    embed = discord.Embed(

        title=title,

        description=description,

        color=color,

    )



    if reels:

        a, b, c = reels

        # Drei Inline-Felder — Emoji-Breite in Codeblöcken bricht sonst das Layout.

        embed.add_field(name="Walze 1", value=a, inline=True)

        embed.add_field(name="Walze 2", value=b, inline=True)

        embed.add_field(name="Walze 3", value=c, inline=True)



    embed.add_field(name="Einsatz", value=f"**{bet:,}** 🪙", inline=True)

    embed.add_field(name="Dein Gold", value=f"**{gold:,}** 🪙", inline=True)

    apply_brand_footer(embed, prefix="Wähle Einsatz unten · /zombies & Spiele bringen Gold")

    embed.set_image(url="https://media.tenor.com/m/koF9C6Zc0pAAAAAd/coins.gif")

    return embed

