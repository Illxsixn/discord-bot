"""
KI-Portraits für Anarchy Pets über die Agnes-API.

Bilder werden einmal generiert, lokal gecacht und bei Evolution neu erzeugt.
"""

from __future__ import annotations

import asyncio
import logging
from io import BytesIO
from pathlib import Path

from PIL import Image

from config import Config
from database.models import PetEvolutionStage, PetRarity, PetRecord
from utils.agnes_images import AgnesImageError, agnes_configured, request_agnes_image
from utils.pet_appearance import secret_evolution_traits_prompt, secret_visual_traits_prompt
from utils.pets import PetSpeciesDefinition, evolution_display, get_species_by_name, rarity_display

logger = logging.getLogger(__name__)

_portrait_locks: dict[int, asyncio.Lock] = {}

SPECIES_PROMPT_HINTS: dict[str, str] = {
    "schattenkatze": "shadowy mystical black cat with glowing eyes",
    "mini_drache": "tiny friendly dragon with small wings",
    "sternenfuchs": "cosmic fox with starry fur patterns",
    "robo_hamster": "cute robotic hamster with metal and LED details",
    "kristallwolf": "crystal wolf made of translucent blue ice shards",
    "wolkenschaf": "fluffy cloud sheep floating slightly",
    "schleimfreund": "adorable green slime blob companion with one simple cute face",
    "mondhase": "moon rabbit with soft silver fur and crescent motifs",
    "feuergecko": "fire gecko with ember tail and warm orange scales",
    "buecher_eule": "wise owl wearing tiny round spectacles",
    "neon_axolotl": "neon axolotl with pink and cyan bioluminescent gills",
    "pilzkroete": "toad with a red mushroom cap on its head",
    "eis_pinguin": "ice penguin with frosty feathers and a cozy scarf",
    "koboldhund": "goblin dog with mossy fur and playful green eyes",
    "galaxie_schlange": "galaxy snake with swirling purple star patterns",
    "moos_eichhorn": "cute squirrel with mossy green fur and tiny acorn",
    "glueh_wuermchen": "magical glowing firefly with soft yellow light trails",
    "kiesel_gnom": "tiny stone gnome creature with pebble skin and crystal eyes",
    "nebel_eule": "misty owl with soft grey feathers and moonlit glow",
    "bernstein_krebs": "amber crab with translucent golden shell and warm highlights",
    "sturm_wiesel": "swift storm weasel with wind-swept fur and electric sparks",
    "korallen_schildkroete": "coral sea turtle with colorful reef patterns on its shell",
    "donner_fledermaus": "thunder bat with dark wings and subtle lightning markings",
    "purpur_schmetterling": "purple butterfly with shimmering iridescent wings",
    "lava_luchs": "lava lynx with ember spots and molten orange fur accents",
    "aurora_rabe": "aurora raven with northern lights shimmer on dark feathers",
    "runen_baer": "rune bear with glowing ancient symbols on its fur",
    "phoenix_kueken": "baby phoenix with small flame feathers and golden glow",
    "kosmos_wal": "tiny cosmic whale floating with starry nebula patterns",
    "mythen_einhorn": "mythical unicorn with flowing mane and soft magical aura",
}

EVOLUTION_PROMPT_HINTS: dict[str, str] = {
    PetEvolutionStage.BABY.value: "baby, small and round, very cute",
    PetEvolutionStage.TEEN.value: "teenager, slightly taller, energetic",
    PetEvolutionStage.ADULT.value: "adult, confident and detailed",
    PetEvolutionStage.LEGENDARY.value: "legendary majestic form, glowing aura, epic details",
}

RARITY_BORDER_COLORS: dict[PetRarity, tuple[int, int, int]] = {
    PetRarity.COMMON: (140, 140, 150),
    PetRarity.UNCOMMON: (80, 180, 90),
    PetRarity.RARE: (70, 130, 220),
    PetRarity.EPIC: (160, 80, 210),
    PetRarity.LEGENDARY: (230, 140, 40),
}

RARITY_BORDER_WIDTH = 14


class PetPortraitError(Exception):
    """Fehler bei der Portrait-Generierung."""


def pet_portrait_path(pet_id: int, evolution_stage: str) -> Path:
    """Absoluter Pfad zur gecachten Portrait-PNG."""
    filename = f"{pet_id}_{evolution_stage}_v{Config.PET_PORTRAIT_PROMPT_VERSION}.png"
    return Config.PET_IMAGE_DIR / filename


def clear_pet_portrait_cache() -> int:
    """
    Löscht alle gecachten Pet-Portraits im Asset-Ordner.

    Returns:
        Anzahl gelöschter Dateien.
    """
    directory = Config.PET_IMAGE_DIR
    if not directory.is_dir():
        return 0

    removed = 0
    for path in directory.glob("*.png"):
        if path.is_file():
            path.unlink()
            removed += 1
    return removed


def invalidate_pet_portrait(pet: PetRecord) -> None:
    """Entfernt alle gecachten Portraits eines Pets (alle Versionen/Evolutionen)."""
    directory = Config.PET_IMAGE_DIR
    if not directory.is_dir():
        return
    pattern = f"{pet.id}_"
    for path in directory.glob(f"{pattern}*.png"):
        if path.is_file():
            path.unlink(missing_ok=True)


def build_pet_portrait_prompt(pet: PetRecord, species: PetSpeciesDefinition | None) -> str:
    """Erstellt einen stabilen Prompt für die Bild-KI (inkl. versteckter Merkmale)."""
    species_key = species.key if species else "schleimfreund"
    species_hint = SPECIES_PROMPT_HINTS.get(species_key, "cute fantasy virtual pet creature")
    evolution_hint = EVOLUTION_PROMPT_HINTS.get(
        pet.evolution_stage,
        EVOLUTION_PROMPT_HINTS[PetEvolutionStage.BABY.value],
    )
    rarity = species.rarity if species else PetRarity.COMMON
    rarity_hint = {
        PetRarity.COMMON: "simple friendly design",
        PetRarity.UNCOMMON: "pleasant polished design",
        PetRarity.RARE: "detailed vibrant design",
        PetRarity.EPIC: "elaborate striking design",
        PetRarity.LEGENDARY: "legendary ornate design with subtle glow",
    }.get(rarity, "friendly design")
    unique_traits = secret_visual_traits_prompt(pet.id, species_key)
    evolution_traits = secret_evolution_traits_prompt(pet.id, species_key, pet.evolution_stage)

    return (
        f"Single unique individual {species_hint}, one creature only, solo portrait, "
        f"exactly one face, one head, no duplicate faces, no twins, no mirror reflection, "
        f"no second character, fantasy virtual pet creature, "
        f"{evolution_hint}, {rarity_hint}, "
        f"distinct appearance: {unique_traits}, "
        f"evolved power traits: {evolution_traits}, "
        "full body character design, centered composition, soft digital illustration, "
        "clean soft gradient background, wholesome game art style, "
        "clearly more powerful at higher evolution stages, "
        "highly distinct from other creatures of same species, "
        "no text, no watermark, no human, no avatar, no frame, no collage"
    )


async def _request_portrait_image(prompt: str) -> bytes:
    """Ruft die Agnes-API auf und liefert PNG-Bytes."""
    if not agnes_configured():
        raise PetPortraitError(
            "KI-Portraits sind nicht konfiguriert. "
            "Trage `AGNES_API_KEY` in der `.env` ein."
        )
    try:
        return await request_agnes_image(prompt)
    except AgnesImageError as exc:
        raise PetPortraitError(str(exc)) from exc


async def ensure_pet_portrait(pet: PetRecord, *, force: bool = False) -> Path:
    """
    Liefert den Pfad zum Portrait (Cache oder neue Generierung).

    Raises:
        PetPortraitError: Bei fehlender Konfiguration oder API-Fehler.
    """
    path = pet_portrait_path(pet.id, pet.evolution_stage)
    if force:
        invalidate_pet_portrait(pet)

    if path.is_file():
        return path

    lock = _portrait_locks.setdefault(pet.id, asyncio.Lock())
    async with lock:
        if path.is_file():
            return path

        species = get_species_by_name(pet.species)
        prompt = build_pet_portrait_prompt(pet, species)
        image_bytes = await _request_portrait_image(prompt)

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(image_bytes)
        logger.info(
            "Pet-Portrait generiert: pet_id=%s species=%s evolution=%s",
            pet.id,
            pet.species,
            pet.evolution_stage,
        )
        return path


def apply_rarity_border(image: Image.Image, rarity: PetRarity) -> Image.Image:
    """Fügt einen farbigen Rahmen passend zur Seltenheit hinzu."""
    color = RARITY_BORDER_COLORS.get(rarity, RARITY_BORDER_COLORS[PetRarity.COMMON])
    rgba = image.convert("RGBA")
    width = RARITY_BORDER_WIDTH
    bordered = Image.new("RGBA", (rgba.width + width * 2, rgba.height + width * 2), (*color, 255))
    bordered.paste(rgba, (width, width), rgba)
    return bordered


def load_pet_portrait_buffer(image_file: Path, rarity: PetRarity) -> BytesIO:
    """Lädt ein Portrait mit Seltenheits-Rahmen für Discord-Anhänge."""
    with Image.open(image_file) as img:
        framed = apply_rarity_border(img, rarity)
        buffer = BytesIO()
        framed.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer


def portrait_status_label(pet: PetRecord) -> str:
    """Kurzinfo für Embeds."""
    species = get_species_by_name(pet.species)
    emoji = species.emoji if species else "🐾"
    rarity = rarity_display(species.rarity) if species else "—"
    return (
        f"{emoji} **{pet.species}** • {rarity}\n"
        f"{evolution_display(pet.evolution_stage)} • Level **{pet.level}**"
    )
