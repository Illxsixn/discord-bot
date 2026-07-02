"""
Dungeon-Logik: HP, Ereignisse, Belohnungen.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timezone

import discord
from discord.ext import commands

from config import Config
from database.database import Database
from database.models import (
    DungeonEventType,
    DungeonRunRecord,
    DungeonRunStatus,
    PetEvolutionStage,
    PetRarity,
    PetRecord,
    PlayerEconomyRecord,
)
from utils.pet_rewards import award_pet_xp
from utils.pets import get_species_rarity

_RARITY_HP_BONUS: dict[PetRarity, int] = {
    PetRarity.COMMON: 0,
    PetRarity.UNCOMMON: 10,
    PetRarity.RARE: 20,
    PetRarity.EPIC: 35,
    PetRarity.LEGENDARY: 50,
}

_EVOLUTION_HP_BONUS: dict[str, int] = {
    PetEvolutionStage.BABY.value: 0,
    PetEvolutionStage.TEEN.value: 10,
    PetEvolutionStage.ADULT.value: 20,
    PetEvolutionStage.LEGENDARY.value: 35,
}

_EVENT_FLAVOR: dict[str, tuple[str, str]] = {
    DungeonEventType.FIGHT.value: ("⚔️ Kampf", "Ein Gegner blockiert den Gang …"),
    DungeonEventType.TRAP.value: ("🪤 Falle", "Der Boden knarzt unter dir …"),
    DungeonEventType.TREASURE.value: ("💎 Schatz", "Eine Truhe wartet in der Ecke."),
    DungeonEventType.FOUNTAIN.value: ("💧 Heilbrunnen", "Frisches Wasser — ein willkommener Anblick."),
    DungeonEventType.GOLD.value: ("🪙 Gold", "Münzen glitzern zwischen den Steinen."),
    DungeonEventType.PET_XP.value: ("✨ Energie", "Magische Spuren hängen in der Luft."),
}

# Freundlichere Verteilung: mehr Gold/Heilung, weniger harte Kämpfe
_EVENT_WEIGHTS: dict[str, int] = {
    DungeonEventType.FIGHT.value: 18,
    DungeonEventType.TRAP.value: 12,
    DungeonEventType.TREASURE.value: 18,
    DungeonEventType.FOUNTAIN.value: 18,
    DungeonEventType.GOLD.value: 24,
    DungeonEventType.PET_XP.value: 10,
}


@dataclass
class RoomOutcome:
    """Ergebnis eines Dungeon-Raums."""

    text: str
    event_type: str = ""
    failed: bool = False
    completed: bool = False
    pet_ko: bool = False


def player_hp_max(level: int) -> int:
    """Maximale Spieler-HP inkl. Level-Bonus."""
    return Config.DUNGEON_PLAYER_HP_BASE + max(0, level - 1) * 2


def pet_hp_max(pet: PetRecord) -> int:
    """Maximale Pet-HP aus Level, Seltenheit und Evolution."""
    rarity = get_species_rarity(pet.species)
    rarity_bonus = _RARITY_HP_BONUS.get(rarity, 0) if rarity else 0
    evo_bonus = _EVOLUTION_HP_BONUS.get(pet.evolution_stage, 0)
    return Config.DUNGEON_PET_HP_BASE + pet.level * 2 + rarity_bonus + evo_bonus


def apply_hp_regen(economy: PlayerEconomyRecord, hp_max: int) -> PlayerEconomyRecord:
    """Regeneriert Spieler-HP passiv (auch langsam ab 0 HP)."""
    now = datetime.now(timezone.utc)
    if economy.pet_recovery_until and economy.pet_recovery_until <= now:
        economy.pet_recovery_until = None
        economy.pet_recovery_pet_id = None

    if economy.player_hp_max <= 0:
        economy.player_hp_max = hp_max
        economy.player_hp = hp_max
        economy.last_hp_regen_at = now
        return economy

    if economy.player_hp_max != hp_max:
        economy.player_hp_max = hp_max
        economy.player_hp = min(economy.player_hp, hp_max)

    if economy.player_hp >= hp_max:
        economy.player_hp = hp_max
        economy.last_hp_regen_at = now
        return economy

    if economy.last_hp_regen_at is None:
        economy.last_hp_regen_at = now
        return economy

    elapsed = (now - economy.last_hp_regen_at).total_seconds()
    ticks = int(elapsed // Config.DUNGEON_HP_REGEN_INTERVAL)
    if ticks <= 0:
        return economy

    gain = ticks * Config.DUNGEON_HP_REGEN_AMOUNT
    economy.player_hp = min(hp_max, economy.player_hp + gain)
    economy.last_hp_regen_at = now
    return economy


def dungeon_cooldown_remaining(economy: PlayerEconomyRecord) -> int | None:
    """Verbleibende Cooldown-Sekunden bis zum nächsten Start."""
    if economy.last_dungeon_at is None:
        return None
    elapsed = (datetime.now(timezone.utc) - economy.last_dungeon_at).total_seconds()
    remaining = Config.DUNGEON_RUN_COOLDOWN - elapsed
    if remaining <= 0:
        return None
    return int(remaining) + 1


def pet_in_recovery(economy: PlayerEconomyRecord, pet_id: int) -> int | None:
    """Verbleibende Erholungssekunden für ein Pet."""
    if economy.pet_recovery_pet_id != pet_id or economy.pet_recovery_until is None:
        return None
    remaining = (economy.pet_recovery_until - datetime.now(timezone.utc)).total_seconds()
    if remaining <= 0:
        return None
    return int(remaining) + 1


def generate_events() -> list[str]:
    """Erzeugt gewichtete Ereignisse für einen Dungeon."""
    count = random.randint(Config.DUNGEON_ROOM_MIN, Config.DUNGEON_ROOM_MAX)
    pool = list(_EVENT_WEIGHTS.keys())
    weights = [_EVENT_WEIGHTS[key] for key in pool]
    return random.choices(pool, weights=weights, k=count)


def event_preview(event_type: str, room_index: int, total: int) -> tuple[str, str]:
    """Titel und Beschreibung für einen Raum."""
    label, desc = _EVENT_FLAVOR.get(event_type, ("❓ Unbekannt", "Etwas Unerwartetes …"))
    return f"Raum {room_index + 1}/{total} — {label}", desc


def resolve_room(
    run: DungeonRunRecord,
    *,
    pet_xp_callback: list[int] | None = None,
) -> RoomOutcome:
    """Löst den aktuellen Raum auf."""
    if run.current_room >= run.total_rooms:
        return RoomOutcome("Der Dungeon ist bereits abgeschlossen.", completed=True)

    event = run.events[run.current_room]
    lines: list[str] = []

    if event == DungeonEventType.FIGHT.value:
        if random.random() < 0.4:
            dmg = random.randint(6, 14)
            player_dmg = (dmg + 1) // 2
            pet_dmg = dmg // 2
            run.player_hp = max(0, run.player_hp - player_dmg)
            run.pet_hp = max(0, run.pet_hp - pet_dmg)
            lines.append(f"Der Gegner trifft hart — du **−{player_dmg}**, {pet_dmg} für dein Pet.")
        else:
            gold = random.randint(10, 22)
            run.session_gold += gold
            lines.append(f"Gemeinsam siegt ihr! **+{gold}** Gold.")

    elif event == DungeonEventType.TRAP.value:
        dmg = random.randint(5, 10)
        run.player_hp = max(0, run.player_hp - dmg)
        lines.append(f"Autsch — die Falle kostet dich **{dmg}** HP.")

    elif event == DungeonEventType.TREASURE.value:
        gold = random.randint(15, 30)
        run.session_gold += gold
        lines.append(f"Die Truhe öffnet sich: **+{gold}** Gold!")

    elif event == DungeonEventType.FOUNTAIN.value:
        heal = Config.DUNGEON_FOUNTAIN_HEAL
        run.player_hp = min(run.player_hp + heal, run.player_hp_max)
        run.pet_hp = min(run.pet_hp + heal, run.pet_hp_max)
        lines.append(f"Erfrischend! Ihr tankt **+{heal}** HP auf.")

    elif event == DungeonEventType.GOLD.value:
        gold = random.randint(6, 14)
        run.session_gold += gold
        lines.append(f"Ein schöner Fund: **+{gold}** Gold.")

    elif event == DungeonEventType.PET_XP.value:
        xp = random.randint(12, 22)
        if pet_xp_callback is not None:
            pet_xp_callback.append(xp)
        lines.append(f"Dein Pet saugt die Energie auf — **+{xp}** Pet-XP!")

    run.rooms_cleared += 1
    run.current_room += 1

    if run.player_hp <= 0:
        return RoomOutcome(
            "\n".join(lines + ["**Du brauchst eine Pause** — HP auf 0. Heile dich und versuch's später."]),
            event_type=event,
            failed=True,
        )
    if run.pet_hp <= 0:
        return RoomOutcome(
            "\n".join(lines + ["**Dein Pet ist erschöpft** — kein Tod, nur kurze Erholung."]),
            event_type=event,
            failed=True,
            pet_ko=True,
        )

    if run.current_room >= run.total_rooms:
        bonus = Config.DUNGEON_COMPLETE_GOLD_BONUS
        run.session_gold += bonus
        return RoomOutcome(
            "\n".join(lines + [f"**Geschafft!** Abschlussbonus: **+{bonus}** Gold."]),
            event_type=event,
            completed=True,
        )

    return RoomOutcome("\n".join(lines), event_type=event)


async def finalize_run(
    db: Database,
    bot: commands.Bot,
    member: discord.Member,
    run: DungeonRunRecord,
    economy: PlayerEconomyRecord,
    *,
    outcome: RoomOutcome,
    player_hp_max_value: int,
    channel: discord.TextChannel | discord.Thread | None,
    pet_xp_pending: list[int],
) -> PlayerEconomyRecord:
    """Schreibt Run-Ergebnis zurück und vergibt Belohnungen."""
    now = datetime.now(timezone.utc)
    run.updated_at = now

    if outcome.completed:
        run.status = DungeonRunStatus.COMPLETED.value
        economy.dungeons_completed += 1
        economy.gold += run.session_gold
    elif outcome.failed:
        run.status = DungeonRunStatus.FAILED.value
        partial = max(1, run.session_gold // 2) if run.session_gold else 0
        economy.gold += partial
        run.session_gold = partial
        if outcome.pet_ko:
            economy.pet_recovery_pet_id = run.pet_id
            economy.pet_recovery_until = datetime.fromtimestamp(
                now.timestamp() + Config.DUNGEON_PET_RECOVERY_SECONDS,
                tz=timezone.utc,
            )
    else:
        await db.save_dungeon_run(run)
        return economy

    economy.player_hp = run.player_hp
    economy.player_hp_max = player_hp_max_value
    economy.last_dungeon_at = now
    economy.last_hp_regen_at = now
    await db.save_dungeon_run(run)

    for xp in pet_xp_pending:
        await award_pet_xp(
            bot,
            member,
            xp,
            channel=channel,
            count_interaction=False,
            announce_evolution=True,
        )

    return await db.save_player_economy(economy)
