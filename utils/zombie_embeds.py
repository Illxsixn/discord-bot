"""
Zombie Survival: Embeds für Run, Profil, Shop und Interface.
"""

from __future__ import annotations

import discord

from config import Config
from database.models import PetRecord, PlayerEconomyRecord, ZombiePlayerRecord, ZombieRunRecord
from utils.embeds import info_embed, spaced_lines, success_embed, error_embed
from utils.pet_play import PET_IMPULSES
from utils.levels import progress_bar, xp_progress
from utils.zombie_content import get_zombie, upgrade_lines, wave_intro_text, wave_location
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
        return f"Cooldown: **{run.pet_action_cooldown}** Angriff(e)"
    return "Bonus-Angriff bereit — **Pet-Angriff** öffnet Impuls-Auswahl"


def build_pet_impulse_embed(
    run: ZombieRunRecord,
    pet: PetRecord,
) -> discord.Embed:
    """Separates Fenster zur Impuls-Auswahl für den Pet-Bonusangriff."""
    impulse_fields: list[tuple[str, str, bool]] = []
    for impulse_id, emoji, label in PET_IMPULSES:
        if impulse_id == "focus":
            effect = "Bonus 8–14 · nächster Nahkampf **+50 %**"
        elif impulse_id == "energy":
            effect = "Heilt dich um **20** HP"
        else:
            effect = "Bonus 5–12 · Endbelohnung **+5 %** (max. 25 %)"
        impulse_fields.append((f"{emoji} {label}", effect, True))

    embed = info_embed(
        "Pet-Bonusangriff",
        spaced_lines(
            f"**{pet.name}** greift **zusätzlich** zu deinem Nahkampf an.",
            f"Cooldown danach: **{Config.ZOMBIE_PET_ACTION_COOLDOWN}** Angriffe.",
            "**Wähle einen Impuls unten:**",
        ),
        fields=impulse_fields,
    )
    if run.in_combat and run.current_zombie_key:
        zombie = get_zombie(run.current_zombie_key)
        if zombie:
            embed.add_field(
                name="Ziel",
                value=f"{zombie.emoji} **{zombie.name}** · {format_hp_bar(run.current_zombie_hp, zombie.hp)}",
                inline=False,
            )
    return embed


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
        title = f"Welle {run.wave}/{run.max_waves} · {location}"
        description = wave_intro_text(run.wave, zombie)
    elif run.between_waves:
        title = f"Welle {run.wave}/{run.max_waves} · {location}"
        description = wave_intro_text(run.wave, None)
    else:
        title = f"Welle {run.wave}/{run.max_waves} · {location}"
        description = "Bereit für den nächsten Einsatz."

    player_hp = format_hp_bar(run.player_hp, run.player_max_hp)
    pet_name = pet.name if pet else "—"
    pet_status = _pet_action_label(run, pet)

    fields: list[tuple[str, str, bool]] = [
        ("HP", player_hp, True),
        ("Gold", f"**{economy.gold:,}** 🪙", True),
        ("Run-Punkte", f"**{run.run_gold}**", True),
        ("Level", f"**{player_level}**", True),
        (f"Pet · {pet_name}", pet_status, True),
        ("Upgrades", upgrade_lines(), True),
    ]

    if run.in_combat and zombie:
        special = "Spezialangriff möglich" if zombie.is_boss else (
            "Doppelangriff möglich" if zombie.double_attack_chance else "Standardangriff"
        )
        fields.extend(
            [
                ("Gegner", f"{zombie.emoji} **{zombie.name}**", True),
                ("Zombie-HP", format_hp_bar(run.current_zombie_hp, zombie.hp), True),
                ("Angriff", f"**{zombie.attack}** · {special}", True),
            ]
        )

    embed = info_embed(title, description, fields=fields)

    if run.last_action_text:
        embed.add_field(name="Letzte Aktion", value=run.last_action_text[:1024], inline=False)

    embed.set_footer(text="Kein Abbrechen — Run endet durch Sieg, Niederlage oder 12h Inaktivität")
    return embed


def build_victory_embed(
    run: ZombieRunRecord,
    rewards: RunRewards,
) -> discord.Embed:
    """Run abgeschlossen — Sieg."""
    embed = success_embed(
        "🏆 Run abgeschlossen",
        "Du hast alle Wellen überlebt und den Seuchenbrecher besiegt!",
        fields=[
            ("Wellen", f"**{run.max_waves}/{run.max_waves}**", True),
            ("Boss besiegt", "Ja", True),
            ("Schaden", f"**{run.total_damage:,}**", True),
            ("Gold", f"**+{rewards.gold:,}** 🪙", True),
            ("XP", f"**+{rewards.player_xp:,}**", True),
            ("Pet-XP", f"**+{rewards.pet_xp:,}**", True),
        ],
    )
    if rewards.luck_bonus_percent:
        embed.add_field(
            name="Glück-Bonus",
            value=f"**+{rewards.luck_bonus_percent} %** auf Belohnungen",
            inline=False,
        )
    return embed


def build_defeat_embed(
    run: ZombieRunRecord,
    rewards: RunRewards,
) -> discord.Embed:
    """Niederlage."""
    embed = error_embed(
        "💀 Überrannt",
        f"Du wurdest in **Welle {run.wave}** besiegt.",
        fields=[
            ("Gold", f"**+{rewards.gold:,}** 🪙 (Trost)", True),
            ("XP", f"**+{rewards.player_xp:,}**", True),
            ("Pet-XP", f"**+{rewards.pet_xp:,}**", True),
        ],
    )
    embed.add_field(
        name="Tipp",
        value="Nutze **Pet-Angriff** für Bonus-Schaden — Fokus, Power oder Glück wählen.",
        inline=False,
    )
    return embed


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
    current, needed, percent = xp_progress(profile.xp, profile.level)
    pet_line = f"**{pet.name}** ({pet.species})" if pet else "Kein aktives Pet"

    embed = info_embed(
        f"Zombie Survival — {member.display_name}",
        member.mention,
        fields=[
            (
                "Profil",
                "\n".join(
                    [
                        f"**Level:** {profile.level} · `{progress_bar(percent, 10)}` **{percent} %**",
                        f"**XP:** {profile.xp:,} ({current:,}/{needed:,} bis Level {profile.level + 1})",
                        f"**Gold:** {economy.gold:,} 🪙",
                        f"**Höchste Welle:** {profile.highest_wave}/{Config.ZOMBIE_MAX_WAVES}",
                    ]
                ),
                False,
            ),
            (
                "Statistik",
                "\n".join(
                    [
                        f"**Zombie-Kills:** {profile.total_kills:,}",
                        f"**Boss-Kills:** {profile.boss_kills:,}",
                        f"**Runs:** {profile.runs_completed} Siege · {profile.runs_failed} Niederlagen",
                    ]
                ),
                False,
            ),
            ("Aktives Pet", pet_line, False),
            ("Perks", upgrade_lines(), False),
        ],
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text="Spieler-Level weiterhin unter /levels level")
    return embed


def build_between_waves_embed(
    run: ZombieRunRecord,
    economy: PlayerEconomyRecord,
) -> discord.Embed:
    """Pause zwischen Wellen — nur Zombie-Perks, kein Shop-Inventar."""
    return info_embed(
        "⏸️ Wellenpause",
        f"Welle **{run.wave}/{run.max_waves}** geschafft. Atme durch, bevor es weitergeht.",
        fields=[
            ("HP", format_hp_bar(run.player_hp, run.player_max_hp), True),
            ("Gold", f"**{economy.gold:,}** 🪙", True),
            ("Perks", upgrade_lines(), False),
            (
                "Shop",
                "Lootboxen & kaufbare Produkte nur unter **`/shop`**.",
                False,
            ),
        ],
    )


def build_interface_embed(economy: PlayerEconomyRecord) -> discord.Embed:
    """Steuerzentrale."""
    return info_embed(
        "🎮 Zombie Survival — Interface",
        "Schnellzugriff auf Profil, Status und Shop.",
        fields=[
            ("Gold", f"**{economy.gold:,}** 🪙", True),
            (
                "Befehle",
                "`/zombies start` · `/zombies status` · `/zombies profil` · `/shop`",
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
        f"🧟 **Zombie-Level:** {profile.level} · Höchste Welle: **{profile.highest_wave}**",
        f"💀 **Kills:** {profile.total_kills} · **Boss:** {profile.boss_kills}",
    ]
    if cooldown:
        lines.append(f"⏳ **Cooldown:** {cooldown // 60}:{cooldown % 60:02d}")
    lines.append("\nStarte einen Run mit **`/zombies start`**.")
    return info_embed(f"Zombie Survival — {member.display_name}", "\n".join(lines))


def build_help_embed() -> discord.Embed:
    """Kurze Modus-Erklärung."""
    return info_embed(
        "🧟 Zombie Survival",
        "Wellenbasiertes Survival-RPG mit Gold, Pets und Bosskampf.",
        fields=[
            (
                "Ablauf",
                "1. `/zombies start` · 2. Nahkampf & **Pet-Angriff** · "
                "3. Wellenpause & **`/shop`** · 4. Boss in Welle 3",
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
