"""
Hilfsfunktionen für das Anarchy-Pets-System.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from config import Config
from database.models import PetEvolutionStage, PetMood, PetRarity
from utils.pet_play import PET_IMPULSES
from utils.helpers import contains_bad_word


@dataclass(frozen=True)
class PetSpeciesDefinition:
    """Definition einer Pet-Art."""

    key: str
    name: str
    emoji: str
    rarity: PetRarity
    weight: int


PET_SPECIES: tuple[PetSpeciesDefinition, ...] = (
    PetSpeciesDefinition("schattenkatze", "Schattenkatze", "🐈‍⬛", PetRarity.UNCOMMON, 12),
    PetSpeciesDefinition("mini_drache", "Mini-Drache", "🐉", PetRarity.RARE, 8),
    PetSpeciesDefinition("sternenfuchs", "Sternenfuchs", "🦊", PetRarity.RARE, 8),
    PetSpeciesDefinition("robo_hamster", "Robo-Hamster", "🤖", PetRarity.COMMON, 18),
    PetSpeciesDefinition("kristallwolf", "Kristallwolf", "🐺", PetRarity.EPIC, 12),
    PetSpeciesDefinition("wolkenschaf", "Wolkenschaf", "☁️", PetRarity.COMMON, 18),
    PetSpeciesDefinition("schleimfreund", "Schleimfreund", "💧", PetRarity.COMMON, 18),
    PetSpeciesDefinition("mondhase", "Mondhase", "🐇", PetRarity.UNCOMMON, 12),
    PetSpeciesDefinition("feuergecko", "Feuergecko", "🦎", PetRarity.UNCOMMON, 12),
    PetSpeciesDefinition("buecher_eule", "Bücher-Eule", "🦉", PetRarity.UNCOMMON, 12),
    PetSpeciesDefinition("neon_axolotl", "Neon-Axolotl", "🌈", PetRarity.RARE, 8),
    PetSpeciesDefinition("pilzkroete", "Pilzkröte", "🍄", PetRarity.COMMON, 18),
    PetSpeciesDefinition("eis_pinguin", "Eis-Pinguin", "🐧", PetRarity.UNCOMMON, 12),
    PetSpeciesDefinition("koboldhund", "Koboldhund", "🐕", PetRarity.RARE, 8),
    PetSpeciesDefinition("galaxie_schlange", "Galaxie-Schlange", "🐍", PetRarity.LEGENDARY, 10),
    # Common
    PetSpeciesDefinition("moos_eichhorn", "Moos-Eichhorn", "🐿️", PetRarity.COMMON, 18),
    PetSpeciesDefinition("glueh_wuermchen", "Glühwürmchen", "🪲", PetRarity.COMMON, 18),
    PetSpeciesDefinition("kiesel_gnom", "Kiesel-Gnom", "🪨", PetRarity.COMMON, 18),
    # Uncommon
    PetSpeciesDefinition("nebel_eule", "Nebel-Eule", "🌙", PetRarity.UNCOMMON, 12),
    PetSpeciesDefinition("bernstein_krebs", "Bernstein-Krebs", "🦀", PetRarity.UNCOMMON, 12),
    PetSpeciesDefinition("sturm_wiesel", "Sturm-Wiesel", "⚡", PetRarity.UNCOMMON, 12),
    # Rare
    PetSpeciesDefinition("korallen_schildkroete", "Korallen-Schildkröte", "🐢", PetRarity.RARE, 8),
    PetSpeciesDefinition("donner_fledermaus", "Donner-Fledermaus", "🦇", PetRarity.RARE, 8),
    PetSpeciesDefinition("purpur_schmetterling", "Purpur-Schmetterling", "🦋", PetRarity.RARE, 8),
    # Epic
    PetSpeciesDefinition("lava_luchs", "Lava-Luchs", "🐆", PetRarity.EPIC, 12),
    PetSpeciesDefinition("aurora_rabe", "Aurora-Rabe", "🌌", PetRarity.EPIC, 12),
    PetSpeciesDefinition("runen_baer", "Runen-Bär", "🐻", PetRarity.EPIC, 12),
    # Legendary
    PetSpeciesDefinition("phoenix_kueken", "Phönix-Küken", "🔥", PetRarity.LEGENDARY, 10),
    PetSpeciesDefinition("kosmos_wal", "Kosmos-Wal", "🐋", PetRarity.LEGENDARY, 10),
    PetSpeciesDefinition("mythen_einhorn", "Mythen-Einhorn", "🦄", PetRarity.LEGENDARY, 10),
)

PERSONALITIES: tuple[str, ...] = (
    "verspielt",
    "schüchtern",
    "frech",
    "neugierig",
    "verschlafen",
    "loyal",
    "chaotisch",
    "mutig",
    "entspannt",
    "dramatisch",
)

FAVORITE_ACTIVITIES: tuple[str, ...] = (
    "Spielen",
    "Schlafen",
    "Erkunden",
    "Lesen",
    "Kuscheln",
    "Abenteuer",
)

LEGACY_MOOD_MAP: dict[str, str] = {
    "happy": PetMood.FOCUS.value,
    "playful": PetMood.ENERGY.value,
    "sleepy": PetMood.LUCK.value,
    "curious": PetMood.FOCUS.value,
}

MOOD_LABELS: dict[str, str] = {
    impulse_id: label for impulse_id, _emoji, label in PET_IMPULSES
}
MOOD_EMOJIS: dict[str, str] = {
    impulse_id: emoji for impulse_id, emoji, _label in PET_IMPULSES
}
PET_MOOD_IDS: tuple[str, ...] = tuple(MOOD_LABELS.keys())

RARITY_EMOJIS: dict[PetRarity, str] = {
    PetRarity.COMMON: "⚪",
    PetRarity.UNCOMMON: "🟢",
    PetRarity.RARE: "🔵",
    PetRarity.EPIC: "🟣",
    PetRarity.LEGENDARY: "🟡",
}

RARITY_XP_BOOST: dict[PetRarity, float] = {
    PetRarity.COMMON: 1.02,
    PetRarity.UNCOMMON: 1.04,
    PetRarity.RARE: 1.06,
    PetRarity.EPIC: 1.08,
    PetRarity.LEGENDARY: 1.10,
}

CATCHPHRASES: dict[str, tuple[str, ...]] = {
    "verspielt": (
        "Lass uns spielen!",
        "Noch eine Runde?",
        "Ich bin bereit für Action!",
    ),
    "schüchtern": (
        "Hallo… ich bin noch ein bisschen nervös.",
        "Danke, dass du da bist.",
        "Ich verstecke mich fast…",
    ),
    "frech": (
        "Hehe, erwischt!",
        "Ich bin der Star hier!",
        "Versuch mich zu finden!",
    ),
    "neugierig": (
        "Was ist das da drüben?",
        "Ich will alles entdecken!",
        "Jede Ecke birgt ein Geheimnis.",
    ),
    "verschlafen": (
        "Gähn… noch fünf Minuten.",
        "Ich träume von Sternen.",
        "Kuscheln ist mein Lieblingssport.",
    ),
    "loyal": (
        "Ich bleibe an deiner Seite.",
        "Du bist mein bester Freund!",
        "Gemeinsam schaffen wir alles.",
    ),
    "chaotisch": (
        "Ups… war das ich?",
        "Chaos ist mein zweiter Vorname!",
        "Niemand weiß, was als Nächstes passiert!",
    ),
    "mutig": (
        "Vorwärts, kein Angst!",
        "Ich beschütze dich!",
        "Abenteuer warten auf uns!",
    ),
    "entspannt": (
        "Alles in Ruhe, alles gut.",
        "Kein Stress, nur gute Vibes.",
        "Heute ist ein chilliger Tag.",
    ),
    "dramatisch": (
        "Das ist der emotionalste Moment meines Lebens!",
        "Die Welt dreht sich nur um uns!",
        "Was für ein spektakulärer Tag!",
    ),
}

EVOLUTION_LABELS: dict[str, str] = {
    PetEvolutionStage.BABY.value: "Baby",
    PetEvolutionStage.TEEN.value: "Teenager",
    PetEvolutionStage.ADULT.value: "Erwachsen",
    PetEvolutionStage.LEGENDARY.value: "Meisterform",
}

EVOLUTION_STAGE_BADGES: dict[str, str] = {
    PetEvolutionStage.BABY.value: "",
    PetEvolutionStage.TEEN.value: "🌱",
    PetEvolutionStage.ADULT.value: "✨",
    PetEvolutionStage.LEGENDARY.value: "👑",
}

RARITY_SPECIES_ORDER: tuple[PetRarity, ...] = (
    PetRarity.COMMON,
    PetRarity.UNCOMMON,
    PetRarity.RARE,
    PetRarity.EPIC,
    PetRarity.LEGENDARY,
)

EVOLUTION_MILESTONES: tuple[int, ...] = (
    Config.PET_EVOLUTION_TEEN,
    Config.PET_EVOLUTION_ADULT,
    Config.PET_EVOLUTION_LEGENDARY,
)

MENTION_PATTERN = re.compile(r"<@!?\d+>|@everyone|@here")


def xp_required_for_level(level: int) -> int:
    """XP, die für das nächste Level benötigt werden."""
    return 100 + (level * 35)


def level_from_xp(xp: int) -> int:
    """Berechnet Pet-Level aus gesammelter XP."""
    level = 1
    while xp >= xp_required_for_level(level):
        xp -= xp_required_for_level(level)
        level += 1
    return level


def xp_progress(xp: int, level: int) -> tuple[int, int, int]:
    """Gibt (aktuell, benötigt, Prozent) für das aktuelle Level zurück."""
    remaining = xp
    for current in range(1, level):
        remaining -= xp_required_for_level(current)
    needed = xp_required_for_level(level)
    current_in_level = max(0, remaining)
    percent = min(100, int((current_in_level / needed) * 100)) if needed else 100
    return current_in_level, needed, percent


def evolution_stage_from_level(level: int) -> str:
    """Bestimmt die Evolutionsstufe anhand des Levels."""
    if level >= Config.PET_EVOLUTION_LEGENDARY:
        return PetEvolutionStage.LEGENDARY.value
    if level >= Config.PET_EVOLUTION_ADULT:
        return PetEvolutionStage.ADULT.value
    if level >= Config.PET_EVOLUTION_TEEN:
        return PetEvolutionStage.TEEN.value
    return PetEvolutionStage.BABY.value


def get_species_definition(species_key: str) -> PetSpeciesDefinition | None:
    """Findet die Art-Definition anhand des Schlüssels."""
    for definition in PET_SPECIES:
        if definition.key == species_key:
            return definition
    return None


def get_species_by_name(name: str) -> PetSpeciesDefinition | None:
    """Findet die Art-Definition anhand des Anzeigenamens."""
    for definition in PET_SPECIES:
        if definition.name == name:
            return definition
    return None


def get_species_rarity(species_name: str) -> PetRarity | None:
    """Liefert die Seltenheit einer Pet-Art."""
    species = get_species_by_name(species_name)
    return species.rarity if species else None


def apply_rarity_xp_boost(amount: int, rarity: PetRarity | None) -> int:
    """Wendet den Seltenheits-XP-Bonus auf eine Basis-XP-Menge an."""
    if amount <= 0 or rarity is None:
        return amount
    multiplier = RARITY_XP_BOOST.get(rarity, 1.0)
    return max(1, round(amount * multiplier))


def rarity_xp_boost_label(rarity: PetRarity) -> str:
    """Formatiert den Seltenheits-XP-Bonus für Embeds."""
    percent = (RARITY_XP_BOOST.get(rarity, 1.0) - 1.0) * 100
    return f"+{percent:.1f} %".replace(".", ",")


def random_species() -> PetSpeciesDefinition:
    """Wählt zufällig eine Pet-Art (gewichtet nach Seltenheit)."""
    weights = [species.weight for species in PET_SPECIES]
    return random.choices(list(PET_SPECIES), weights=weights, k=1)[0]


def random_personality() -> str:
    """Wählt zufällig eine Persönlichkeit."""
    return random.choice(PERSONALITIES)


def normalize_mood(mood: str) -> str:
    """Mappt alte Stimmungswerte auf die drei Pet-Play-Impulse."""
    normalized = LEGACY_MOOD_MAP.get(mood, mood)
    if normalized in MOOD_LABELS:
        return normalized
    return PetMood.FOCUS.value


def random_mood() -> str:
    """Wählt zufällig einen Impuls-Zustand."""
    return random.choice(PET_MOOD_IDS)


def random_favorite_activity() -> str:
    """Wählt zufällig eine Lieblingsaktivität."""
    return random.choice(FAVORITE_ACTIVITIES)


def random_catchphrase(personality: str) -> str:
    """Wählt einen passenden Spruch zur Persönlichkeit."""
    phrases = CATCHPHRASES.get(personality, ("Hallo, ich bin dein neuer Begleiter!",))
    return random.choice(phrases)


def default_pet_name(species: PetSpeciesDefinition) -> str:
    """Erzeugt einen Standardnamen für ein neues Pet."""
    suffix = random.randint(100, 999)
    return f"{species.name} {suffix}"


def mood_display(mood: str) -> str:
    """Formatiert Impuls-Zustand mit Emoji und Label."""
    mood = normalize_mood(mood)
    emoji = MOOD_EMOJIS.get(mood, "🐾")
    label = MOOD_LABELS.get(mood, mood)
    return f"{emoji} {label}"


def evolution_display(stage: str) -> str:
    """Deutscher Anzeigename einer Evolutionsstufe."""
    badge = EVOLUTION_STAGE_BADGES.get(stage, "")
    label = EVOLUTION_LABELS.get(stage, stage)
    if badge:
        return f"{badge} {label}"
    return label


def species_display_emoji(
    species: PetSpeciesDefinition | None,
    evolution_stage: str,
) -> str:
    """Art-Emoji mit optionalem Evolutions-Akzent."""
    if species is None:
        return "🐾"
    badge = EVOLUTION_STAGE_BADGES.get(evolution_stage, "")
    if badge:
        return f"{badge}{species.emoji}"
    return species.emoji


def rarity_display(rarity: PetRarity) -> str:
    """Formatiert Seltenheit mit Emoji."""
    return f"{RARITY_EMOJIS.get(rarity, '⚪')} {rarity.value}"


def format_date(dt: datetime | None) -> str:
    """Formatiert Datum für Embeds."""
    if dt is None:
        return "Unbekannt"
    return dt.astimezone(timezone.utc).strftime("%d.%m.%Y")


def pet_birthday(dt: datetime | None) -> str:
    """Geburtstag = Adoptionstag."""
    return format_date(dt)


def validate_pet_name(name: str, bad_words: list[str] | None = None) -> str | None:
    """
    Prüft einen Pet-Namen.

    Returns:
        Fehlermeldung oder None wenn gültig.
    """
    cleaned = name.strip()
    if not cleaned:
        return "Der Name darf nicht leer sein."
    if len(cleaned) > Config.PET_NAME_MAX_LENGTH:
        return f"Der Name darf maximal **{Config.PET_NAME_MAX_LENGTH}** Zeichen lang sein."
    if MENTION_PATTERN.search(cleaned):
        return "Mentions (@User, @everyone, @here) sind nicht erlaubt."
    if bad_words:
        found = contains_bad_word(cleaned, bad_words)
        if found:
            return "Dieser Name ist auf dem Server nicht erlaubt."
    return None


def is_evolution_milestone(old_level: int, new_level: int) -> int | None:
    """Gibt das erreichte Meilenstein-Level zurück, falls vorhanden."""
    for milestone in EVOLUTION_MILESTONES:
        if old_level < milestone <= new_level:
            return milestone
    return None
