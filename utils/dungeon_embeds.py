"""
Dungeon-Embeds: Texte, GIFs und HP-Anzeige.
"""

from __future__ import annotations

import discord

from config import Config
from database.models import DungeonRunRecord, DungeonRunStatus, PetRecord
from utils.dungeons import event_preview
from utils.embeds import info_embed
from utils.levels import progress_bar

# Öffentliche GIF-URLs (Discord-kompatibel, kein Upload nötig)
EVENT_GIFS: dict[str, str] = {
    "fight": "https://media.tenor.com/m/ZKbLlBdhGVAAAAAd/fighting.gif",
    "trap": "https://media.tenor.com/m/oLFaW5eD9yQAAAAd/trap-door.gif",
    "treasure": "https://media.tenor.com/m/x4dG6fXLgN0AAAAd/treasure-chest.gif",
    "fountain": "https://media.tenor.com/m/8R2HfbzJAAAAAAd/water.gif",
    "gold": "https://media.tenor.com/m/koF9C6Zc0pAAAAAd/coins.gif",
    "pet_xp": "https://media.tenor.com/m/3ov6Q2xXyQAAAAAd/sparkle.gif",
}

START_GIF = "https://media.tenor.com/m/7AUpst1S8xAAAAAd/dungeon.gif"
COMPLETE_GIF = "https://media.tenor.com/m/x4dG6fXLgN0AAAAd/treasure-chest.gif"
FAIL_GIF = "https://media.tenor.com/m/WM7Oe0s02AAAAAd/tired.gif"


def format_hp_bar(current: int, maximum: int) -> str:
    """HP mit Mini-Balken."""
    if maximum <= 0:
        return f"**{current}** HP"
    pct = min(int((current / maximum) * 100), 100)
    return f"`{progress_bar(pct, 8)}` **{current}** / **{maximum}**"


def _apply_gif(embed: discord.Embed, url: str | None) -> None:
    if url:
        embed.set_image(url=url)


def build_start_embed(
    run: DungeonRunRecord,
    pet: PetRecord,
    *,
    title: str,
    description: str,
) -> discord.Embed:
    embed = info_embed(title, description)
    embed.add_field(name="❤️ Du", value=format_hp_bar(run.player_hp, run.player_hp_max), inline=True)
    embed.add_field(name=f"🐾 {pet.name}", value=format_hp_bar(run.pet_hp, run.pet_hp_max), inline=True)
    embed.add_field(name="🪙 Session", value=f"**{run.session_gold}**", inline=True)
    embed.set_footer(text=f"{run.total_rooms} Räume · Klicke Weiter zum Betreten")
    _apply_gif(embed, EVENT_GIFS.get(run.events[0]) or START_GIF)
    return embed


def build_room_result_embed(
    run: DungeonRunRecord,
    pet: PetRecord,
    outcome_text: str,
    *,
    last_event: str,
) -> discord.Embed:
    """Embed nach einem abgeschlossenen Raum."""
    embed = info_embed(
        f"Raum {run.rooms_cleared}/{run.total_rooms}",
        outcome_text,
    )
    embed.add_field(name="❤️ Du", value=format_hp_bar(run.player_hp, run.player_hp_max), inline=True)
    embed.add_field(name=f"🐾 {pet.name}", value=format_hp_bar(run.pet_hp, run.pet_hp_max), inline=True)
    embed.add_field(name="🪙 Session", value=f"**{run.session_gold}**", inline=True)

    if run.current_room < run.total_rooms:
        next_title, next_desc = event_preview(run.events[run.current_room], run.current_room, run.total_rooms)
        embed.add_field(name="👀 Als Nächstes", value=f"{next_title}\n_{next_desc}_", inline=False)
        embed.set_footer(text="Klicke Weiter für den nächsten Raum")
    else:
        embed.set_footer(text="Fast geschafft …")
    _apply_gif(embed, EVENT_GIFS.get(last_event, START_GIF))
    return embed


def build_finished_embed(
    run: DungeonRunRecord,
    pet: PetRecord,
    outcome_text: str,
    *,
    gold_received: int,
    completed: bool,
) -> discord.Embed:
    if completed:
        embed = discord.Embed(
            title="🎉 Dungeon geschafft!",
            description=outcome_text,
            color=Config.COLOR_SUCCESS,
        )
        embed.add_field(name="Gold erhalten", value=f"**+{gold_received:,}** 🪙", inline=False)
        _apply_gif(embed, COMPLETE_GIF)
    else:
        embed = discord.Embed(
            title="😮‍💨 Dungeon beendet",
            description=outcome_text,
            color=Config.COLOR_WARNING,
        )
        if gold_received:
            embed.add_field(name="Gold (Anteil)", value=f"**+{gold_received:,}** 🪙", inline=False)
        _apply_gif(embed, FAIL_GIF)

    embed.add_field(name="🐾 Pet", value=f"**{pet.name}**", inline=True)
    embed.add_field(name="Räume", value=f"**{run.rooms_cleared}** / **{run.total_rooms}**", inline=True)
    embed.set_footer(text="Kein Pet-Tod — bei Erschöpfung kurz `/dungeon status` checken")
    return embed


def build_resume_embed(run: DungeonRunRecord, pet: PetRecord) -> discord.Embed:
    title, desc = event_preview(run.events[run.current_room], run.current_room, run.total_rooms)
    embed = info_embed(
        "Dungeon läuft",
        f"{desc}\n\nDu hast noch einen aktiven Lauf — klicke **Weiter**.",
    )
    embed.add_field(name="❤️ Du", value=format_hp_bar(run.player_hp, run.player_hp_max), inline=True)
    embed.add_field(name=f"🐾 {pet.name}", value=format_hp_bar(run.pet_hp, run.pet_hp_max), inline=True)
    _apply_gif(embed, EVENT_GIFS.get(run.events[run.current_room]))
    return embed
