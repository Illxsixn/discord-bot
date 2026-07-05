"""
Versteckte visuelle Merkmale pro Pet — nur für KI-Prompts, nicht in Discord sichtbar.

Deterministisch aus Pet-ID + Art: gleiches Pet = gleiche Merkmale, andere Pets = andere.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class SecretPetTraits:
    """Interne Merkmale für Bildgenerierung (nie an User ausgeben)."""

    eye_color: str
    fur_pattern: str
    markings: str
    accessory: str
    pose: str
    color_accent: str
    expression: str


@dataclass(frozen=True)
class SecretEvolutionTraits:
    """Interne Evolutionsmerkmale für stärkere Portraits."""

    body_trait: str
    aura_trait: str
    power_trait: str
    detail_trait: str


EYE_COLORS: tuple[str, ...] = (
    "deep amber",
    "bright emerald",
    "soft violet",
    "ice blue",
    "golden yellow",
    "ruby red",
    "silver grey",
    "teal cyan",
    "sunset orange",
    "mint green",
)

FUR_PATTERNS: tuple[str, ...] = (
    "solid coat",
    "subtle gradient fur",
    "speckled fur texture",
    "striped pattern",
    "spotted pattern",
    "two-tone fur split",
    "dappled markings",
    "marbled swirls on fur",
    "patchwork color blocks",
    "frost-tipped fur edges",
)

MARKINGS: tuple[str, ...] = (
    "small heart-shaped spot on chest",
    "crescent mark on forehead",
    "tiny star freckles on cheeks",
    "lightning bolt stripe on flank",
    "soft spiral mark on shoulder",
    "diamond-shaped patch on back",
    "three tiny dots above nose",
    "asymmetric ear tip coloring",
    "glowing rune-like spot on hip",
    "delicate paw pad highlights",
)

ACCESSORIES: tuple[str, ...] = (
    "thin braided collar with tiny charm",
    "small silk neck scarf",
    "mini bell on a leather collar",
    "woven flower bracelet on front leg",
    "tiny crystal pendant",
    "colorful bandana",
    "small feather tied behind ear",
    "bronze tag on collar",
    "soft ribbon bow",
    "glowing anklet ring",
    "no accessory",
    "no accessory",
)

POSES: tuple[str, ...] = (
    "sitting upright three-quarter view facing left",
    "standing proudly with head turned to the side",
    "playful crouch ready to pounce, asymmetric stance",
    "relaxed lounging pose on one hip",
    "mid-step walking pose to the side",
    "sitting with single tail curled once beside the body",
    "stretching pose with one paw forward",
    "alert stance ears perked up, body angled slightly",
)

COLOR_ACCENTS: tuple[str, ...] = (
    "rose gold accent highlights",
    "cool blue accent highlights",
    "warm copper accent highlights",
    "pastel pink accent highlights",
    "neon lime accent highlights",
    "deep crimson accent highlights",
    "lavender accent highlights",
    "sunshine yellow accent highlights",
)

EXPRESSIONS: tuple[str, ...] = (
    "gentle curious expression",
    "confident smirk expression",
    "sleepy relaxed expression",
    "excited happy expression",
    "calm wise expression",
    "mischievous playful expression",
)

EVOLUTION_TRAITS: dict[str, tuple[SecretEvolutionTraits, ...]] = {
    "baby": (
        SecretEvolutionTraits(
            "small rounded body proportions",
            "very faint soft glow",
            "tiny harmless sparkles",
            "simple smooth silhouette",
        ),
        SecretEvolutionTraits(
            "short limbs and oversized head",
            "soft pastel aura",
            "gentle magical shimmer",
            "minimal markings and cute features",
        ),
    ),
    "teen": (
        SecretEvolutionTraits(
            "sleeker taller body proportions",
            "visible colored aura around the body",
            "small magical energy wisps",
            "slightly sharper markings and stronger posture",
        ),
        SecretEvolutionTraits(
            "athletic young creature silhouette",
            "subtle glowing outline",
            "floating tiny power motes",
            "more defined fur, scales, feathers, or shell texture",
        ),
    ),
    "adult": (
        SecretEvolutionTraits(
            "powerful mature body with confident stance",
            "bright controlled aura",
            "visible elemental energy flowing around paws, tail, wings, or body",
            "ornate markings and refined fantasy creature details",
        ),
        SecretEvolutionTraits(
            "larger heroic silhouette with strong proportions",
            "radiant aura halo behind the creature",
            "crackling magical particles and energy trails",
            "detailed evolved patterns, sharper features, and elegant armor-like accents",
        ),
    ),
    "legendary": (
        SecretEvolutionTraits(
            "majestic legendary form with imposing silhouette",
            "intense glowing aura and divine backlight",
            "powerful elemental storm swirling around the creature",
            "mythic ornaments, crown-like shapes, glowing runes, and dramatic evolved markings",
        ),
        SecretEvolutionTraits(
            "ancient mythical beast form, grand and powerful",
            "cosmic aura with radiant energy rings",
            "floating shards, stars, flames, lightning, or magical crystals around the body",
            "highly ornate legendary details, luminous symbols, and epic fantasy presence",
        ),
    ),
}


def _trait_seed(*parts: object) -> int:
    digest = hashlib.sha256(":".join(str(part) for part in parts).encode()).hexdigest()
    return int(digest[:16], 16)


def derive_secret_traits(pet_id: int, species_key: str) -> SecretPetTraits:
    """Erzeugt stabile, einzigartige Merkmale für ein Pet."""
    rng = random.Random(_trait_seed(pet_id, species_key, "base"))
    accessory = rng.choice(ACCESSORIES)
    return SecretPetTraits(
        eye_color=rng.choice(EYE_COLORS),
        fur_pattern=rng.choice(FUR_PATTERNS),
        markings=rng.choice(MARKINGS),
        accessory=accessory,
        pose=rng.choice(POSES),
        color_accent=rng.choice(COLOR_ACCENTS),
        expression=rng.choice(EXPRESSIONS),
    )


def derive_secret_evolution_traits(
    pet_id: int,
    species_key: str,
    evolution_stage: str,
) -> SecretEvolutionTraits:
    """Erzeugt stabile Evolutionsmerkmale für ein Pet und eine Stufe."""
    traits = EVOLUTION_TRAITS.get(evolution_stage, EVOLUTION_TRAITS["baby"])
    rng = random.Random(_trait_seed(pet_id, species_key, evolution_stage, "evolution"))
    return rng.choice(traits)


def secret_visual_traits_prompt(pet_id: int, species_key: str) -> str:
    """Formatiert Merkmale als englischen Prompt-Block für die Bild-KI."""
    traits = derive_secret_traits(pet_id, species_key)
    parts = [
        traits.fur_pattern,
        f"{traits.eye_color} eyes",
        traits.markings,
        traits.pose,
        traits.color_accent,
        traits.expression,
    ]
    if traits.accessory != "no accessory":
        parts.insert(3, traits.accessory)
    return ", ".join(parts)


def secret_evolution_traits_prompt(
    pet_id: int,
    species_key: str,
    evolution_stage: str,
) -> str:
    """Formatiert versteckte Evolutionsmerkmale für die Bild-KI."""
    traits = derive_secret_evolution_traits(pet_id, species_key, evolution_stage)
    return ", ".join(
        (
            traits.body_trait,
            traits.aura_trait,
            traits.power_trait,
            traits.detail_trait,
        )
    )
