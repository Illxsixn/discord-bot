"""
Einheitliche, übersichtliche Embeds für das Pet-System.
"""

from __future__ import annotations

from datetime import datetime, timezone

import discord

from config import Config
from database.models import PetEvolutionStage, PetRarity, PetRecord
from utils.embeds import apply_brand_footer, split_embed_fields, spaced_lines
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


def pet_embed_color(evolution_stage: str) -> int:
    """Embed-Farbe passend zur Evolutionsstufe."""
    colors = {
        PetEvolutionStage.BABY.value: Config.COLOR_INFO,
        PetEvolutionStage.TEEN.value: 0x57F287,
        PetEvolutionStage.ADULT.value: 0xFEE75C,
        PetEvolutionStage.LEGENDARY.value: 0xEB459E,
    }
    return colors.get(evolution_stage, Config.COLOR_INFO)


def _pet_embed(
    title: str,
    *,
    description: str | None = None,
    evolution_stage: str = PetEvolutionStage.BABY.value,
    fields: list[tuple[str, str, bool]] | None = None,
    color: int | None = None,
) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=color or pet_embed_color(evolution_stage),
        timestamp=datetime.now(timezone.utc),
    )
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    apply_brand_footer(embed)
    return embed


def build_pet_info_embed(pet: PetRecord, member: discord.Member) -> discord.Embed:
    """Übersichtliches Profil des aktiven Pets."""
    species = get_species_by_name(pet.species)
    emoji = species_display_emoji(species, pet.evolution_stage)
    current, needed, percent = xp_progress(pet.xp, pet.level)
    rarity = rarity_display(species.rarity) if species else "—"
    xp_bonus = pet_xp_boost_label(pet.species, pet.evolution_stage) if species else "—"

    return _pet_embed(
        f"{emoji} {pet.name}",
        description=spaced_lines(
            f"**{evolution_display(pet.evolution_stage)}**",
            f"Besitzer: {member.mention}",
        ),
        evolution_stage=pet.evolution_stage,
        fields=[
            (
                "📊 Fortschritt",
                spaced_lines(
                    f"Level **{pet.level}** · **{pet.xp:,}** XP",
                    f"`{current:,}` / `{needed:,}` XP (**{percent} %**)",
                ),
                False,
            ),
            (
                "🧬 Profil",
                spaced_lines(
                    f"**Art:** {pet.species}",
                    f"**Seltenheit:** {rarity}",
                    f"**XP-Bonus:** {xp_bonus}",
                ),
                False,
            ),
            (
                "⚡ Impuls",
                mood_display(pet.mood),
                False,
            ),
            (
                "🎭 Charakter",
                spaced_lines(
                    f"**Persönlichkeit:** {pet.personality}",
                    f"**Lieblingsaktivität:** {pet.favorite_activity}",
                ),
                False,
            ),
            ("💬 Catchphrase", f"*{pet.catchphrase}*", False),
            (
                "📅 Meta",
                spaced_lines(
                    f"**Geburtstag:** {pet_birthday(pet.adoption_date)}",
                    f"**Interaktionen:** {pet.total_interactions:,}",
                ),
                False,
            ),
        ],
    )


def build_pet_duplicate_embed(
    member: discord.Member,
    species: PetSpeciesDefinition,
    *,
    pet_xp: int,
    player_xp: int,
) -> discord.Embed:
    """Embed wenn ein bereits besessenes Pet gezogen wurde."""
    emoji = species_display_emoji(species, PetEvolutionStage.BABY.value)
    return _pet_embed(
        f"🔄 {emoji} Duplikat — {species.name}",
        description=spaced_lines(
            f"{member.mention}, du hast **{species.name}** bereits in deiner Sammlung!",
            "Statt eines zweiten Exemplars erhältst du:",
            f"🐾 **+{pet_xp} Pet-XP** (dein {species.name})\n"
            f"📈 **+{player_xp} Spieler-XP**",
        ),
        evolution_stage=PetEvolutionStage.BABY.value,
        color=Config.COLOR_WARNING,
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

    return _pet_embed(
        f"🐣 {emoji} {pet.name}",
        description=spaced_lines(
            f"{member.mention} hat ein neues Pet adoptiert!",
            f"**{species.name}** · {rarity_display(species.rarity)}",
            f"{personality} · {mood_display(mood)} · {favorite}",
            f"*{catchphrase}*",
        ),
        evolution_stage=pet.evolution_stage,
        fields=[
            ("Status", status, False),
            ("Evolution", evolution_display(pet.evolution_stage), False),
        ],
        color=Config.COLOR_SUCCESS,
    )


def build_pet_collection_embed(owner_name: str, pets: list[PetRecord]) -> discord.Embed:
    """Sammlungsübersicht mit kompakten Einträgen."""
    lines: list[str] = []
    for pet in pets:
        species = get_species_by_name(pet.species)
        emoji = species_display_emoji(species, pet.evolution_stage)
        active = "⭐ " if pet.is_active else ""
        rarity = rarity_display(species.rarity) if species else "—"
        lines.append(
            spaced_lines(
                f"{active}{emoji} **{pet.name}**",
                f"Lv. **{pet.level}** · {evolution_display(pet.evolution_stage)} · {rarity}",
            )
        )

    return _pet_embed(
        f"🐾 Sammlung · {owner_name}",
        description=f"**{len(pets)}** Pets · ⭐ = aktiv\n\n" + "\n\n".join(lines),
    )


def _dex_entry(species: PetSpeciesDefinition, discovered: bool) -> str:
    if discovered:
        return f"✅ {species.emoji} **{species.name}**"
    return "❓ ░░░ **???**"


def build_pet_dex_embed(discovered_names: set[str], *, owner_name: str | None = None) -> discord.Embed:
    """Sammlungsbuch aller Pet-Arten."""
    total = len(PET_SPECIES)
    found = sum(1 for species in PET_SPECIES if species.name in discovered_names)

    fields: list[tuple[str, str, bool]] = []
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
    owner_line = f"Sammlung von **{owner_name}**\n" if owner_name else ""

    return _pet_embed(
        title,
        description=f"{owner_line}Entdeckt: **{found}/{total}** Arten\n✅ gefunden · ❓ noch unbekannt",
        fields=fields,
    )


def build_pet_leaderboard_embed(
    guild_name: str,
    *,
    sort_label: str,
    lines: list[str],
) -> discord.Embed:
    """Server-Rangliste."""
    return _pet_embed(
        f"🏆 Pet-Rangliste · {guild_name}",
        description=f"Sortierung: **{sort_label}**",
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

    return _pet_embed(
        f"{emoji} Impuls-Rush · {pet.name}",
        description=spaced_lines(*description_parts),
        evolution_stage=pet.evolution_stage,
    )


def build_pet_display_embed(
    pet: PetRecord,
    member: discord.Member,
    *,
    portrait_label: str,
) -> discord.Embed:
    """Embed für KI-Portraits."""
    species = get_species_by_name(pet.species)
    emoji = species_display_emoji(species, pet.evolution_stage)
    embed = _pet_embed(
        f"🖼️ {emoji} {pet.name}",
        description=(
            f"{member.mention} zeigt sein Pet\n"
            f"**{evolution_display(pet.evolution_stage)}** · {portrait_label}\n\n"
            f"*{pet.catchphrase}*"
        ),
        evolution_stage=pet.evolution_stage,
    )
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
