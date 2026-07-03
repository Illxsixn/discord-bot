"""
Zombie Survival: Typen, Wellen, Shop und Flavor-Texte.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from config import Config

ZOMBIE_TYPE_STREUNER = "streuner"
ZOMBIE_TYPE_RASENDER = "rasender"
ZOMBIE_TYPE_BOSS = "seuchenbrecher"

NORMAL_ZOMBIE_POOL = (ZOMBIE_TYPE_STREUNER, ZOMBIE_TYPE_RASENDER)

WAVE_LOCATIONS: dict[int, str] = {
    1: "Verlassene Station",
    2: "Eingestürzter Korridor",
    3: "Seuchenherd",
}

WAVE_ZOMBIE_COUNTS: dict[int, int] = {
    1: 2,
    2: 2,
    3: 1,
}


@dataclass(frozen=True)
class ZombieDefinition:
    """Stat-Block eines Zombie-Typs."""

    key: str
    name: str
    emoji: str
    hp: int
    attack: int
    points: int
    asset_folder: str
    description: str
    traits: tuple[str, ...]
    double_attack_chance: float = 0.0
    is_boss: bool = False
    special_attack_chance: float = 0.0


ZOMBIES: dict[str, ZombieDefinition] = {
    ZOMBIE_TYPE_STREUNER: ZombieDefinition(
        key=ZOMBIE_TYPE_STREUNER,
        name="Streuner",
        emoji="🧟",
        hp=34,
        attack=7,
        points=50,
        asset_folder="common",
        description="Ein langsamer Streuner mit kaputter Kleidung und graugrüner Haut.",
        traits=("eingefallene Augen", "zerrissene Kleidung", "langsame Haltung", "graugrüne Haut"),
    ),
    ZOMBIE_TYPE_RASENDER: ZombieDefinition(
        key=ZOMBIE_TYPE_RASENDER,
        name="Rasender",
        emoji="🏃",
        hp=24,
        attack=10,
        points=60,
        asset_folder="fast",
        description="Ein aggressiver Rasender mit roten Augen und schneller Bewegung.",
        traits=("rote Augen", "schnelle Bewegungsunschärfe", "dünner Körper", "aggressive Pose"),
        double_attack_chance=0.25,
    ),
    ZOMBIE_TYPE_BOSS: ZombieDefinition(
        key=ZOMBIE_TYPE_BOSS,
        name="Seuchenbrecher",
        emoji="👁️",
        hp=115,
        attack=13,
        points=250,
        asset_folder="boss",
        description="Ein riesiger mutierter Seuchenbrecher mit dunkler Aura.",
        traits=(
            "riesiger mutierter Körper",
            "leuchtende Augen",
            "dunkle Aura",
            "schwere Schultern",
            "zerstörte Umgebung",
        ),
        is_boss=True,
        special_attack_chance=0.30,
    ),
}


def get_zombie(key: str | None) -> ZombieDefinition | None:
    """Zombie-Definition nach Schlüssel."""
    if not key:
        return None
    return ZOMBIES.get(key)


def wave_zombie_list(wave: int, run_id: int) -> list[str]:
    """Deterministische Zombie-Liste für eine Welle."""
    rng = random.Random(run_id * 997 + wave * 13)
    if wave >= Config.ZOMBIE_MAX_WAVES:
        return [ZOMBIE_TYPE_BOSS]
    count = WAVE_ZOMBIE_COUNTS.get(wave, 2)
    return [rng.choice(NORMAL_ZOMBIE_POOL) for _ in range(count)]


def wave_location(wave: int) -> str:
    """Ortsname für die Welle."""
    return WAVE_LOCATIONS.get(wave, "Verlassenes Gebiet")


def wave_intro_text(wave: int, zombie: ZombieDefinition | None) -> str:
    """Flavor-Beschreibung für Run-Embed."""
    location = wave_location(wave)
    if zombie is None:
        return f"Welle {wave} abgeschlossen. Kurz durchatmen in **{location}**."
    if zombie.is_boss:
        return (
            f"Die Sirene verstummt. In **{location}** erhebt sich der **{zombie.name}** — "
            "leuchtende Augen, dunkle Aura."
        )
    if zombie.key == ZOMBIE_TYPE_RASENDER:
        return f"Die Sirene heult. In **{location}** rennt ein **{zombie.name}** auf dich zu."
    return f"In **{location}** schlurft ein **{zombie.name}** aus dem Nebel."


def player_max_hp(player_level: int) -> int:
    """Maximale Spieler-HP für einen Run (skaliert mit /levels)."""
    return Config.ZOMBIE_PLAYER_HP_BASE + max(0, player_level - 1) * 2


def melee_base_damage(player_level: int) -> int:
    """Basis-Nahkampfschaden (skaliert mit /levels)."""
    return 11 + max(0, player_level - 1) // 2


def upgrade_lines() -> str:
    """Coming-soon Upgrade-Hinweise."""
    return "Glück · Fokus · Energie — **Coming soon**"
