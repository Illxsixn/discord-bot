"""
Pet-Skills (Impulse) für Profil-Anzeige — gekoppelt an /levels.
"""

from __future__ import annotations

from utils.pet_play import PET_IMPULSES

# (id, Kurzbeschreibung für /pet info)
PET_SKILL_EFFECTS: dict[str, str] = {
    "focus": "Bonus-Angriff · nächster Nahkampf +50 %",
    "energy": "Heilt den Spieler um 20 HP",
    "luck": "Bonus-Angriff · Endbelohnung +5 %",
}


def pet_skill_level(player_level: int) -> int:
    """Skill-Level — identisch mit /levels (Spieler & Pet)."""
    return max(1, player_level)


def pet_skill_fields(player_level: int) -> list[tuple[str, str, bool]]:
    """Drei Skill-Felder für Embed (Artwork 3-Spalten)."""
    level = pet_skill_level(player_level)
    fields: list[tuple[str, str, bool]] = []
    for impulse_id, emoji, label in PET_IMPULSES:
        effect = PET_SKILL_EFFECTS.get(impulse_id, "Spezialfähigkeit")
        fields.append(
            (
                f"{emoji} {label}",
                spaced_skill_line(level, effect),
                True,
            )
        )
    return fields


def spaced_skill_line(level: int, effect: str) -> str:
    """Formatiert Skill-Level und Effekt."""
    return f"Level **{level}**\n{effect}"


def pet_skills_summary(player_level: int) -> str:
    """Kompakte Skill-Zeile."""
    level = pet_skill_level(player_level)
    parts = [
        f"{emoji} **{label}** Lv. **{level}**"
        for _id, emoji, label in PET_IMPULSES
    ]
    return " · ".join(parts)
