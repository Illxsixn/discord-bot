"""
Datenbankmodelle und Konstanten für den Discord-Bot.

Definiert Tabellennamen, Standardwerte und Hilfsfunktionen für
Guild-Einstellungen sowie Strukturen für Warnungen und Mutes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AutoModPunishment(str, Enum):
    """Mögliche Strafen bei AutoMod-Verstößen."""

    WARN = "warn"
    TIMEOUT = "timeout"
    KICK = "kick"
    BAN = "ban"


# Standard-Nachrichten mit Platzhaltern
DEFAULT_WELCOME_MESSAGE: str = (
    "🎉 Willkommen {user}!\n\n"
    "Du bist Mitglied Nummer **{membercount}** auf **{server}**."
)

DEFAULT_LEAVE_MESSAGE: str = "😢 **{username}** hat den Server verlassen."


@dataclass
class GuildSettings:
    """
    Vollständige Server-Einstellungen aus der SQLite-Datenbank.

    Alle Felder entsprechen den konfigurierbaren Bot-Optionen pro Guild.
    """

    guild_id: int

    # Welcome-System
    welcome_enabled: bool = False
    welcome_channel_id: int | None = None
    welcome_message: str = DEFAULT_WELCOME_MESSAGE
    welcome_use_embed: bool = True
    welcome_show_join_date: bool = True
    welcome_image_enabled: bool = False

    # Leave-System
    leave_enabled: bool = False
    leave_channel_id: int | None = None
    leave_message: str = DEFAULT_LEAVE_MESSAGE
    leave_use_embed: bool = True

    # Log-System
    logs_enabled: bool = False
    logs_channel_id: int | None = None

    # AutoMod
    automod_enabled: bool = False
    spam_protection: bool = False
    invite_blocker: bool = False
    link_blocker: bool = False
    bad_word_filter: bool = False
    bad_words: list[str] = field(default_factory=list)
    automod_punishment: AutoModPunishment = AutoModPunishment.WARN
    automod_timeout_minutes: int = 10

    # Moderation: Mute-Rolle
    mute_role_id: int | None = None

    # Level-System
    levels_enabled: bool = False
    levels_xp_min: int = 15
    levels_xp_max: int = 25
    levels_cooldown: int = 60
    levels_announce_channel_id: int | None = None
    levels_announce_enabled: bool = True

    # Turnier-System
    tournament_channel_id: int | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "GuildSettings":
        """Erstellt GuildSettings aus einem SQLite-Zeilen-Dictionary."""
        bad_words_raw = row.get("bad_words") or "[]"
        try:
            import json

            bad_words = json.loads(bad_words_raw)
        except (json.JSONDecodeError, TypeError):
            bad_words = []

        punishment_raw = row.get("automod_punishment") or AutoModPunishment.WARN.value
        try:
            punishment = AutoModPunishment(punishment_raw)
        except ValueError:
            punishment = AutoModPunishment.WARN

        return cls(
            guild_id=row["guild_id"],
            welcome_enabled=bool(row.get("welcome_enabled", 0)),
            welcome_channel_id=row.get("welcome_channel_id"),
            welcome_message=row.get("welcome_message") or DEFAULT_WELCOME_MESSAGE,
            welcome_use_embed=bool(row.get("welcome_use_embed", 1)),
            welcome_show_join_date=bool(row.get("welcome_show_join_date", 1)),
            welcome_image_enabled=bool(row.get("welcome_image_enabled", 0)),
            leave_enabled=bool(row.get("leave_enabled", 0)),
            leave_channel_id=row.get("leave_channel_id"),
            leave_message=row.get("leave_message") or DEFAULT_LEAVE_MESSAGE,
            leave_use_embed=bool(row.get("leave_use_embed", 1)),
            logs_enabled=bool(row.get("logs_enabled", 0)),
            logs_channel_id=row.get("logs_channel_id"),
            automod_enabled=bool(row.get("automod_enabled", 0)),
            spam_protection=bool(row.get("spam_protection", 0)),
            invite_blocker=bool(row.get("invite_blocker", 0)),
            link_blocker=bool(row.get("link_blocker", 0)),
            bad_word_filter=bool(row.get("bad_word_filter", 0)),
            bad_words=bad_words,
            automod_punishment=punishment,
            automod_timeout_minutes=int(row.get("automod_timeout_minutes") or 10),
            mute_role_id=row.get("mute_role_id"),
            levels_enabled=bool(row.get("levels_enabled", 0)),
            levels_xp_min=int(row.get("levels_xp_min") or 15),
            levels_xp_max=int(row.get("levels_xp_max") or 25),
            levels_cooldown=int(row.get("levels_cooldown") or 60),
            levels_announce_channel_id=row.get("levels_announce_channel_id"),
            levels_announce_enabled=bool(row.get("levels_announce_enabled", 1)),
            tournament_channel_id=row.get("tournament_channel_id"),
        )


class PollType(str, Enum):
    """Typ einer Umfrage."""

    YES_NO = "yes_no"
    MULTI = "multi"


@dataclass
class UserLevelRecord:
    """XP- und Level-Daten eines Nutzers."""

    guild_id: int
    user_id: int
    xp: int
    level: int
    last_xp_at: datetime | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "UserLevelRecord":
        last_xp = row.get("last_xp_at")
        last_xp_at = datetime.fromisoformat(last_xp) if isinstance(last_xp, str) and last_xp else None
        return cls(
            guild_id=row["guild_id"],
            user_id=row["user_id"],
            xp=int(row.get("xp") or 0),
            level=int(row.get("level") or 1),
            last_xp_at=last_xp_at,
        )


@dataclass
class PlayerEconomyRecord:
    """Gold und Lootbox-Inventar pro Guild."""

    guild_id: int
    user_id: int
    gold: int = 0
    lootbox_count: int = 0

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "PlayerEconomyRecord":
        return cls(
            guild_id=row["guild_id"],
            user_id=row["user_id"],
            gold=int(row.get("gold") or 0),
            lootbox_count=int(row.get("lootbox_count") or 0),
        )


class ZombieRunStatus(str, Enum):
    """Status eines Zombie-Survival-Laufs."""

    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class ZombieCooldownType(str, Enum):
    """Cooldown-Typen für Zombie Survival."""

    RUN = "run"


@dataclass
class ZombiePlayerRecord:
    """Permanentes Zombie-Survival-Profil pro Guild."""

    guild_id: int
    user_id: int
    highest_wave: int = 0
    total_kills: int = 0
    boss_kills: int = 0
    runs_completed: int = 0
    runs_failed: int = 0
    perks_json: str = "{}"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "ZombiePlayerRecord":
        created = row.get("created_at")
        updated = row.get("updated_at")
        return cls(
            guild_id=row["guild_id"],
            user_id=row["user_id"],
            highest_wave=int(row.get("highest_wave") or 0),
            total_kills=int(row.get("total_kills") or 0),
            boss_kills=int(row.get("boss_kills") or 0),
            runs_completed=int(row.get("runs_completed") or 0),
            runs_failed=int(row.get("runs_failed") or 0),
            perks_json=row.get("perks_json") or "{}",
            created_at=datetime.fromisoformat(created) if isinstance(created, str) else datetime.now(timezone.utc),
            updated_at=datetime.fromisoformat(updated) if isinstance(updated, str) else datetime.now(timezone.utc),
        )


@dataclass
class ZombieRunRecord:
    """Laufender oder abgeschlossener Zombie-Survival-Run."""

    id: int
    guild_id: int
    user_id: int
    status: str
    wave: int
    max_waves: int
    player_hp: int
    player_max_hp: int
    created_at: datetime
    updated_at: datetime
    channel_id: int | None = None
    message_id: int | None = None
    run_gold: int = 0
    current_zombie_key: str | None = None
    current_zombie_hp: int = 0
    zombies_remaining: int = 0
    pet_action_cooldown: int = 0
    luck_bonus_uses: int = 0
    focus_active: int = 0
    total_damage: int = 0
    last_action_text: str = ""
    shop_available: int = 0

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "ZombieRunRecord":
        created = row.get("created_at")
        updated = row.get("updated_at")
        return cls(
            id=int(row["id"]),
            guild_id=row["guild_id"],
            user_id=row["user_id"],
            channel_id=row.get("channel_id"),
            message_id=row.get("message_id"),
            status=row.get("status") or ZombieRunStatus.ACTIVE.value,
            wave=int(row.get("wave") or 1),
            max_waves=int(row.get("max_waves") or 3),
            player_hp=int(row.get("player_hp") or 0),
            player_max_hp=int(row.get("player_max_hp") or 0),
            run_gold=int(row.get("run_gold") or 0),
            current_zombie_key=row.get("current_zombie_key"),
            current_zombie_hp=int(row.get("current_zombie_hp") or 0),
            zombies_remaining=int(row.get("zombies_remaining") or 0),
            pet_action_cooldown=int(row.get("pet_action_cooldown") or 0),
            luck_bonus_uses=int(row.get("luck_bonus_uses") or 0),
            focus_active=int(row.get("focus_active") or 0),
            total_damage=int(row.get("total_damage") or 0),
            last_action_text=row.get("last_action_text") or "",
            shop_available=int(row.get("shop_available") or 0),
            created_at=datetime.fromisoformat(created) if isinstance(created, str) else datetime.now(timezone.utc),
            updated_at=datetime.fromisoformat(updated) if isinstance(updated, str) else datetime.now(timezone.utc),
        )

    @property
    def in_combat(self) -> bool:
        """True wenn ein Zombie aktiv ist."""
        return bool(self.current_zombie_key) and self.current_zombie_hp > 0

    @property
    def between_waves(self) -> bool:
        """True zwischen Wellen (Wellenpause erlaubt)."""
        return not self.in_combat and self.shop_available == 1


@dataclass
class ReactionRoleRecord:
    """Reaktionsrolle an eine Nachricht gebunden."""

    id: int
    guild_id: int
    channel_id: int
    message_id: int
    emoji: str
    role_id: int
    created_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "ReactionRoleRecord":
        created = row.get("created_at")
        created_at = datetime.fromisoformat(created) if isinstance(created, str) else datetime.utcnow()
        return cls(
            id=row["id"],
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            message_id=row["message_id"],
            emoji=row["emoji"],
            role_id=row["role_id"],
            created_at=created_at,
        )


@dataclass
class PollRecord:
    """Gespeicherte Umfrage."""

    id: int
    guild_id: int
    channel_id: int
    message_id: int
    question: str
    poll_type: PollType
    options: list[str]
    ends_at: datetime | None
    ended: bool
    creator_id: int
    created_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "PollRecord":
        import json

        options_raw = row.get("options_json") or "[]"
        try:
            options = json.loads(options_raw)
        except (json.JSONDecodeError, TypeError):
            options = []

        poll_type_raw = row.get("poll_type") or PollType.YES_NO.value
        try:
            poll_type = PollType(poll_type_raw)
        except ValueError:
            poll_type = PollType.YES_NO

        ends_raw = row.get("ends_at")
        ends_at = datetime.fromisoformat(ends_raw) if isinstance(ends_raw, str) and ends_raw else None
        created_raw = row.get("created_at")
        created_at = datetime.fromisoformat(created_raw) if isinstance(created_raw, str) else datetime.utcnow()

        return cls(
            id=row["id"],
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            message_id=row["message_id"],
            question=row["question"],
            poll_type=poll_type,
            options=options,
            ends_at=ends_at,
            ended=bool(row.get("ended", 0)),
            creator_id=row["creator_id"],
            created_at=created_at,
        )


@dataclass
class GiveawayRecord:
    """Gespeichertes Gewinnspiel."""

    id: int
    guild_id: int
    channel_id: int
    message_id: int
    prize: str
    winner_count: int
    emoji: str
    ends_at: datetime
    ended: bool
    creator_id: int
    winner_ids: list[int]
    created_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "GiveawayRecord":
        import json

        winners_raw = row.get("winner_ids_json") or "[]"
        try:
            winner_ids = [int(x) for x in json.loads(winners_raw)]
        except (json.JSONDecodeError, TypeError, ValueError):
            winner_ids = []

        ends_at = datetime.fromisoformat(row["ends_at"]) if row.get("ends_at") else datetime.now(timezone.utc)
        if ends_at.tzinfo is None:
            ends_at = ends_at.replace(tzinfo=timezone.utc)
        created_raw = row.get("created_at")
        created_at = datetime.fromisoformat(created_raw) if isinstance(created_raw, str) else datetime.now(timezone.utc)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        return cls(
            id=row["id"],
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            message_id=row["message_id"],
            prize=row["prize"],
            winner_count=int(row.get("winner_count") or 1),
            emoji=row.get("emoji") or "🎉",
            ends_at=ends_at,
            ended=bool(row.get("ended", 0)),
            creator_id=row["creator_id"],
            winner_ids=winner_ids,
            created_at=created_at,
        )


@dataclass
class WarningRecord:
    """Einzelner Warn-Eintrag in der Datenbank."""

    id: int
    guild_id: int
    user_id: int
    moderator_id: int
    reason: str
    created_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "WarningRecord":
        """Erstellt WarningRecord aus einer SQLite-Zeile."""
        created = row.get("created_at")
        if isinstance(created, str):
            created_at = datetime.fromisoformat(created)
        else:
            created_at = datetime.utcnow()

        return cls(
            id=row["id"],
            guild_id=row["guild_id"],
            user_id=row["user_id"],
            moderator_id=row["moderator_id"],
            reason=row.get("reason") or "Kein Grund angegeben",
            created_at=created_at,
        )


class ChallengeType(str, Enum):
    """Typ einer täglichen Aufgabe."""

    MESSAGES = "messages"
    ACTIVE = "active"
    REACTIONS = "reactions"
    COMMANDS = "commands"
    PET_PLAY = "pet_play"
    PET_INFO = "pet_info"
    PET_ACTIVITY = "pet_activity"


PET_CHALLENGE_TYPES: frozenset[ChallengeType] = frozenset(
    {
        ChallengeType.PET_PLAY,
        ChallengeType.PET_INFO,
        ChallengeType.PET_ACTIVITY,
    }
)


def is_pet_challenge_type(challenge_type: ChallengeType) -> bool:
    """True wenn die Aufgabe eine Pet-Tagesaufgabe ist."""
    return challenge_type in PET_CHALLENGE_TYPES


class TicketStatus(str, Enum):
    """Status eines Support-Tickets."""

    OPEN = "open"
    CLAIMED = "claimed"
    CLOSED = "closed"


DEFAULT_TICKET_PANEL_TITLE: str = "Support-Tickets"
DEFAULT_TICKET_PANEL_MESSAGE: str = (
    "Brauchst du Hilfe vom Team?\n\n"
    "Klicke auf **{button}**, um einen privaten Kanal zu öffnen.\n"
    "Pro Person ist jeweils **ein offenes Ticket** möglich."
)
DEFAULT_TICKET_WELCOME_MESSAGE: str = (
    "Hallo {user}!\n\n"
    "Beschreibe dein Anliegen — das Team meldet sich so schnell wie möglich.\n\n"
    "Nutze die Buttons unten oder `/ticket close` / `/ticket claim`."
)
DEFAULT_TICKET_PANEL_BUTTON: str = "Ticket erstellen"


@dataclass
class TicketSettings:
    """Ticket-System-Einstellungen pro Server."""

    guild_id: int
    enabled: bool = False
    category_id: int | None = None
    staff_role_id: int | None = None
    log_channel_id: int | None = None
    panel_channel_id: int | None = None
    panel_message_id: int | None = None
    panel_title: str = DEFAULT_TICKET_PANEL_TITLE
    panel_message: str = DEFAULT_TICKET_PANEL_MESSAGE
    welcome_message: str = DEFAULT_TICKET_WELCOME_MESSAGE
    panel_button_label: str = DEFAULT_TICKET_PANEL_BUTTON

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "TicketSettings":
        return cls(
            guild_id=row["guild_id"],
            enabled=bool(row.get("enabled", 0)),
            category_id=row.get("category_id"),
            staff_role_id=row.get("staff_role_id"),
            log_channel_id=row.get("log_channel_id"),
            panel_channel_id=row.get("panel_channel_id"),
            panel_message_id=row.get("panel_message_id"),
            panel_title=row.get("panel_title") or DEFAULT_TICKET_PANEL_TITLE,
            panel_message=row.get("panel_message") or DEFAULT_TICKET_PANEL_MESSAGE,
            welcome_message=row.get("welcome_message") or DEFAULT_TICKET_WELCOME_MESSAGE,
            panel_button_label=row.get("panel_button_label") or DEFAULT_TICKET_PANEL_BUTTON,
        )


@dataclass
class TicketRecord:
    """Einzelnes Support-Ticket."""

    id: int
    guild_id: int
    channel_id: int
    opener_id: int
    claimed_by_id: int | None
    status: TicketStatus
    reason: str | None
    created_at: datetime
    closed_at: datetime | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "TicketRecord":
        created = row.get("created_at")
        created_at = datetime.fromisoformat(created) if isinstance(created, str) else datetime.utcnow()
        closed_raw = row.get("closed_at")
        closed_at = datetime.fromisoformat(closed_raw) if isinstance(closed_raw, str) and closed_raw else None
        return cls(
            id=row["id"],
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            opener_id=row["opener_id"],
            claimed_by_id=row.get("claimed_by_id"),
            status=TicketStatus(row["status"]),
            reason=row.get("reason"),
            created_at=created_at,
            closed_at=closed_at,
        )


@dataclass
class GuessGameRecord:
    """Aktives Zahlenraten-Spiel pro Kanal."""

    guild_id: int
    channel_id: int
    target_number: int
    started_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "GuessGameRecord":
        started = row.get("started_at")
        started_at = datetime.fromisoformat(started) if isinstance(started, str) else datetime.utcnow()
        return cls(
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            target_number=int(row["target_number"]),
            started_at=started_at,
        )


@dataclass
class GuessStatsRecord:
    """Statistiken für Zahlenraten pro Nutzer."""

    guild_id: int
    user_id: int
    games_played: int = 0
    games_won: int = 0
    total_guesses: int = 0
    win_attempts_sum: int = 0
    best_win_attempts: int | None = None
    fastest_win_seconds: int | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "GuessStatsRecord":
        return cls(
            guild_id=row["guild_id"],
            user_id=row["user_id"],
            games_played=int(row.get("games_played") or 0),
            games_won=int(row.get("games_won") or 0),
            total_guesses=int(row.get("total_guesses") or 0),
            win_attempts_sum=int(row.get("win_attempts_sum") or 0),
            best_win_attempts=row.get("best_win_attempts"),
            fastest_win_seconds=row.get("fastest_win_seconds"),
        )

    @property
    def average_win_attempts(self) -> float | None:
        """Durchschnittliche Versuche bei Siegen."""
        if self.games_won <= 0:
            return None
        return self.win_attempts_sum / self.games_won


@dataclass
class ChallengeTask:
    """Einzelne tägliche Aufgabe."""

    type: ChallengeType
    target: int
    key: str = ""
    progress: int = 0
    completed: bool = False
    reward_xp: int = 0
    reward_pet_xp: int = 0

    def __post_init__(self) -> None:
        if not self.key:
            self.key = self.type.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "key": self.key,
            "target": self.target,
            "progress": self.progress,
            "completed": self.completed,
            "reward_xp": self.reward_xp,
            "reward_pet_xp": self.reward_pet_xp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChallengeTask":
        reward_xp_raw = data.get("reward_xp")
        reward_pet_xp_raw = data.get("reward_pet_xp")
        type_raw = str(data["type"])
        if type_raw == "pet":
            type_raw = ChallengeType.PET_PLAY.value
        challenge_type = ChallengeType(type_raw)
        return cls(
            type=challenge_type,
            key=str(data.get("key") or challenge_type.value),
            target=int(data["target"]),
            progress=int(data.get("progress") or 0),
            completed=bool(data.get("completed")),
            reward_xp=int(reward_xp_raw) if reward_xp_raw is not None else 0,
            reward_pet_xp=int(reward_pet_xp_raw) if reward_pet_xp_raw is not None else 0,
        )

    @property
    def label(self) -> str:
        """Deutsche Beschreibung der Aufgabe."""
        labels = {
            ChallengeType.MESSAGES: f"Schreibe **{self.target}** Nachrichten",
            ChallengeType.ACTIVE: "Sei heute aktiv",
            ChallengeType.REACTIONS: f"Reagiere auf **{self.target}** Nachrichten",
            ChallengeType.COMMANDS: f"Nutze **{self.target}** Bot-Befehle",
            ChallengeType.PET_PLAY: f"Spiele **{self.target}**× mit deinem Pet (`/pet play`)",
            ChallengeType.PET_INFO: f"Nutze **`/pet info`** **{self.target}**×",
            ChallengeType.PET_ACTIVITY: (
                f"Sammle **{self.target}**× Pet-Aktivitäts-XP (Nachrichten mit aktivem Pet)"
            ),
        }
        return labels.get(self.type, self.type.value)

    @property
    def reward_text(self) -> str:
        """Belohnungsanzeige für Embeds."""
        if is_pet_challenge_type(self.type):
            return f"**{self.reward_pet_xp} Pet-XP**"
        return f"**{self.reward_xp} XP**"


class PetRarity(str, Enum):
    """Seltenheit eines Pet-Typs."""

    COMMON = "gewöhnlich"
    UNCOMMON = "ungewöhnlich"
    RARE = "selten"
    EPIC = "episch"
    LEGENDARY = "legendär"


class PetEvolutionStage(str, Enum):
    """Evolutionsstufe eines Pets."""

    BABY = "baby"
    TEEN = "teen"
    ADULT = "adult"
    LEGENDARY = "legendary"


class PetMood(str, Enum):
    """Impuls-Zustand eines Pets (identisch mit /pet play)."""

    FOCUS = "focus"
    ENERGY = "energy"
    LUCK = "luck"


class PetCooldownType(str, Enum):
    """Typen persistenter Pet-Cooldowns."""

    EGG = "egg"
    PLAY = "play"
    RENAME = "rename"
    ACTIVITY = "activity"


@dataclass
class PetRecord:
    """Virtuelles Haustier eines Nutzers."""

    id: int
    owner_id: int
    guild_id: int
    name: str
    species: str
    level: int = 1
    xp: int = 0
    mood: str = PetMood.FOCUS.value
    favorite_activity: str = ""
    personality: str = ""
    catchphrase: str = ""
    adoption_date: datetime | None = None
    last_interaction: datetime | None = None
    total_interactions: int = 0
    evolution_stage: str = PetEvolutionStage.BABY.value
    is_active: bool = True

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "PetRecord":
        adoption = row.get("adoption_date")
        last = row.get("last_interaction")
        return cls(
            id=row["id"],
            owner_id=row["owner_id"],
            guild_id=row["guild_id"],
            name=row["name"],
            species=row["species"],
            level=int(row.get("level") or 1),
            xp=int(row.get("xp") or 0),
            mood=row.get("mood") or PetMood.FOCUS.value,
            favorite_activity=row.get("favorite_activity") or "",
            personality=row.get("personality") or "",
            catchphrase=row.get("catchphrase") or "",
            adoption_date=datetime.fromisoformat(adoption) if isinstance(adoption, str) and adoption else None,
            last_interaction=datetime.fromisoformat(last) if isinstance(last, str) and last else None,
            total_interactions=int(row.get("total_interactions") or 0),
            evolution_stage=row.get("evolution_stage") or PetEvolutionStage.BABY.value,
            is_active=bool(row.get("is_active", 1)),
        )


@dataclass
class DailyChallengeRecord:
    """Tägliche Aufgaben eines Nutzers."""

    guild_id: int
    user_id: int
    challenge_date: str
    challenges: list[ChallengeTask]
    generation_version: int = 1

    def to_json(self) -> str:
        payload = {
            "version": self.generation_version,
            "challenges": [task.to_dict() for task in self.challenges],
        }
        return json.dumps(payload)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "DailyChallengeRecord":
        raw = row.get("challenges_json") or "[]"
        generation_version = 1
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            parsed = []
        if isinstance(parsed, dict):
            generation_version = int(parsed.get("version") or 1)
            items = parsed.get("challenges") or []
        else:
            items = parsed if isinstance(parsed, list) else []
        return cls(
            guild_id=row["guild_id"],
            user_id=row["user_id"],
            challenge_date=row["challenge_date"],
            challenges=[ChallengeTask.from_dict(item) for item in items],
            generation_version=generation_version,
        )


class TournamentStatus(str, Enum):
    """Status eines Turniers."""

    OPEN = "open"
    CLOSED = "closed"
    FINISHED = "finished"


class TournamentMatchStatus(str, Enum):
    """Status eines Turnier-Matches."""

    OPEN = "open"
    PENDING_CONFIRMATION = "pending_confirmation"
    DISPUTED = "disputed"
    FINISHED = "finished"


@dataclass
class TournamentRecord:
    """Turnier-Stammdaten."""

    id: int
    guild_id: int
    name: str
    game: str
    description: str
    max_teams: int
    status: TournamentStatus
    created_at: datetime
    interface_channel_id: int | None = None
    interface_message_id: int | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "TournamentRecord":
        created = row.get("created_at")
        status_raw = row.get("status") or TournamentStatus.OPEN.value
        try:
            status = TournamentStatus(status_raw)
        except ValueError:
            status = TournamentStatus.OPEN
        return cls(
            id=row["id"],
            guild_id=row["guild_id"],
            name=row["name"],
            game=row["game"],
            description=row.get("description") or "",
            max_teams=int(row.get("max_teams") or 2),
            status=status,
            created_at=datetime.fromisoformat(created) if isinstance(created, str) else datetime.utcnow(),
            interface_channel_id=row.get("interface_channel_id"),
            interface_message_id=row.get("interface_message_id"),
        )


@dataclass
class TournamentTeamRecord:
    """Team innerhalb eines Turniers."""

    id: int
    tournament_id: int
    name: str
    captain_id: int
    registered: bool
    message_id: int | None = None
    interface_channel_id: int | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "TournamentTeamRecord":
        return cls(
            id=row["id"],
            tournament_id=row["tournament_id"],
            name=row["name"],
            captain_id=row["captain_id"],
            registered=bool(row.get("registered", 0)),
            message_id=row.get("message_id"),
            interface_channel_id=row.get("interface_channel_id"),
        )


@dataclass
class TournamentMatchRecord:
    """Einzelnes Match in einem Turnier."""

    id: int
    tournament_id: int
    round: int
    team1_id: int | None
    team2_id: int | None
    map_name: str
    winner_id: int | None
    status: TournamentMatchStatus
    message_id: int | None
    reported_by_team_id: int | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "TournamentMatchRecord":
        status_raw = row.get("status") or TournamentMatchStatus.OPEN.value
        try:
            status = TournamentMatchStatus(status_raw)
        except ValueError:
            status = TournamentMatchStatus.OPEN
        return cls(
            id=row["id"],
            tournament_id=row["tournament_id"],
            round=int(row.get("round") or 1),
            team1_id=row.get("team1_id"),
            team2_id=row.get("team2_id"),
            map_name=row.get("map") or "",
            winner_id=row.get("winner_id"),
            status=status,
            message_id=row.get("message_id"),
            reported_by_team_id=row.get("reported_by_team_id"),
        )
