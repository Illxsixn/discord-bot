"""
Zombie Survival: Kampflogik, Pet-Aktionen und Zombie-Angriffe.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from config import Config
from database.models import PetRecord, PetRarity, ZombieRunRecord
from utils.pet_play import impulse_by_id
from utils.pets import get_species_rarity
from utils.zombie_content import ZOMBIES, get_zombie, melee_base_damage, wave_zombie_list

_PASSIVE_HELP_CHANCE: dict[PetRarity, float] = {
    PetRarity.COMMON: 0.05,
    PetRarity.UNCOMMON: 0.10,
    PetRarity.RARE: 0.15,
    PetRarity.EPIC: 0.20,
    PetRarity.LEGENDARY: 0.25,
}


@dataclass
class CombatResult:
    """Ergebnis einer Kampfaktion."""

    lines: list[str] = field(default_factory=list)
    zombie_killed: bool = False
    wave_cleared: bool = False
    run_failed: bool = False
    run_completed: bool = False
    boss_killed: bool = False


def _pet_rarity(pet: PetRecord | None) -> PetRarity | None:
    if pet is None:
        return None
    return get_species_rarity(pet.species)


def tick_cooldowns(run: ZombieRunRecord) -> None:
    """Reduziert Pet-Cooldown am Rundenende."""
    if run.pet_action_cooldown > 0:
        run.pet_action_cooldown -= 1


def spawn_wave(run: ZombieRunRecord) -> list[str]:
    """Startet die aktuelle Welle und spawnt den ersten Zombie."""
    zombies = wave_zombie_list(run.wave, run.id)
    run.zombies_remaining = len(zombies)
    run.shop_available = 0
    return _spawn_next_from_queue(run, zombies)


def _spawn_next_from_queue(run: ZombieRunRecord, queue: list[str]) -> list[str]:
    """Spawnt den nächsten Zombie aus der Welle."""
    lines: list[str] = []
    if run.zombies_remaining <= 0:
        run.current_zombie_key = None
        run.current_zombie_hp = 0
        run.shop_available = 1
        lines.append(f"**Welle {run.wave}** geschafft! Wellenpause — Käufe unter **`/shop`**.")
        heal = max(1, int(run.player_max_hp * Config.ZOMBIE_BETWEEN_WAVE_HEAL_PERCENT / 100))
        run.player_hp = min(run.player_max_hp, run.player_hp + heal)
        lines.append(f"Kurz durchatmen — **+{heal}** HP.")
        return lines

    index = len(queue) - run.zombies_remaining
    key = queue[index]
    zombie = get_zombie(key)
    if zombie is None:
        return lines

    run.current_zombie_key = key
    run.current_zombie_hp = zombie.hp
    lines.append(f"Ein **{zombie.emoji} {zombie.name}** erscheint!")
    return lines


def _on_zombie_killed(run: ZombieRunRecord, zombie_key: str) -> CombatResult:
    """Verarbeitet Zombie-Tod."""
    result = CombatResult(zombie_killed=True)
    zombie = get_zombie(zombie_key)
    if zombie:
        run.run_gold += random.randint(25, 50) if not zombie.is_boss else random.randint(80, 120)
        if zombie.is_boss:
            result.boss_killed = True
            result.run_completed = True
            result.lines.append(f"**{zombie.name}** fällt! Der Seuchenherd ist gesäubert.")
            run.current_zombie_key = None
            run.current_zombie_hp = 0
            run.zombies_remaining = 0
            run.shop_available = 0
            return result

    run.zombies_remaining -= 1
    queue = wave_zombie_list(run.wave, run.id)
    if run.zombies_remaining <= 0:
        run.current_zombie_key = None
        run.current_zombie_hp = 0
        run.shop_available = 1
        heal = max(1, int(run.player_max_hp * Config.ZOMBIE_BETWEEN_WAVE_HEAL_PERCENT / 100))
        before = run.player_hp
        run.player_hp = min(run.player_max_hp, run.player_hp + heal)
        gained = run.player_hp - before
        result.wave_cleared = True
        result.lines.append(f"**Welle {run.wave}** geschafft! Wellenpause — Käufe unter **`/shop`**.")
        if gained > 0:
            result.lines.append(f"Kurz durchatmen — **+{gained}** HP.")
    else:
        result.lines.extend(_spawn_next_from_queue(run, queue))
    return result


def _zombie_attack(run: ZombieRunRecord, zombie_key: str) -> list[str]:
    """Zombie greift zurück an."""
    zombie = get_zombie(zombie_key)
    if zombie is None or run.player_hp <= 0:
        return []

    lines: list[str] = []
    defense_bonus = 0
    damage = max(1, zombie.attack - defense_bonus)

    if zombie.double_attack_chance and random.random() < zombie.double_attack_chance:
        damage *= 2
        lines.append(f"**Doppelangriff!** Der {zombie.name} trifft hart.")

    if zombie.special_attack_chance and random.random() < zombie.special_attack_chance:
        extra = random.randint(4, 10)
        damage += extra
        lines.append(f"**Spezialangriff!** Dunkle Aura trifft dich für **+{extra}** Schaden.")

    run.player_hp = max(0, run.player_hp - damage)
    lines.append(f"Der **{zombie.name}** greift an — **−{damage}** HP.")
    return lines


def _maybe_passive_help(run: ZombieRunRecord, pet: PetRecord | None) -> list[str]:
    """Passive Pet-Hilfe basierend auf Seltenheit."""
    if pet is None:
        return []
    rarity = _pet_rarity(pet)
    if rarity is None:
        return []
    chance = _PASSIVE_HELP_CHANCE.get(rarity, 0.05)
    if random.random() >= chance:
        return []

    lines: list[str] = []
    if random.random() < 0.55 and run.current_zombie_key and run.current_zombie_hp > 0:
        dmg = random.randint(3, 8)
        run.current_zombie_hp = max(0, run.current_zombie_hp - dmg)
        run.total_damage += dmg
        lines.append(f"**{pet.name}** hilft — **−{dmg}** Schaden am Zombie.")
    else:
        heal = random.randint(3, 8)
        run.player_hp = min(run.player_max_hp, run.player_hp + heal)
        lines.append(f"**{pet.name}** heilt dich — **+{heal}** HP.")
    return lines


def perform_melee(
    run: ZombieRunRecord,
    *,
    player_level: int,
    zombie_level: int,
    pet: PetRecord | None,
) -> CombatResult:
    """Spieler-Nahkampfangriff."""
    result = CombatResult()
    if not run.in_combat or not run.current_zombie_key:
        result.lines.append("Kein Zombie im Visier.")
        return result

    base = melee_base_damage(player_level, zombie_level)
    damage = random.randint(max(1, base - 2), base + 3)
    if run.focus_active:
        damage = int(damage * 1.5)
        run.focus_active = 0
        result.lines.append("**Fokus** — verstärkter Treffer!")

    run.current_zombie_hp = max(0, run.current_zombie_hp - damage)
    run.total_damage += damage
    result.lines.append(f"Du triffst für **{damage}** Schaden.")

    result.lines.extend(_maybe_passive_help(run, pet))

    if run.current_zombie_hp <= 0:
        kill_result = _on_zombie_killed(run, run.current_zombie_key)
        result.lines.extend(kill_result.lines)
        result.zombie_killed = kill_result.zombie_killed
        result.wave_cleared = kill_result.wave_cleared
        result.run_completed = kill_result.run_completed
        result.boss_killed = kill_result.boss_killed
        tick_cooldowns(run)
        if run.player_hp <= 0:
            result.run_failed = True
        return result

    result.lines.extend(_zombie_attack(run, run.current_zombie_key))
    tick_cooldowns(run)
    if run.player_hp <= 0:
        result.run_failed = True
    return result


def perform_pet_action(
    run: ZombieRunRecord,
    pet: PetRecord | None,
    impulse_id: str,
) -> CombatResult:
    """Pet-Bonusangriff — gewählter Impuls, zusätzlich zum Spieler-Nahkampf."""
    result = CombatResult()
    if pet is None:
        result.lines.append("Kein aktives Pet — Pet-Angriff deaktiviert.")
        return result
    if run.pet_action_cooldown > 0:
        result.lines.append(
            f"Pet-Angriff auf Cooldown (**{run.pet_action_cooldown}** Angriff(e) verbleibend)."
        )
        return result
    if not run.in_combat or not run.current_zombie_key:
        result.lines.append("Kein Zombie aktiv.")
        return result

    impulse = impulse_by_id(impulse_id)
    if impulse is None:
        result.lines.append("Unbekannter Impuls.")
        return result

    _, emoji, label = impulse

    if impulse_id == "focus":
        dmg = random.randint(8, 14)
        run.focus_active = 1
        result.lines.append(
            f"**{pet.name}** — {emoji} **{label}**: Bonus **{dmg}** Schaden · "
            "Nächster Nahkampf **+50 %**."
        )
    elif impulse_id == "energy":
        dmg = random.randint(15, 30)
        result.lines.append(f"**{pet.name}** — {emoji} **{label}**: Bonus **{dmg}** Schaden!")
    elif impulse_id == "luck":
        dmg = random.randint(5, 12)
        max_uses = Config.ZOMBIE_LUCK_BONUS_MAX // Config.ZOMBIE_LUCK_BONUS_PERCENT
        if run.luck_bonus_uses < max_uses:
            run.luck_bonus_uses += 1
            pct = run.luck_bonus_uses * Config.ZOMBIE_LUCK_BONUS_PERCENT
            result.lines.append(
                f"**{pet.name}** — {emoji} **{label}**: Bonus **{dmg}** Schaden · "
                f"Endbonus **+{pct} %** (max. {Config.ZOMBIE_LUCK_BONUS_MAX} %)."
            )
        else:
            result.lines.append(
                f"**{pet.name}** — {emoji} **{label}**: Bonus **{dmg}** Schaden · "
                "Glück-Bonus bereits maximal."
            )
    else:
        dmg = random.randint(8, 14)
        result.lines.append(f"**{pet.name}** — Bonus **{dmg}** Schaden!")

    run.current_zombie_hp = max(0, run.current_zombie_hp - dmg)
    run.total_damage += dmg

    if run.current_zombie_hp <= 0 and run.current_zombie_key:
        kill_result = _on_zombie_killed(run, run.current_zombie_key)
        result.lines.extend(kill_result.lines)
        result.zombie_killed = kill_result.zombie_killed
        result.wave_cleared = kill_result.wave_cleared
        result.run_completed = kill_result.run_completed
        result.boss_killed = kill_result.boss_killed

    run.pet_action_cooldown = Config.ZOMBIE_PET_ACTION_COOLDOWN
    return result


def advance_to_next_wave(run: ZombieRunRecord) -> CombatResult:
    """Startet die nächste Welle."""
    result = CombatResult()
    if run.in_combat:
        result.lines.append("Besiege zuerst den aktiven Zombie.")
        return result
    if not run.between_waves:
        result.lines.append("Schließe zuerst die aktuelle Welle ab.")
        return result
    if run.wave >= run.max_waves:
        result.lines.append("Alle Wellen abgeschlossen.")
        return result

    run.wave += 1
    run.shop_available = 0
    result.lines.append(f"**Welle {run.wave}/{run.max_waves}** beginnt!")
    result.lines.extend(spawn_wave(run))
    return result
