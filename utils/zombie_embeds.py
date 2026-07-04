"""
Zombie Survival: Embeds für Run, Profil, Shop und Interface.
"""

from __future__ import annotations

import discord

from config import Config
from database.models import PetRecord, PlayerEconomyRecord, ZombiePlayerRecord, ZombieRunRecord
from utils.embeds import info_embed, success_embed, error_embed, apply_brand_footer, spaced_lines
from utils.levels import progress_bar
from utils.zombie_combat import pet_action_cooldown_attacks
from utils.zombie_content import get_zombie, melee_base_damage, scaled_zombie_attack, wave_intro_text, wave_location
from utils.zombie_rewards import RunRewards


def format_hp_bar(current: int, maximum: int) -> str:
    """HP mit Mini-Balken."""
    if maximum <= 0:
        return f"**{current}** HP"
    pct = min(int((current / maximum) * 100), 100)
    return f"`{progress_bar(pct, 8)}` **{current}** / **{maximum}** HP"


def _pet_action_label(run: ZombieRunRecord, pet: PetRecord | None) -> str:
    if pet is None:
        return "Kein Pet — deaktiviert"
    if run.pet_action_cooldown > 0:
        attacks = run.pet_action_cooldown
        label = "Angriff" if attacks == 1 else "Angriffe"
        return f"Cooldown: **{attacks}** {label} (Nahkampf)"
    return "🎯 Fokus · ⚡ Energie · 🍀 Glück — wähle im Menü"


def build_run_embed(
    run: ZombieRunRecord,
    *,
    pet: PetRecord | None,
    economy: PlayerEconomyRecord,
    player_level: int,
) -> discord.Embed:
    """Aktiver Run — Kampf oder zwischen Wellen."""
    location = wave_location(run.wave)
    zombie = get_zombie(run.current_zombie_key)

    if run.in_combat and zombie:
        title = f"🧟 Welle {run.wave}/{run.max_waves} · {location}"
        description = wave_intro_text(run.wave, zombie)
    else:
        title = f"🧟 Welle {run.wave}/{run.max_waves} · {location}"
        description = "Bereit für den nächsten Einsatz."

    fields: list[tuple[str, str, bool]] = [
        (
            "Spieler",
            "\n".join(
                [
                    f"❤️ HP: {format_hp_bar(run.player_hp, run.player_max_hp)}",
                    f"🪙 Gold: **{economy.gold:,}** · Run-Punkte: **{run.run_gold}**",
                    f"⚔️ Nahkampf: **{melee_base_damage(player_level)}**",
                ]
            ),
            False,
        ),
    ]

    if run.in_combat and zombie:
        zombie_max_hp = run.current_zombie_max_hp or zombie.hp
        attack_value = scaled_zombie_attack(zombie, run.companion_rarity or None)
        special = "Spezialangriff möglich" if zombie.is_boss else (
            "Doppelangriff möglich" if zombie.double_attack_chance else "Standardangriff"
        )
        fields.append(
            (
                "Gegner",
                "\n".join(
                    [
                        f"{zombie.emoji} **{zombie.name}**",
                        f"❤️ HP: {format_hp_bar(run.current_zombie_hp, zombie_max_hp)}",
                        f"⚔️ Angriff: **{attack_value}** · {special}",
                    ]
                ),
                False,
            )
        )

    pet_name = pet.name if pet else "—"
    fields.append((f"🐾 {pet_name}", _pet_action_label(run, pet), False))

    if run.last_action_text:
        fields.append(("Letzte Aktion", run.last_action_text[:1024], False))

    embed = info_embed(title, description, fields=fields)
    apply_brand_footer(
        embed,
        prefix="Kein Abbrechen — Run endet durch Sieg, Niederlage oder 12h Inaktivität",
        with_icon=False,
    )
    return embed


def build_pet_action_picker_embed(pet: PetRecord, *, companion_rarity: str = "") -> discord.Embed:
    """Separates Menü zur Auswahl der Pet-Spezialaktion im Kampf."""
    cooldown = pet_action_cooldown_attacks(companion_rarity or None)
    return info_embed(
        f"🐾 Pet-Aktion — {pet.name}",
        "Wähle **eine** Spezialaktion für diesen Kampfzug.",
        fields=[
            ("🎯 Fokus", "Nächster Nahkampf **+100 %** Schaden", True),
            ("⚡ Energie", f"Sofort-Schaden + **{Config.ZOMBIE_PET_ENERGY_HEAL}** HP Heilung", True),
            (
                "🍀 Glück",
                f"Endbonus **+{Config.ZOMBIE_LUCK_BONUS_PERCENT} %** "
                f"(max. **{Config.ZOMBIE_LUCK_BONUS_MAX} %**)",
                True,
            ),
            (
                "Cooldown",
                f"**{cooldown}** Nahkampf-Angriffe nach der Aktion",
                False,
            ),
        ],
    )


def build_victory_embed(
    run: ZombieRunRecord,
    rewards: RunRewards,
) -> discord.Embed:
    """Run abgeschlossen — Sieg."""
    fields: list[tuple[str, str, bool]] = [
        ("Wellen", f"**{run.max_waves}/{run.max_waves}**", True),
        ("Boss besiegt", "Ja", True),
        ("Schaden", f"**{run.total_damage:,}**", True),
        ("Gold", f"**+{rewards.gold:,}** 🪙", True),
        ("XP", f"**+{rewards.player_xp:,}**", True),
        ("Pet-XP", f"**+{rewards.pet_xp:,}**", True),
    ]
    if rewards.luck_bonus_percent:
        fields.append(
            (
                "Glück-Bonus",
                f"**+{rewards.luck_bonus_percent} %** auf Belohnungen",
                False,
            )
        )

    return success_embed(
        "🏆 Run abgeschlossen",
        "Du hast alle Wellen überlebt und den Seuchenbrecher besiegt!",
        fields=fields,
    )


def build_defeat_embed(
    run: ZombieRunRecord,
    rewards: RunRewards,
) -> discord.Embed:
    """Niederlage."""
    return error_embed(
        "💀 Überrannt",
        f"Du wurdest in **Welle {run.wave}** besiegt.",
        fields=[
            ("Gold", f"**+{rewards.gold:,}** 🪙 (Trost)", True),
            ("XP", f"**+{rewards.player_xp:,}**", True),
            ("Pet-XP", f"**+{rewards.pet_xp:,}**", True),
            (
                "Tipp",
                "Nutze Pet-Aktion clever — Fokus, Power oder Glück je nach Impuls.",
                False,
            ),
        ],
    )


def build_expired_embed() -> discord.Embed:
    """12-Stunden-Inaktivität."""
    return error_embed(
        "Run zusammengebrochen",
        "Dein Run ist nach **12 Stunden** Inaktivität zusammengebrochen.\n"
        "Du erhältst eine kleine Trostbelohnung (Gold & XP).\n"
        f"Cooldown: **{Config.ZOMBIE_RUN_COOLDOWN // 60} Minuten** — dann `/zombies start`.",
    )


def build_profile_embed(
    profile: ZombiePlayerRecord,
    economy: PlayerEconomyRecord,
    pet: PetRecord | None,
    member: discord.Member,
) -> discord.Embed:
    """Permanentes Zombie-Profil."""
    pet_line = f"**{pet.name}** ({pet.species})" if pet else "Kein aktives Pet"

    embed = info_embed(
        f"Zombie Survival — {member.display_name}",
        member.mention,
        fields=[
            (
                "Profil",
                spaced_lines(
                    f"**Gold:** {economy.gold:,} 🪙",
                    f"**Höchste Welle:** {profile.highest_wave}/{Config.ZOMBIE_MAX_WAVES}",
                ),
                False,
            ),
            (
                "Statistik",
                spaced_lines(
                    f"**Zombie-Kills:** {profile.total_kills:,}",
                    f"**Boss-Kills:** {profile.boss_kills:,}",
                    f"**Runs:** {profile.runs_completed} Siege · {profile.runs_failed} Niederlagen",
                ),
                False,
            ),
            ("Aktives Pet", pet_line, False),
        ],
        thumbnail=member.display_avatar.url,
    )
    apply_brand_footer(embed, prefix="Spieler-Level weiterhin unter /levels level")
    return embed


def build_interface_embed(economy: PlayerEconomyRecord) -> discord.Embed:
    """Steuerzentrale."""
    return info_embed(
        "🎮 Zombie Survival — Interface",
        "Schnellzugriff auf Profil, Status und Shop.",
        fields=[
            ("Gold", f"**{economy.gold:,}** 🪙", True),
            (
                "Befehle",
                "`/zombies start` · `/zombies resume` · `/zombies profil` · `/shop`",
                False,
            ),
        ],
    )


def build_idle_status_embed(
    member: discord.Member,
    economy: PlayerEconomyRecord,
    profile: ZombiePlayerRecord,
    *,
    cooldown: int | None = None,
) -> discord.Embed:
    """Kurzstatus ohne aktiven Run."""
    lines = [
        f"🪙 **Gold:** {economy.gold:,}",
        f"🏆 **Höchste Welle:** {profile.highest_wave}/{Config.ZOMBIE_MAX_WAVES}",
        f"💀 **Kills:** {profile.total_kills} · **Boss:** {profile.boss_kills}",
    ]
    if cooldown:
        lines.append(f"⏳ **Cooldown:** {cooldown // 60}:{cooldown % 60:02d}")
    lines.append("Starte einen Run mit **`/zombies start`**.")
    return info_embed(f"Zombie Survival — {member.display_name}", spaced_lines(*lines))


def build_help_embed() -> discord.Embed:
    """Kurze Modus-Erklärung."""
    return info_embed(
        "🧟 Zombie Survival",
        "Wellenbasiertes Survival-RPG mit Gold, Pets und Bosskampf.",
        fields=[
            (
                "Ablauf",
                "1. `/zombies start` · 2. Nahkampf & Pet-Aktion (Fokus/Glück/Power) · "
                "3. Wellen laufen direkt weiter · Boss in Welle 3",
                False,
            ),
            (
                "Regeln",
                f"**{Config.ZOMBIE_MAX_WAVES} Wellen** · **Kein Abbrechen** · "
                f"**{Config.ZOMBIE_RUN_INACTIVITY // 3600}h** Inaktivität beendet Run · "
                f"**+{Config.ZOMBIE_BETWEEN_WAVE_HEAL_PERCENT} %** HP nach jeder Welle",
                False,
            ),
            (
                "Befehle",
                "`start` · `status` · `profil` · `interface` · `leaderboard` · Shop: **`/shop`**",
                False,
            ),
        ],
    )
