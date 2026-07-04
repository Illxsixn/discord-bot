"""
Einheitliche, übersichtliche Embeds für das Pet-System.

Layout: Titel · Beschreibung (Absätze) · Inline-Felder (3er-Reihen) · Marken-Footer.
Farbe: durchgehend dunkel-lila (COLOR_ARTWORK).
"""

from __future__ import annotations

import discord

from config import Config
from database.models import PetEvolutionStage, PetRarity, PetRecord
from utils.embeds import artwork_embed, split_embed_fields, spaced_lines
from utils.pets import (
    PET_SPECIES,
    PetSpeciesDefinition,
    evolution_display,
    get_species_by_name,
    mood_display,
    pet_birthday,
    rarity_display,
    pet_xp_boost_label,
    species_display_emoji,
    xp_progress,
)

RARITY_ORDER: tuple[PetRarity, ...] = (
    PetRarity.COMMON,
    PetRarity.UNCOMMON,
    PetRarity.RARE,
    PetRarity.EPIC,
    PetRarity.LEGENDARY,
)


def apply_pet_image_layout(
    embed: discord.Embed,
    *,
    attachment_filename: str,
) -> discord.Embed:
    """
    Großes Pet-Bild unten, dasselbe Pet klein oben rechts (Thumbnail).

    Nutzen, wenn ein Pet-Portrait als Anhang mitgesendet wird.
    """
    url = f"attachment://{attachment_filename}"
    embed.set_image(url=url)
    embed.set_thumbnail(url=url)
    return embed


def build_pet_info_embed(
    pet: PetRecord,
    member: discord.Member,
) -> discord.Embed:
    """Übersichtliches Profil des aktiven Pets."""
    species = get_species_by_name(pet.species)
    emoji = species_display_emoji(species, pet.evolution_stage)
    current, needed, percent = xp_progress(pet.xp, pet.level)
    rarity = rarity_display(species.rarity) if species else "—"
    xp_bonus = pet_xp_boost_label(pet.species) if species else "—"

    description = spaced_lines(
        f"**{evolution_display(pet.evolution_stage)}** — dein aktiver Begleiter.",
        f"Besitzer: {member.mention}",
        f"*{pet.catchphrase}*",
    )

    fields: list[tuple[str, str, bool]] = [
        ("Level", f"**{pet.level}**", True),
        ("XP gesamt", f"**{pet.xp:,}**", True),
        ("Fortschritt", f"**{percent} %**\n`{current:,}` / `{needed:,}`", True),
        ("Art", pet.species, True),
        ("Seltenheit", rarity, True),
        ("XP-Bonus", xp_bonus, True),
        ("Impuls", mood_display(pet.mood), True),
        ("Geburtstag", pet_birthday(pet.adoption_date), True),
        ("Interaktionen", f"**{pet.total_interactions:,}**", True),
    ]

    return artwork_embed(f"{emoji} {pet.name}", description=description, fields=fields)


def build_pet_duplicate_embed(
    member: discord.Member,
    species: PetSpeciesDefinition,
    *,
    pet_xp: int,
    player_xp: int,
) -> discord.Embed:
    """Embed wenn ein bereits besessenes Pet gezogen wurde."""
    emoji = species_display_emoji(species, PetEvolutionStage.BABY.value)
    return artwork_embed(
        f"🔄 Duplikat — {emoji} {species.name}",
        description=spaced_lines(
            f"{member.mention}, du hast **{species.name}** bereits in deiner Sammlung!",
            "Statt eines zweiten Exemplars erhältst du Ersatz-XP:",
        ),
        fields=[
            ("Pet-XP", f"**+{pet_xp}** 🐾", True),
            ("Spieler-XP", f"**+{player_xp}** 📈", True),
            ("Seltenheit", rarity_display(species.rarity), True),
        ],
    )


def build_pet_hatch_embed(
    member: discord.Member,
    pet: PetRecord,
    species: PetSpeciesDefinition,
    *,
    personality: str,
    mood: str,
    favorite: str,
    catchphrase: str,
) -> discord.Embed:
    """Embed nach dem Schlüpfen eines Eis."""
    emoji = species_display_emoji(species, pet.evolution_stage)
    status = "⭐ Aktives Pet" if pet.is_active else "📦 In Sammlung"

    return artwork_embed(
        f"🐣 Neues Pet — {emoji} {pet.name}",
        description=spaced_lines(
            f"{member.mention} hat ein neues Pet adoptiert!",
            f"**{species.name}** · {rarity_display(species.rarity)}",
            f"*{catchphrase}*",
        ),
        fields=[
            ("Status", status, True),
            ("Evolution", evolution_display(pet.evolution_stage), True),
            ("Impuls", mood_display(mood), True),
            ("Level", f"**{pet.level}**", True),
        ],
    )


def build_pet_collection_embed(owner_name: str, pets: list[PetRecord]) -> discord.Embed:
    """Sammlungsübersicht mit kompakten Einträgen."""
    active = next((pet for pet in pets if pet.is_active), None)
    active_line = "—"
    if active is not None:
        species = get_species_by_name(active.species)
        emoji = species_display_emoji(species, active.evolution_stage)
        active_line = f"{emoji} **{active.name}** · Lv. **{active.level}**"

    lines: list[str] = []
    for pet in pets:
        species = get_species_by_name(pet.species)
        emoji = species_display_emoji(species, pet.evolution_stage)
        star = "⭐ " if pet.is_active else ""
        rarity = rarity_display(species.rarity) if species else "—"
        lines.append(
            f"{star}{emoji} **{pet.name}** · Lv. **{pet.level}** · {rarity}"
        )

    return artwork_embed(
        f"🐾 Sammlung · {owner_name}",
        description=spaced_lines(
            f"**{len(pets)}** Pets gesammelt · ⭐ = aktiv",
            f"Aktives Pet: {active_line}",
        ),
        fields=split_embed_fields("Alle Pets", lines, joiner="\n"),
    )


def _dex_entry(species: PetSpeciesDefinition, discovered: bool) -> str:
    if discovered:
        return f"✅ {species.emoji} **{species.name}**"
    return "❓ ░░░ **???**"


def build_pet_dex_embed(discovered_names: set[str], *, owner_name: str | None = None) -> discord.Embed:
    """Sammlungsbuch aller Pet-Arten."""
    total = len(PET_SPECIES)
    found = sum(1 for species in PET_SPECIES if species.name in discovered_names)

    fields: list[tuple[str, str, bool]] = [
        ("Entdeckt", f"**{found}** / **{total}**", True),
        ("Gefunden", "✅ bekannt", True),
        ("Unbekannt", "❓ ???", True),
    ]

    for rarity in RARITY_ORDER:
        species_list = [species for species in PET_SPECIES if species.rarity == rarity]
        if not species_list:
            continue
        category_found = sum(1 for species in species_list if species.name in discovered_names)
        entries = [
            _dex_entry(species, species.name in discovered_names)
            for species in species_list
        ]
        fields.append(
            (
                f"{rarity_display(rarity)} ({category_found}/{len(species_list)})",
                "\n".join(entries),
                False,
            )
        )

    title = f"📖 Pet-Dex · {owner_name}" if owner_name else "📖 Pet-Dex"
    owner_line = f"Sammlung von **{owner_name}**" if owner_name else "Alle Pet-Arten im Überblick"

    return artwork_embed(
        title,
        description=spaced_lines(
            owner_line,
            "Entdecke alle Arten — gefundene Pets erscheinen mit Namen.",
        ),
        fields=fields,
    )


def build_pet_leaderboard_embed(
    guild_name: str,
    *,
    sort_label: str,
    lines: list[str],
) -> discord.Embed:
    """Server-Rangliste."""
    return artwork_embed(
        f"🏆 Pet-Rangliste · {guild_name}",
        description=spaced_lines(
            f"Sortierung: **{sort_label}**",
            "Die stärksten Begleiter auf diesem Server.",
        ),
        fields=split_embed_fields("Top Pets", lines) if lines else [("Top Pets", "—", False)],
    )


def _impulse_score_bar(score: int, total_rounds: int) -> str:
    filled = "🟩" * score
    empty = "⬜" * (total_rounds - score)
    return f"{filled}{empty}"


def build_pet_play_embed(
    pet: PetRecord,
    species: PetSpeciesDefinition | None,
    *,
    round_num: int = 1,
    total_rounds: int = 3,
    score: int = 0,
    feedback: str | None = None,
    xp_gain: int | None = None,
    xp_breakdown: str | None = None,
) -> discord.Embed:
    """Embed für das Impuls-Minispiel (/pet play)."""
    emoji = species_display_emoji(species, pet.evolution_stage)
    bar = _impulse_score_bar(score, total_rounds)
    rarity = rarity_display(species.rarity) if species else "—"

    description_parts = [
        f"*{pet.catchphrase}*",
        f"{bar} · Runde **{round_num}/{total_rounds}**",
    ]
    if feedback:
        description_parts.append(feedback)
    if xp_gain is not None:
        xp_line = f"**+{xp_gain} Pet-XP**"
        if xp_breakdown:
            xp_line += f" · {xp_breakdown}"
        description_parts.append(xp_line)
        description_parts.append(f"⏳ Nächstes Spiel in **{Config.PET_PLAY_COOLDOWN // 60} Min.**")
    else:
        description_parts.append("**Welchen Impuls zeigt dein Pet?**")

    fields: list[tuple[str, str, bool]] = [
        ("Level", f"**{pet.level}**", True),
        ("Evolution", evolution_display(pet.evolution_stage), True),
        ("Impuls", mood_display(pet.mood), True),
        ("Art", pet.species, True),
        ("Seltenheit", rarity, True),
        ("Score", f"**{score}** / **{total_rounds}**", True),
    ]

    return artwork_embed(
        f"{emoji} Impuls-Rush · {pet.name}",
        description=spaced_lines(*description_parts),
        fields=fields,
    )


def build_pet_display_embed(
    pet: PetRecord,
    member: discord.Member,
    *,
    portrait_label: str,
    attachment_filename: str | None = None,
) -> discord.Embed:
    """Embed für KI-Portraits — großes Bild unten, Pet klein oben rechts."""
    species = get_species_by_name(pet.species)
    emoji = species_display_emoji(species, pet.evolution_stage)
    rarity = rarity_display(species.rarity) if species else "—"

    embed = artwork_embed(
        f"🖼️ {emoji} {pet.name}",
        description=spaced_lines(
            f"{member.mention} zeigt sein aktives Pet.",
            portrait_label,
            f"*{pet.catchphrase}*",
        ),
        fields=[
            ("Level", f"**{pet.level}**", True),
            ("Evolution", evolution_display(pet.evolution_stage), True),
            ("Seltenheit", rarity, True),
            ("Impuls", mood_display(pet.mood), True),
            ("Art", pet.species, True),
        ],
    )

    if attachment_filename:
        apply_pet_image_layout(embed, attachment_filename=attachment_filename)

    return embed


def build_leaderboard_line(
    *,
    rank: int,
    pet: PetRecord,
    owner_name: str,
    medal_prefix: str,
) -> str:
    """Eine Zeile für die Pet-Rangliste."""
    species = get_species_by_name(pet.species)
    emoji = species_display_emoji(species, pet.evolution_stage)
    return (
        f"{medal_prefix} {emoji} **{pet.name}** · {owner_name}\n\n"
        f"Lv. **{pet.level}** · **{pet.xp:,}** XP\n"
        f"{evolution_display(pet.evolution_stage)} · **{pet.total_interactions}** Interaktionen"
    )
