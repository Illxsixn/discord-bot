"""
Konfigurationsmodul für den Discord-Bot.

Lädt Umgebungsvariablen aus einer .env-Datei und stellt zentrale
Einstellungen für den gesamten Bot bereit.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Basisverzeichnis des Projekts (Ordner, in dem config.py liegt)
BASE_DIR: Path = Path(__file__).resolve().parent

# .env-Datei laden (falls vorhanden)
load_dotenv(BASE_DIR / ".env")


def _safe_int(value: str | None, default: int | None = None) -> int | None:
    """Parst eine Ganzzahl aus Umgebungsvariablen ohne Import-Absturz."""
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


class Config:
    """Zentrale Bot-Konfiguration aus Umgebungsvariablen."""

    # Discord Bot Token – Pflichtfeld für den Start
    DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")

    # Optional: Owner-ID für erweiterte Bot-Befehle
    OWNER_ID: int | None = (
        _safe_int(os.getenv("OWNER_ID")) if os.getenv("OWNER_ID") else None
    )

    # Logging-Stufe (DEBUG, INFO, WARNING, ERROR)
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    # Pfad zur SQLite-Datenbank
    DATABASE_PATH: Path = BASE_DIR / "database.db"

    # Marken-Signatur in Embeds
    BOT_BRAND_NAME: str = "Anarchy"
    BOT_BRAND_ICON_PATH: Path = BASE_DIR / "assets" / "anarchy_icon.png"

    # Standard-Farben für Embeds (Discord-Farbcodes)
    COLOR_SUCCESS: int = 0x2ECC71  # Grün
    COLOR_ERROR: int = 0xE74C3C  # Rot
    COLOR_WARNING: int = 0xF1C40F  # Gelb
    COLOR_INFO: int = 0x3498DB  # Blau
    COLOR_ARTWORK: int = 0x2D1B4E  # Dunkel-Lila (Standard-Inhalts-Embeds)

    # Cooldown in Sekunden für wiederholte Slash-Commands
    DEFAULT_COOLDOWN: float = 3.0
    EMOJI_USER_COOLDOWN: float = 30.0
    EMOJI_RESPONSE_TIMEOUT: float = 60.0

    # Maximale Anzahl gespeicherter Warnungen pro User (0 = unbegrenzt)
    MAX_WARNINGS_DISPLAY: int = 25

    # Level-System Standardwerte
    XP_PER_MESSAGE: int = 5
    LEVEL_XP_COOLDOWN: int = 10
    LEVEL_LEADERBOARD_LIMIT: int = 10
    GAME_WIN_XP: int = 25
    GAME_WIN_GOLD_MIN: int = 5
    GAME_WIN_GOLD_MAX: int = 15

    # Lootbox & Gold
    LOOTBOX_PRICE: int = 75
    LOOTBOX_XP_CHANCE_MIN: int = 5
    LOOTBOX_XP_CHANCE_MAX: int = 30
    LOOTBOX_XP_MIN: int = 1
    LOOTBOX_XP_MAX: int = 80
    LOOTBOX_CONSOLATION_GOLD_MIN: int = 5
    LOOTBOX_CONSOLATION_GOLD_MAX: int = 12
    LOOTBOX_CONSOLATION_XP_MIN: int = 4
    LOOTBOX_CONSOLATION_XP_MAX: int = 12
    LOOTBOX_INVENTORY_MAX: int = 10
    LOOTBOX_BATCH_MAX: int = 10
    LOOTBOX_BUY_OPTIONS: tuple[int, ...] = (1, 5, 10)
    LOOTBOX_LEADERBOARD_LIMIT: int = 10

    # Zombie Survival (Gold über Runs — Lootboxen unverändert)
    ZOMBIE_MAX_WAVES: int = 3
    ZOMBIE_RUN_COOLDOWN: int = 1800
    ZOMBIE_RUN_INACTIVITY: int = 43200
    ZOMBIE_VIEW_TIMEOUT: float = 43200.0
    ZOMBIE_PLAYER_HP_BASE: int = 105
    ZOMBIE_BETWEEN_WAVE_HEAL_PERCENT: int = 32
    ZOMBIE_PET_ACTION_COOLDOWN: int = 2
    ZOMBIE_PET_ACTION_COOLDOWN_EPIC: int = 3
    ZOMBIE_PET_ACTION_COOLDOWN_LEGENDARY: int = 4
    ZOMBIE_PET_ENERGY_HEAL: int = 20
    ZOMBIE_PET_FOCUS_DAMAGE_MULTIPLIER: float = 2.0
    # Multiplikatoren (HP, Angriff) wenn ein Pet den Run begleitet — Legendary = härtere Horde
    ZOMBIE_PET_DIFFICULTY_HP: dict[str, float] = {
        "gewöhnlich": 1.0,
        "ungewöhnlich": 1.0,
        "selten": 1.05,
        "episch": 1.12,
        "legendär": 1.35,
    }
    ZOMBIE_PET_DIFFICULTY_ATTACK: dict[str, float] = {
        "gewöhnlich": 1.0,
        "ungewöhnlich": 1.0,
        "selten": 1.05,
        "episch": 1.10,
        "legendär": 1.28,
    }
    ZOMBIE_ACTION_COOLDOWN: float = 1.5
    ZOMBIE_LUCK_BONUS_PERCENT: int = 5
    ZOMBIE_LUCK_BONUS_MAX: int = 25
    ZOMBIE_LEADERBOARD_LIMIT: int = 10
    ZOMBIE_ASSETS_DIR: Path = BASE_DIR / "assets" / "zombies"
    ZOMBIE_ASSET_PROMPT_VERSION: int = 1
    ZOMBIE_GIF_FRAME_COUNT: int = 4
    ZOMBIE_GIF_FRAME_MS: int = 450
    ZOMBIE_GIF_OUTPUT_SIZE: int = 512
    ZOMBIE_GIF_VARIANTS_COMMON: int = 1
    ZOMBIE_GIF_VARIANTS_FAST: int = 1
    ZOMBIE_VICTORY_GOLD_MIN: int = 80
    ZOMBIE_VICTORY_GOLD_MAX: int = 180
    ZOMBIE_DEFEAT_GOLD_MIN: int = 10
    ZOMBIE_DEFEAT_GOLD_MAX: int = 50
    ZOMBIE_VICTORY_XP_MIN: int = 80
    ZOMBIE_VICTORY_XP_MAX: int = 220
    ZOMBIE_DEFEAT_XP_MIN: int = 20
    ZOMBIE_DEFEAT_XP_MAX: int = 60
    ZOMBIE_VICTORY_PET_XP_MIN: int = 20
    ZOMBIE_VICTORY_PET_XP_MAX: int = 35
    ZOMBIE_DEFEAT_PET_XP: int = 5

    # Slot-Maschine
    SLOT_BET_OPTIONS: tuple[int, ...] = (5, 10, 25, 50)
    SLOT_DEFAULT_BET: int = 10
    SLOT_VIEW_TIMEOUT: float = 180.0
    SLOT_TARGET_RTP: float = 0.75
    SLOT_BET_UNIT: int = 5
    SLOT_PAIR_PAYOUT_PER_5_GOLD: int = 2
    SLOT_JACKPOT_MIN_MULTIPLIER: int = 20
    SLOT_JACKPOT_CHANCE: float = 0.10
    SLOT_SPIN_ANIMATION_STEPS: int = 3
    SLOT_SPIN_ANIMATION_DELAY: float = 0.45

    # Embed-Nachrichten: Auto-Löschung nach Sekunden (0 = aus)
    EMBED_AUTO_DELETE_SECONDS: int = 300

    CHALLENGE_XP_MIN: int = 15
    CHALLENGE_XP_MAX: int = 40
    CHALLENGE_PET_XP_MIN: int = 20
    CHALLENGE_PET_XP_MAX: int = 50
    CHALLENGE_GENERATION_VERSION: int = 4
    DAILY_CHALLENGE_COUNT: int = 4
    DAILY_PET_CHALLENGE_COUNT: int = 2
    CHALLENGE_MESSAGE_TARGETS: tuple[int, ...] = (30, 35, 40, 45, 50, 55, 60, 65, 70)
    POLL_MAX_OPTIONS: int = 10
    GIVEAWAY_MAX_WINNERS: int = 20
    COMMUNITY_TASK_INTERVAL: float = 30.0

    # Pet-System
    PET_XP_ACTIVITY_MIN: int = 2
    PET_XP_ACTIVITY_MAX: int = 5
    PET_XP_ACTIVITY_COOLDOWN: int = 10
    PET_XP_PLAY_BASE_MIN: int = 8
    PET_XP_PLAY_BASE_MAX: int = 14
    PET_XP_PLAY_HIT_BONUS: int = 3
    PET_XP_GAME_MIN: int = 2
    PET_XP_GAME_MAX: int = 5
    PET_EGG_COOLDOWN: int = 86400
    PET_DUPLICATE_PET_XP: int = 25
    PET_DUPLICATE_PLAYER_XP: int = 25
    PET_PLAY_COOLDOWN: int = 300  # 5 Minuten
    PET_RENAME_COOLDOWN: int = 604800
    PET_NAME_MAX_LENGTH: int = 15
    PET_LEADERBOARD_LIMIT: int = 10
    PET_EVOLUTION_TEEN: int = 10
    PET_EVOLUTION_ADULT: int = 25
    PET_EVOLUTION_LEGENDARY: int = 50
    PET_IMAGE_DIR: Path = BASE_DIR / "assets" / "pets"
    PET_PORTRAIT_PROMPT_VERSION: int = 4
    AGNES_API_KEY: str = os.getenv("AGNES_API_KEY", "")
    AGNES_API_URL: str = os.getenv(
        "AGNES_API_URL",
        "https://apihub.agnes-ai.com/v1/images/generations",
    )
    AGNES_IMAGE_MODEL: str = os.getenv("AGNES_IMAGE_MODEL", "agnes-image-2.1-flash")
    AGNES_IMAGE_SIZE: str = os.getenv("AGNES_IMAGE_SIZE", "1024x1024")
    AGNES_REQUEST_TIMEOUT: int = _safe_int(os.getenv("AGNES_REQUEST_TIMEOUT"), 120) or 120

    @classmethod
    def validate(cls) -> None:
        """
        Prüft, ob alle Pflichtkonfigurationen gesetzt sind.

        Raises:
            ValueError: Wenn der Discord-Token fehlt oder ungültig ist.
        """
        if not cls.DISCORD_TOKEN or cls.DISCORD_TOKEN == "dein_bot_token_hier":
            raise ValueError(
                "DISCORD_TOKEN fehlt oder ist nicht gesetzt.\n"
                "Kopiere .env nach .env und trage deinen Bot-Token ein."
            )
