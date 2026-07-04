"""
SQLite-Datenbankschicht mit aiosqlite.

Verwaltet Guild-Einstellungen, Warnungen und persistente
Bot-Konfiguration pro Server.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from config import Config
from database.models import (
    DEFAULT_LEAVE_MESSAGE,
    DEFAULT_WELCOME_MESSAGE,
    AutoModPunishment,
    GiveawayRecord,
    DailyChallengeRecord,
    GuessGameRecord,
    GuessStatsRecord,
    GuildSettings,
    PetCooldownType,
    PetRecord,
    PollRecord,
    PollType,
    ReactionRoleRecord,
    TicketRecord,
    TicketSettings,
    TicketStatus,
    TournamentMatchRecord,
    TournamentMatchStatus,
    TournamentRecord,
    TournamentStatus,
    TournamentTeamRecord,
    PlayerEconomyRecord,
    UserLevelRecord,
    WarningRecord,
    ZombiePlayerRecord,
    ZombieRunRecord,
    ZombieRunStatus,
)

logger = logging.getLogger(__name__)

# SQL zum Erstellen aller Tabellen beim ersten Start
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id INTEGER PRIMARY KEY,
    welcome_enabled INTEGER DEFAULT 0,
    welcome_channel_id INTEGER,
    welcome_message TEXT DEFAULT '',
    welcome_use_embed INTEGER DEFAULT 1,
    welcome_show_join_date INTEGER DEFAULT 1,
    welcome_image_enabled INTEGER DEFAULT 0,
    leave_enabled INTEGER DEFAULT 0,
    leave_channel_id INTEGER,
    leave_message TEXT DEFAULT '',
    leave_use_embed INTEGER DEFAULT 1,
    logs_enabled INTEGER DEFAULT 0,
    logs_channel_id INTEGER,
    automod_enabled INTEGER DEFAULT 0,
    spam_protection INTEGER DEFAULT 0,
    invite_blocker INTEGER DEFAULT 0,
    link_blocker INTEGER DEFAULT 0,
    bad_word_filter INTEGER DEFAULT 0,
    bad_words TEXT DEFAULT '[]',
    automod_punishment TEXT DEFAULT 'warn',
    automod_timeout_minutes INTEGER DEFAULT 10,
    mute_role_id INTEGER
);

CREATE TABLE IF NOT EXISTS warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    moderator_id INTEGER NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_warnings_guild_user
    ON warnings (guild_id, user_id);

CREATE TABLE IF NOT EXISTS user_levels (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    last_xp_at TEXT,
    PRIMARY KEY (guild_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_user_levels_guild_xp
    ON user_levels (guild_id, xp DESC);

CREATE TABLE IF NOT EXISTS player_economy (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    gold INTEGER DEFAULT 0,
    lootbox_count INTEGER DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_player_economy_guild_gold
    ON player_economy (guild_id, gold DESC);

CREATE TABLE IF NOT EXISTS reaction_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    emoji TEXT NOT NULL,
    role_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (message_id, emoji)
);

CREATE INDEX IF NOT EXISTS idx_reaction_roles_message
    ON reaction_roles (message_id);

CREATE TABLE IF NOT EXISTS polls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL UNIQUE,
    question TEXT NOT NULL,
    poll_type TEXT NOT NULL,
    options_json TEXT DEFAULT '[]',
    ends_at TEXT,
    ended INTEGER DEFAULT 0,
    creator_id INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS giveaways (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL UNIQUE,
    prize TEXT NOT NULL,
    winner_count INTEGER DEFAULT 1,
    emoji TEXT DEFAULT '🎉',
    ends_at TEXT NOT NULL,
    ended INTEGER DEFAULT 0,
    creator_id INTEGER NOT NULL,
    winner_ids_json TEXT DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS guess_games (
    channel_id INTEGER PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    target_number INTEGER NOT NULL,
    started_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS guess_user_attempts (
    channel_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    attempts INTEGER DEFAULT 0,
    PRIMARY KEY (channel_id, user_id)
);

CREATE TABLE IF NOT EXISTS guess_stats (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    games_played INTEGER DEFAULT 0,
    games_won INTEGER DEFAULT 0,
    total_guesses INTEGER DEFAULT 0,
    win_attempts_sum INTEGER DEFAULT 0,
    best_win_attempts INTEGER,
    fastest_win_seconds INTEGER,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS daily_challenges (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    challenge_date TEXT NOT NULL,
    challenges_json TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id, challenge_date)
);

CREATE TABLE IF NOT EXISTS ticket_settings (
    guild_id INTEGER PRIMARY KEY,
    enabled INTEGER DEFAULT 0,
    category_id INTEGER,
    staff_role_id INTEGER,
    log_channel_id INTEGER,
    panel_channel_id INTEGER,
    panel_message_id INTEGER,
    panel_title TEXT DEFAULT 'Support-Tickets',
    panel_message TEXT,
    welcome_message TEXT,
    panel_button_label TEXT DEFAULT 'Ticket erstellen'
);

CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL UNIQUE,
    opener_id INTEGER NOT NULL,
    claimed_by_id INTEGER,
    status TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL,
    closed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_tickets_guild_status
    ON tickets (guild_id, status);

CREATE INDEX IF NOT EXISTS idx_tickets_opener
    ON tickets (guild_id, opener_id, status);

CREATE TABLE IF NOT EXISTS pets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    species TEXT NOT NULL,
    level INTEGER DEFAULT 1,
    xp INTEGER DEFAULT 0,
    mood TEXT DEFAULT 'focus',
    favorite_activity TEXT,
    personality TEXT,
    catchphrase TEXT,
    adoption_date TEXT DEFAULT CURRENT_TIMESTAMP,
    last_interaction TEXT DEFAULT CURRENT_TIMESTAMP,
    total_interactions INTEGER DEFAULT 0,
    evolution_stage TEXT DEFAULT 'baby',
    is_active INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_pets_owner
    ON pets (guild_id, owner_id);

CREATE INDEX IF NOT EXISTS idx_pets_leaderboard
    ON pets (guild_id, level DESC, xp DESC);

CREATE TABLE IF NOT EXISTS pet_cooldowns (
    guild_id INTEGER NOT NULL,
    owner_id INTEGER NOT NULL,
    cooldown_type TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    PRIMARY KEY (guild_id, owner_id, cooldown_type)
);

CREATE TABLE IF NOT EXISTS turniere (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    game TEXT NOT NULL,
    description TEXT DEFAULT '',
    max_teams INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_turniere_guild
    ON turniere (guild_id, status);

CREATE TABLE IF NOT EXISTS turnier_maps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL,
    mapname TEXT NOT NULL,
    FOREIGN KEY (tournament_id) REFERENCES turniere(id) ON DELETE CASCADE,
    UNIQUE (tournament_id, mapname)
);

CREATE TABLE IF NOT EXISTS turnier_teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    captain_id INTEGER NOT NULL,
    registered INTEGER DEFAULT 0,
    FOREIGN KEY (tournament_id) REFERENCES turniere(id) ON DELETE CASCADE,
    UNIQUE (tournament_id, name)
);

CREATE TABLE IF NOT EXISTS turnier_team_members (
    team_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    PRIMARY KEY (team_id, user_id),
    FOREIGN KEY (team_id) REFERENCES turnier_teams(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS turnier_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL,
    round INTEGER NOT NULL,
    team1_id INTEGER,
    team2_id INTEGER,
    map TEXT DEFAULT '',
    winner_id INTEGER,
    status TEXT NOT NULL DEFAULT 'open',
    message_id INTEGER,
    reported_by_team_id INTEGER,
    FOREIGN KEY (tournament_id) REFERENCES turniere(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_turnier_matches_tournament
    ON turnier_matches (tournament_id, round);

CREATE TABLE IF NOT EXISTS zombie_players (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    level INTEGER DEFAULT 1,
    xp INTEGER DEFAULT 0,
    highest_wave INTEGER DEFAULT 0,
    total_kills INTEGER DEFAULT 0,
    boss_kills INTEGER DEFAULT 0,
    runs_completed INTEGER DEFAULT 0,
    runs_failed INTEGER DEFAULT 0,
    perks_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_zombie_players_guild_level
    ON zombie_players (guild_id, level DESC);

CREATE INDEX IF NOT EXISTS idx_zombie_players_guild_wave
    ON zombie_players (guild_id, highest_wave DESC);

CREATE TABLE IF NOT EXISTS zombie_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    channel_id INTEGER,
    message_id INTEGER,
    status TEXT NOT NULL DEFAULT 'active',
    wave INTEGER DEFAULT 1,
    max_waves INTEGER DEFAULT 3,
    player_hp INTEGER NOT NULL,
    player_max_hp INTEGER NOT NULL,
    run_gold INTEGER DEFAULT 0,
    current_zombie_key TEXT,
    current_zombie_hp INTEGER DEFAULT 0,
    zombies_remaining INTEGER DEFAULT 0,
    pet_action_cooldown INTEGER DEFAULT 0,
    luck_bonus_uses INTEGER DEFAULT 0,
    focus_active INTEGER DEFAULT 0,
    total_damage INTEGER DEFAULT 0,
    last_action_text TEXT DEFAULT '',
    shop_available INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_zombie_runs_active
    ON zombie_runs (guild_id, user_id, status);

CREATE TABLE IF NOT EXISTS zombie_cooldowns (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    cooldown_type TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id, cooldown_type)
);
"""

_GUILD_SETTINGS_MIGRATIONS = [
    "ALTER TABLE guild_settings ADD COLUMN levels_enabled INTEGER DEFAULT 0",
    "ALTER TABLE guild_settings ADD COLUMN levels_xp_min INTEGER DEFAULT 15",
    "ALTER TABLE guild_settings ADD COLUMN levels_xp_max INTEGER DEFAULT 25",
    "ALTER TABLE guild_settings ADD COLUMN levels_cooldown INTEGER DEFAULT 60",
    "ALTER TABLE guild_settings ADD COLUMN levels_announce_channel_id INTEGER",
    "ALTER TABLE guild_settings ADD COLUMN levels_announce_enabled INTEGER DEFAULT 1",
    "ALTER TABLE guess_stats ADD COLUMN win_attempts_sum INTEGER DEFAULT 0",
    "ALTER TABLE guild_settings ADD COLUMN tournament_channel_id INTEGER",
    "ALTER TABLE turnier_teams ADD COLUMN message_id INTEGER",
    "ALTER TABLE turnier_teams ADD COLUMN interface_channel_id INTEGER",
]

_TICKET_SETTINGS_MIGRATIONS = [
    "ALTER TABLE ticket_settings ADD COLUMN panel_title TEXT DEFAULT 'Support-Tickets'",
    "ALTER TABLE ticket_settings ADD COLUMN panel_message TEXT",
    "ALTER TABLE ticket_settings ADD COLUMN welcome_message TEXT",
    "ALTER TABLE ticket_settings ADD COLUMN panel_button_label TEXT DEFAULT 'Ticket erstellen'",
]

_PLAYER_ECONOMY_MIGRATIONS = [
    "ALTER TABLE player_economy ADD COLUMN player_hp INTEGER DEFAULT 0",
    "ALTER TABLE player_economy ADD COLUMN player_hp_max INTEGER DEFAULT 0",
    "ALTER TABLE player_economy ADD COLUMN last_hp_regen_at TEXT",
    "ALTER TABLE player_economy ADD COLUMN last_dungeon_at TEXT",
    "ALTER TABLE player_economy ADD COLUMN dungeons_completed INTEGER DEFAULT 0",
    "ALTER TABLE player_economy ADD COLUMN pet_recovery_until TEXT",
    "ALTER TABLE player_economy ADD COLUMN pet_recovery_pet_id INTEGER",
]

_TOURNAMENT_MIGRATIONS = [
    "ALTER TABLE turniere ADD COLUMN interface_channel_id INTEGER",
    "ALTER TABLE turniere ADD COLUMN interface_message_id INTEGER",
]

class Database:
    """
    Asynchrone SQLite-Datenbankverbindung für den Bot.

    Wird einmal pro Bot-Instanz erstellt und an alle Cogs übergeben.
    """

    def __init__(self, path: str | None = None) -> None:
        """
        Initialisiert die Datenbank mit optionalem Pfad.

        Args:
            path: Pfad zur .db-Datei (Standard: config.DATABASE_PATH).
        """
        self.path = str(path or Config.DATABASE_PATH)
        self._connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Stellt die Datenbankverbindung her."""
        self._connection = await aiosqlite.connect(self.path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA foreign_keys = ON")
        await self._connection.execute("PRAGMA journal_mode = WAL")
        await self._connection.commit()
        logger.info("Datenbank verbunden: %s", self.path)

    async def close(self) -> None:
        """Schließt die Datenbankverbindung."""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("Datenbankverbindung geschlossen.")

    async def initialize(self) -> None:
        """Erstellt Tabellen falls nicht vorhanden."""
        if not self._connection:
            raise RuntimeError("Datenbank nicht verbunden. Rufe connect() zuerst auf.")
        await self._connection.executescript(_SCHEMA_SQL)
        await self._migrate_guild_settings()
        await self._migrate_ticket_settings()
        await self._migrate_player_economy()
        await self._migrate_tournaments()
        await self._connection.commit()
        logger.info("Datenbankschema initialisiert.")

    async def _migrate_guild_settings(self) -> None:
        """Fügt neue Spalten zu guild_settings hinzu (idempotent)."""
        for sql in _GUILD_SETTINGS_MIGRATIONS:
            try:
                await self._connection.execute(sql)
            except aiosqlite.OperationalError:
                pass

    async def _migrate_ticket_settings(self) -> None:
        """Fügt neue Spalten zu ticket_settings hinzu (idempotent)."""
        for sql in _TICKET_SETTINGS_MIGRATIONS:
            try:
                await self._connection.execute(sql)
            except aiosqlite.OperationalError:
                pass

    async def _migrate_player_economy(self) -> None:
        """Fügt Legacy-Spalten zu player_economy hinzu (idempotent, ungenutzt)."""
        for sql in _PLAYER_ECONOMY_MIGRATIONS:
            try:
                await self._connection.execute(sql)
            except aiosqlite.OperationalError:
                pass

    async def _migrate_tournaments(self) -> None:
        """Fügt Interface-Spalten zu turniere hinzu (idempotent)."""
        for sql in _TOURNAMENT_MIGRATIONS:
            try:
                await self._connection.execute(sql)
            except aiosqlite.OperationalError:
                pass

    @property
    def conn(self) -> aiosqlite.Connection:
        """Gibt die aktive Verbindung zurück."""
        if not self._connection:
            raise RuntimeError("Datenbank nicht verbunden.")
        return self._connection

    async def _ensure_guild(self, guild_id: int) -> None:
        """Legt Standard-Einstellungen für eine Guild an, falls noch nicht vorhanden."""
        cursor = await self.conn.execute(
            "SELECT guild_id FROM guild_settings WHERE guild_id = ?",
            (guild_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            await self.conn.execute(
                """
                INSERT INTO guild_settings (guild_id, welcome_message, leave_message)
                VALUES (?, ?, ?)
                """,
                (guild_id, DEFAULT_WELCOME_MESSAGE, DEFAULT_LEAVE_MESSAGE),
            )
            await self.conn.commit()

    async def get_guild_settings(self, guild_id: int) -> GuildSettings:
        """
        Lädt alle Einstellungen für einen Server.

        Args:
            guild_id: Discord Guild ID.

        Returns:
            GuildSettings-Objekt.
        """
        await self._ensure_guild(guild_id)
        cursor = await self.conn.execute(
            "SELECT * FROM guild_settings WHERE guild_id = ?",
            (guild_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return GuildSettings(guild_id=guild_id)
        return GuildSettings.from_row(dict(row))

    async def update_guild_settings(self, guild_id: int, **fields: Any) -> GuildSettings:
        """
        Aktualisiert einzelne Guild-Einstellungsfelder.

        Args:
            guild_id: Discord Guild ID.
            **fields: Spaltenname -> Wert.

        Returns:
            Aktualisierte GuildSettings.
        """
        await self._ensure_guild(guild_id)

        if "bad_words" in fields and isinstance(fields["bad_words"], list):
            fields["bad_words"] = json.dumps(fields["bad_words"])

        if "automod_punishment" in fields and isinstance(
            fields["automod_punishment"], AutoModPunishment
        ):
            fields["automod_punishment"] = fields["automod_punishment"].value

        # Boolean-Werte in Integer für SQLite
        for key, value in list(fields.items()):
            if isinstance(value, bool):
                fields[key] = int(value)

        if not fields:
            return await self.get_guild_settings(guild_id)

        columns = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [guild_id]
        await self.conn.execute(
            f"UPDATE guild_settings SET {columns} WHERE guild_id = ?",
            values,
        )
        await self.conn.commit()
        return await self.get_guild_settings(guild_id)

    async def reset_guild_settings(self, guild_id: int) -> GuildSettings:
        """
        Setzt alle Einstellungen eines Servers auf Standard zurück.

        Args:
            guild_id: Discord Guild ID.

        Returns:
            Zurückgesetzte GuildSettings.
        """
        await self.conn.execute(
            "DELETE FROM guild_settings WHERE guild_id = ?",
            (guild_id,),
        )
        await self.conn.commit()
        return await self.get_guild_settings(guild_id)

    async def add_warning(
        self,
        guild_id: int,
        user_id: int,
        moderator_id: int,
        reason: str,
    ) -> WarningRecord:
        """
        Speichert eine neue Verwarnung.

        Args:
            guild_id: Server-ID.
            user_id: Verwarnter User.
            moderator_id: Moderator.
            reason: Grund.

        Returns:
            Erstellter WarningRecord.
        """
        created_at = datetime.now(timezone.utc).isoformat()
        cursor = await self.conn.execute(
            """
            INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (guild_id, user_id, moderator_id, reason, created_at),
        )
        await self.conn.commit()
        warning_id = cursor.lastrowid
        return WarningRecord(
            id=warning_id,
            guild_id=guild_id,
            user_id=user_id,
            moderator_id=moderator_id,
            reason=reason,
            created_at=datetime.fromisoformat(created_at),
        )

    async def remove_warning(self, guild_id: int, warning_id: int) -> bool:
        """
        Entfernt eine Verwarnung anhand der ID.

        Returns:
            True wenn gelöscht, False wenn nicht gefunden.
        """
        cursor = await self.conn.execute(
            "DELETE FROM warnings WHERE id = ? AND guild_id = ?",
            (warning_id, guild_id),
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def get_warnings(
        self,
        guild_id: int,
        user_id: int,
        *,
        limit: int = 25,
    ) -> list[WarningRecord]:
        """
        Lädt alle Warnungen eines Users auf einem Server.

        Args:
            guild_id: Server-ID.
            user_id: User-ID.
            limit: Maximale Anzahl.

        Returns:
            Liste von WarningRecords.
        """
        cursor = await self.conn.execute(
            """
            SELECT * FROM warnings
            WHERE guild_id = ? AND user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (guild_id, user_id, limit),
        )
        rows = await cursor.fetchall()
        return [WarningRecord.from_row(dict(row)) for row in rows]

    async def count_warnings(self, guild_id: int, user_id: int) -> int:
        """Zählt Warnungen eines Users."""
        cursor = await self.conn.execute(
            "SELECT COUNT(*) as cnt FROM warnings WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        row = await cursor.fetchone()
        return int(row["cnt"]) if row else 0

    # ── Level-System ────────────────────────────────────────────────

    async def get_user_level(self, guild_id: int, user_id: int) -> UserLevelRecord:
        """Lädt Level-Daten oder erstellt Standardwerte."""
        cursor = await self.conn.execute(
            "SELECT * FROM user_levels WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return UserLevelRecord(guild_id=guild_id, user_id=user_id, xp=0, level=1)
        return UserLevelRecord.from_row(dict(row))

    async def save_user_level(self, record: UserLevelRecord) -> UserLevelRecord:
        """Speichert XP/Level eines Nutzers."""
        last_xp = record.last_xp_at.isoformat() if record.last_xp_at else None
        await self.conn.execute(
            """
            INSERT INTO user_levels (guild_id, user_id, xp, level, last_xp_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                xp = excluded.xp,
                level = excluded.level,
                last_xp_at = excluded.last_xp_at
            """,
            (record.guild_id, record.user_id, record.xp, record.level, last_xp),
        )
        await self.conn.commit()
        return record

    async def get_level_leaderboard(
        self,
        guild_id: int,
        *,
        limit: int = 10,
    ) -> list[UserLevelRecord]:
        """Top-N Nutzer nach XP."""
        cursor = await self.conn.execute(
            """
            SELECT * FROM user_levels
            WHERE guild_id = ?
            ORDER BY xp DESC, level DESC
            LIMIT ?
            """,
            (guild_id, limit),
        )
        rows = await cursor.fetchall()
        return [UserLevelRecord.from_row(dict(row)) for row in rows]

    async def get_user_rank(self, guild_id: int, user_id: int) -> int:
        """Platzierung eines Nutzers (1 = höchste XP)."""
        record = await self.get_user_level(guild_id, user_id)
        cursor = await self.conn.execute(
            """
            SELECT COUNT(*) + 1 AS rank_pos FROM user_levels
            WHERE guild_id = ? AND xp > ?
            """,
            (guild_id, record.xp),
        )
        row = await cursor.fetchone()
        return int(row["rank_pos"]) if row else 1

    # ── Economy (Gold & Lootboxen) ──────────────────────────────────

    async def get_player_economy(self, guild_id: int, user_id: int) -> PlayerEconomyRecord:
        """Lädt Gold und Lootbox-Inventar oder Standardwerte."""
        cursor = await self.conn.execute(
            "SELECT * FROM player_economy WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return PlayerEconomyRecord(guild_id=guild_id, user_id=user_id)
        return PlayerEconomyRecord.from_row(dict(row))

    async def save_player_economy(self, record: PlayerEconomyRecord) -> PlayerEconomyRecord:
        """Speichert Gold und Lootbox-Inventar."""
        await self.conn.execute(
            """
            INSERT INTO player_economy (guild_id, user_id, gold, lootbox_count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                gold = excluded.gold,
                lootbox_count = excluded.lootbox_count
            """,
            (
                record.guild_id,
                record.user_id,
                record.gold,
                record.lootbox_count,
            ),
        )
        await self.conn.commit()
        return record

    async def add_player_gold(self, guild_id: int, user_id: int, amount: int) -> PlayerEconomyRecord:
        """Addiert Gold (negativ zum Abziehen)."""
        record = await self.get_player_economy(guild_id, user_id)
        record.gold = max(0, record.gold + amount)
        return await self.save_player_economy(record)

    async def add_lootboxes(self, guild_id: int, user_id: int, count: int) -> PlayerEconomyRecord:
        """Addiert oder entfernt Lootboxen im Inventar."""
        record = await self.get_player_economy(guild_id, user_id)
        record.lootbox_count = max(0, record.lootbox_count + count)
        return await self.save_player_economy(record)

    async def get_gold_leaderboard(
        self,
        guild_id: int,
        *,
        limit: int = 10,
    ) -> list[PlayerEconomyRecord]:
        """Top-N Nutzer nach Gold."""
        cursor = await self.conn.execute(
            """
            SELECT * FROM player_economy
            WHERE guild_id = ? AND gold > 0
            ORDER BY gold DESC
            LIMIT ?
            """,
            (guild_id, limit),
        )
        rows = await cursor.fetchall()
        return [PlayerEconomyRecord.from_row(dict(row)) for row in rows]

    # ── Zombie Survival ─────────────────────────────────────────────

    async def get_zombie_player(self, guild_id: int, user_id: int) -> ZombiePlayerRecord:
        """Lädt oder erstellt ein Zombie-Profil."""
        cursor = await self.conn.execute(
            "SELECT * FROM zombie_players WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        row = await cursor.fetchone()
        if row:
            return ZombiePlayerRecord.from_row(dict(row))
        now = datetime.now(timezone.utc).isoformat()
        await self.conn.execute(
            """
            INSERT INTO zombie_players (
                guild_id, user_id, highest_wave, total_kills, boss_kills,
                runs_completed, runs_failed, perks_json, created_at, updated_at
            ) VALUES (?, ?, 0, 0, 0, 0, 0, '{}', ?, ?)
            """,
            (guild_id, user_id, now, now),
        )
        await self.conn.commit()
        return ZombiePlayerRecord(
            guild_id=guild_id,
            user_id=user_id,
            created_at=datetime.fromisoformat(now),
            updated_at=datetime.fromisoformat(now),
        )

    async def save_zombie_player(self, record: ZombiePlayerRecord) -> ZombiePlayerRecord:
        """Speichert Zombie-Profil."""
        record.updated_at = datetime.now(timezone.utc)
        await self.conn.execute(
            """
            INSERT INTO zombie_players (
                guild_id, user_id, highest_wave, total_kills, boss_kills,
                runs_completed, runs_failed, perks_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                highest_wave = excluded.highest_wave,
                total_kills = excluded.total_kills,
                boss_kills = excluded.boss_kills,
                runs_completed = excluded.runs_completed,
                runs_failed = excluded.runs_failed,
                perks_json = excluded.perks_json,
                updated_at = excluded.updated_at
            """,
            (
                record.guild_id,
                record.user_id,
                record.highest_wave,
                record.total_kills,
                record.boss_kills,
                record.runs_completed,
                record.runs_failed,
                record.perks_json,
                record.created_at.isoformat(),
                record.updated_at.isoformat(),
            ),
        )
        await self.conn.commit()
        return record

    async def get_active_zombie_run(self, guild_id: int, user_id: int) -> ZombieRunRecord | None:
        """Lädt den aktiven Zombie-Run eines Nutzers."""
        cursor = await self.conn.execute(
            """
            SELECT * FROM zombie_runs
            WHERE guild_id = ? AND user_id = ? AND status = ?
            ORDER BY id DESC LIMIT 1
            """,
            (guild_id, user_id, ZombieRunStatus.ACTIVE.value),
        )
        row = await cursor.fetchone()
        return ZombieRunRecord.from_row(dict(row)) if row else None

    async def get_zombie_run(self, run_id: int) -> ZombieRunRecord | None:
        """Lädt einen Zombie-Run per ID."""
        cursor = await self.conn.execute(
            "SELECT * FROM zombie_runs WHERE id = ?",
            (run_id,),
        )
        row = await cursor.fetchone()
        return ZombieRunRecord.from_row(dict(row)) if row else None

    async def get_all_active_zombie_runs(self) -> list[ZombieRunRecord]:
        """Lädt alle aktiven Runs (für persistente Views)."""
        cursor = await self.conn.execute(
            "SELECT * FROM zombie_runs WHERE status = ?",
            (ZombieRunStatus.ACTIVE.value,),
        )
        rows = await cursor.fetchall()
        return [ZombieRunRecord.from_row(dict(row)) for row in rows]

    async def save_zombie_run(self, run: ZombieRunRecord) -> ZombieRunRecord:
        """Speichert oder aktualisiert einen Zombie-Run."""
        run.updated_at = datetime.now(timezone.utc)
        updated = run.updated_at.isoformat()
        if run.id:
            await self.conn.execute(
                """
                UPDATE zombie_runs SET
                    channel_id = ?, message_id = ?, status = ?, wave = ?, max_waves = ?,
                    player_hp = ?, player_max_hp = ?, run_gold = ?,
                    current_zombie_key = ?, current_zombie_hp = ?, zombies_remaining = ?,
                    pet_action_cooldown = ?, luck_bonus_uses = ?, focus_active = ?,
                    total_damage = ?, last_action_text = ?, shop_available = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    run.channel_id,
                    run.message_id,
                    run.status,
                    run.wave,
                    run.max_waves,
                    run.player_hp,
                    run.player_max_hp,
                    run.run_gold,
                    run.current_zombie_key,
                    run.current_zombie_hp,
                    run.zombies_remaining,
                    run.pet_action_cooldown,
                    run.luck_bonus_uses,
                    run.focus_active,
                    run.total_damage,
                    run.last_action_text,
                    run.shop_available,
                    updated,
                    run.id,
                ),
            )
        else:
            created = run.created_at.isoformat()
            cursor = await self.conn.execute(
                """
                INSERT INTO zombie_runs (
                    guild_id, user_id, channel_id, message_id, status, wave, max_waves,
                    player_hp, player_max_hp, run_gold, current_zombie_key, current_zombie_hp,
                    zombies_remaining, pet_action_cooldown, luck_bonus_uses, focus_active,
                    total_damage, last_action_text, shop_available, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.guild_id,
                    run.user_id,
                    run.channel_id,
                    run.message_id,
                    run.status,
                    run.wave,
                    run.max_waves,
                    run.player_hp,
                    run.player_max_hp,
                    run.run_gold,
                    run.current_zombie_key,
                    run.current_zombie_hp,
                    run.zombies_remaining,
                    run.pet_action_cooldown,
                    run.luck_bonus_uses,
                    run.focus_active,
                    run.total_damage,
                    run.last_action_text,
                    run.shop_available,
                    created,
                    updated,
                ),
            )
            run.id = cursor.lastrowid or 0
        await self.conn.commit()
        return run

    async def get_stale_active_zombie_runs(self, max_inactivity_seconds: int) -> list[ZombieRunRecord]:
        """Lädt aktive Runs, die länger als max_inactivity_seconds inaktiv sind."""
        cutoff = datetime.now(timezone.utc).timestamp() - max_inactivity_seconds
        cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()
        cursor = await self.conn.execute(
            """
            SELECT * FROM zombie_runs
            WHERE status = ? AND updated_at < ?
            """,
            (ZombieRunStatus.ACTIVE.value, cutoff_iso),
        )
        rows = await cursor.fetchall()
        return [ZombieRunRecord.from_row(dict(row)) for row in rows]

    async def set_zombie_cooldown(
        self,
        guild_id: int,
        user_id: int,
        cooldown_type: str,
        expires_at: datetime,
    ) -> None:
        """Setzt einen Zombie-Cooldown."""
        await self.conn.execute(
            """
            INSERT INTO zombie_cooldowns (guild_id, user_id, cooldown_type, expires_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id, cooldown_type) DO UPDATE SET
                expires_at = excluded.expires_at
            """,
            (guild_id, user_id, cooldown_type, expires_at.isoformat()),
        )
        await self.conn.commit()

    async def get_zombie_cooldown(
        self,
        guild_id: int,
        user_id: int,
        cooldown_type: str,
    ) -> datetime | None:
        """Lädt Ablaufzeit eines Cooldowns."""
        cursor = await self.conn.execute(
            """
            SELECT expires_at FROM zombie_cooldowns
            WHERE guild_id = ? AND user_id = ? AND cooldown_type = ?
            """,
            (guild_id, user_id, cooldown_type),
        )
        row = await cursor.fetchone()
        if not row or not row["expires_at"]:
            return None
        return datetime.fromisoformat(row["expires_at"])

    async def get_zombie_leaderboard(
        self,
        guild_id: int,
        sort_by: str,
        limit: int = 10,
    ) -> list[ZombiePlayerRecord]:
        """Lädt Zombie-Rangliste nach Spalte."""
        allowed = {
            "kills": "total_kills",
            "boss_kills": "boss_kills",
        }
        column = allowed.get(sort_by, "total_kills")
        cursor = await self.conn.execute(
            f"""
            SELECT * FROM zombie_players
            WHERE guild_id = ?
            ORDER BY {column} DESC, highest_wave DESC
            LIMIT ?
            """,
            (guild_id, limit),
        )
        rows = await cursor.fetchall()
        return [ZombiePlayerRecord.from_row(dict(row)) for row in rows]

    async def get_zombie_gold_leaderboard(
        self,
        guild_id: int,
        limit: int = 10,
    ) -> list[PlayerEconomyRecord]:
        """Gold-Rangliste für Zombie-Leaderboard."""
        return await self.get_gold_leaderboard(guild_id, limit)

    # ── Reaktionsrollen ─────────────────────────────────────────────

    async def add_reaction_role(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        emoji: str,
        role_id: int,
    ) -> ReactionRoleRecord:
        """Speichert eine Reaktionsrolle."""
        created_at = datetime.now(timezone.utc).isoformat()
        cursor = await self.conn.execute(
            """
            INSERT INTO reaction_roles (guild_id, channel_id, message_id, emoji, role_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (guild_id, channel_id, message_id, emoji, role_id, created_at),
        )
        await self.conn.commit()
        return ReactionRoleRecord(
            id=cursor.lastrowid,
            guild_id=guild_id,
            channel_id=channel_id,
            message_id=message_id,
            emoji=emoji,
            role_id=role_id,
            created_at=datetime.fromisoformat(created_at),
        )

    async def get_reaction_role(self, message_id: int, emoji: str) -> ReactionRoleRecord | None:
        """Findet Reaktionsrolle anhand Nachricht und Emoji."""
        cursor = await self.conn.execute(
            "SELECT * FROM reaction_roles WHERE message_id = ? AND emoji = ?",
            (message_id, emoji),
        )
        row = await cursor.fetchone()
        return ReactionRoleRecord.from_row(dict(row)) if row else None

    async def get_reaction_roles_for_message(self, message_id: int) -> list[ReactionRoleRecord]:
        """Alle Reaktionsrollen einer Nachricht."""
        cursor = await self.conn.execute(
            "SELECT * FROM reaction_roles WHERE message_id = ? ORDER BY id ASC",
            (message_id,),
        )
        rows = await cursor.fetchall()
        return [ReactionRoleRecord.from_row(dict(row)) for row in rows]

    async def get_reaction_roles_for_guild(self, guild_id: int) -> list[ReactionRoleRecord]:
        """Alle Reaktionsrollen eines Servers."""
        cursor = await self.conn.execute(
            "SELECT * FROM reaction_roles WHERE guild_id = ? ORDER BY message_id, id",
            (guild_id,),
        )
        rows = await cursor.fetchall()
        return [ReactionRoleRecord.from_row(dict(row)) for row in rows]

    async def remove_reaction_role(self, reaction_role_id: int, guild_id: int) -> bool:
        """Entfernt eine Reaktionsrolle."""
        cursor = await self.conn.execute(
            "DELETE FROM reaction_roles WHERE id = ? AND guild_id = ?",
            (reaction_role_id, guild_id),
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def remove_reaction_roles_for_message(self, message_id: int) -> None:
        """Entfernt alle Reaktionsrollen einer Nachricht."""
        await self.conn.execute("DELETE FROM reaction_roles WHERE message_id = ?", (message_id,))
        await self.conn.commit()

    # ── Umfragen ────────────────────────────────────────────────────

    async def create_poll(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        question: str,
        poll_type: PollType,
        options: list[str],
        creator_id: int,
        ends_at: datetime | None = None,
    ) -> PollRecord:
        """Speichert eine neue Umfrage."""
        created_at = datetime.now(timezone.utc).isoformat()
        ends_str = ends_at.isoformat() if ends_at else None
        cursor = await self.conn.execute(
            """
            INSERT INTO polls (
                guild_id, channel_id, message_id, question, poll_type,
                options_json, ends_at, ended, creator_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                guild_id,
                channel_id,
                message_id,
                question,
                poll_type.value,
                json.dumps(options),
                ends_str,
                creator_id,
                created_at,
            ),
        )
        await self.conn.commit()
        return PollRecord(
            id=cursor.lastrowid,
            guild_id=guild_id,
            channel_id=channel_id,
            message_id=message_id,
            question=question,
            poll_type=poll_type,
            options=options,
            ends_at=ends_at,
            ended=False,
            creator_id=creator_id,
            created_at=datetime.fromisoformat(created_at),
        )

    async def get_poll(self, poll_id: int) -> PollRecord | None:
        """Lädt Umfrage per ID."""
        cursor = await self.conn.execute("SELECT * FROM polls WHERE id = ?", (poll_id,))
        row = await cursor.fetchone()
        return PollRecord.from_row(dict(row)) if row else None

    async def get_poll_by_message(self, message_id: int) -> PollRecord | None:
        """Lädt Umfrage anhand der Nachrichten-ID."""
        cursor = await self.conn.execute("SELECT * FROM polls WHERE message_id = ?", (message_id,))
        row = await cursor.fetchone()
        return PollRecord.from_row(dict(row)) if row else None

    async def get_active_polls(self) -> list[PollRecord]:
        """Alle laufenden Umfragen."""
        cursor = await self.conn.execute("SELECT * FROM polls WHERE ended = 0")
        rows = await cursor.fetchall()
        return [PollRecord.from_row(dict(row)) for row in rows]

    async def end_poll(self, poll_id: int) -> PollRecord | None:
        """Markiert Umfrage als beendet (nur wenn noch aktiv)."""
        cursor = await self.conn.execute(
            "UPDATE polls SET ended = 1 WHERE id = ? AND ended = 0",
            (poll_id,),
        )
        await self.conn.commit()
        if cursor.rowcount == 0:
            return None
        return await self.get_poll(poll_id)

    async def delete_poll(self, poll_id: int) -> None:
        """Entfernt eine Umfrage aus der Datenbank."""
        await self.conn.execute("DELETE FROM polls WHERE id = ?", (poll_id,))
        await self.conn.commit()

    # ── Gewinnspiele ────────────────────────────────────────────────

    async def create_giveaway(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        prize: str,
        winner_count: int,
        emoji: str,
        ends_at: datetime,
        creator_id: int,
    ) -> GiveawayRecord:
        """Speichert ein neues Gewinnspiel."""
        created_at = datetime.now(timezone.utc).isoformat()
        cursor = await self.conn.execute(
            """
            INSERT INTO giveaways (
                guild_id, channel_id, message_id, prize, winner_count,
                emoji, ends_at, ended, creator_id, winner_ids_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, '[]', ?)
            """,
            (
                guild_id,
                channel_id,
                message_id,
                prize,
                winner_count,
                emoji,
                ends_at.isoformat(),
                creator_id,
                created_at,
            ),
        )
        await self.conn.commit()
        return GiveawayRecord(
            id=cursor.lastrowid,
            guild_id=guild_id,
            channel_id=channel_id,
            message_id=message_id,
            prize=prize,
            winner_count=winner_count,
            emoji=emoji,
            ends_at=ends_at,
            ended=False,
            creator_id=creator_id,
            winner_ids=[],
            created_at=datetime.fromisoformat(created_at),
        )

    async def get_giveaway(self, giveaway_id: int) -> GiveawayRecord | None:
        """Lädt Gewinnspiel per ID."""
        cursor = await self.conn.execute("SELECT * FROM giveaways WHERE id = ?", (giveaway_id,))
        row = await cursor.fetchone()
        return GiveawayRecord.from_row(dict(row)) if row else None

    async def get_giveaway_by_message(self, message_id: int) -> GiveawayRecord | None:
        """Lädt Gewinnspiel anhand der Nachrichten-ID."""
        cursor = await self.conn.execute("SELECT * FROM giveaways WHERE message_id = ?", (message_id,))
        row = await cursor.fetchone()
        return GiveawayRecord.from_row(dict(row)) if row else None

    async def get_active_giveaways(self) -> list[GiveawayRecord]:
        """Alle laufenden Gewinnspiele."""
        cursor = await self.conn.execute("SELECT * FROM giveaways WHERE ended = 0")
        rows = await cursor.fetchall()
        return [GiveawayRecord.from_row(dict(row)) for row in rows]

    async def finish_giveaway(self, giveaway_id: int, winner_ids: list[int]) -> GiveawayRecord | None:
        """Beendet Gewinnspiel und speichert Gewinner."""
        await self.conn.execute(
            "UPDATE giveaways SET ended = 1, winner_ids_json = ? WHERE id = ?",
            (json.dumps(winner_ids), giveaway_id),
        )
        await self.conn.commit()
        return await self.get_giveaway(giveaway_id)

    async def update_giveaway_winners(self, giveaway_id: int, winner_ids: list[int]) -> GiveawayRecord | None:
        """Aktualisiert Gewinner eines beendeten Gewinnspiels (Reroll)."""
        await self.conn.execute(
            "UPDATE giveaways SET winner_ids_json = ? WHERE id = ?",
            (json.dumps(winner_ids), giveaway_id),
        )
        await self.conn.commit()
        return await self.get_giveaway(giveaway_id)

    async def delete_giveaway(self, giveaway_id: int) -> None:
        """Entfernt ein Gewinnspiel aus der Datenbank."""
        await self.conn.execute("DELETE FROM giveaways WHERE id = ?", (giveaway_id,))
        await self.conn.commit()

    # ── Zahlenraten ─────────────────────────────────────────────────

    async def get_guess_game(self, channel_id: int) -> GuessGameRecord | None:
        """Lädt aktives Zahlenraten-Spiel in einem Kanal."""
        cursor = await self.conn.execute(
            "SELECT * FROM guess_games WHERE channel_id = ?",
            (channel_id,),
        )
        row = await cursor.fetchone()
        return GuessGameRecord.from_row(dict(row)) if row else None

    async def create_guess_game(self, guild_id: int, channel_id: int, target_number: int) -> GuessGameRecord:
        """Startet ein neues Zahlenraten-Spiel."""
        started_at = datetime.now(timezone.utc).isoformat()
        await self.conn.execute(
            """
            INSERT INTO guess_games (channel_id, guild_id, target_number, started_at)
            VALUES (?, ?, ?, ?)
            """,
            (channel_id, guild_id, target_number, started_at),
        )
        await self.conn.execute(
            "DELETE FROM guess_user_attempts WHERE channel_id = ?",
            (channel_id,),
        )
        await self.conn.commit()
        return GuessGameRecord(
            guild_id=guild_id,
            channel_id=channel_id,
            target_number=target_number,
            started_at=datetime.fromisoformat(started_at),
        )

    async def delete_guess_game(self, channel_id: int) -> None:
        """Beendet und entfernt ein Zahlenraten-Spiel."""
        await self.conn.execute("DELETE FROM guess_games WHERE channel_id = ?", (channel_id,))
        await self.conn.execute("DELETE FROM guess_user_attempts WHERE channel_id = ?", (channel_id,))
        await self.conn.commit()

    async def increment_guess_attempt(self, channel_id: int, user_id: int) -> int:
        """Erhöht Versuchszähler und gibt neue Anzahl zurück."""
        await self.conn.execute(
            """
            INSERT INTO guess_user_attempts (channel_id, user_id, attempts)
            VALUES (?, ?, 1)
            ON CONFLICT(channel_id, user_id) DO UPDATE SET
                attempts = attempts + 1
            """,
            (channel_id, user_id),
        )
        await self.conn.commit()
        cursor = await self.conn.execute(
            "SELECT attempts FROM guess_user_attempts WHERE channel_id = ? AND user_id = ?",
            (channel_id, user_id),
        )
        row = await cursor.fetchone()
        return int(row["attempts"]) if row else 1

    async def get_guess_attempts(self, channel_id: int, user_id: int) -> int:
        """Versuche eines Nutzers im aktuellen Spiel."""
        cursor = await self.conn.execute(
            "SELECT attempts FROM guess_user_attempts WHERE channel_id = ? AND user_id = ?",
            (channel_id, user_id),
        )
        row = await cursor.fetchone()
        return int(row["attempts"]) if row else 0

    async def get_guess_participants(self, channel_id: int) -> list[tuple[int, int]]:
        """Alle Teilnehmer (user_id, attempts) eines Kanal-Spiels."""
        cursor = await self.conn.execute(
            "SELECT user_id, attempts FROM guess_user_attempts WHERE channel_id = ?",
            (channel_id,),
        )
        rows = await cursor.fetchall()
        return [(int(row["user_id"]), int(row["attempts"])) for row in rows]

    async def get_guess_stats(self, guild_id: int, user_id: int) -> GuessStatsRecord:
        """Lädt oder erstellt Guess-Statistiken."""
        cursor = await self.conn.execute(
            "SELECT * FROM guess_stats WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return GuessStatsRecord(guild_id=guild_id, user_id=user_id)
        return GuessStatsRecord.from_row(dict(row))

    async def save_guess_stats(self, stats: GuessStatsRecord) -> GuessStatsRecord:
        """Speichert Guess-Statistiken."""
        await self.conn.execute(
            """
            INSERT INTO guess_stats (
                guild_id, user_id, games_played, games_won, total_guesses,
                win_attempts_sum, best_win_attempts, fastest_win_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                games_played = excluded.games_played,
                games_won = excluded.games_won,
                total_guesses = excluded.total_guesses,
                win_attempts_sum = excluded.win_attempts_sum,
                best_win_attempts = excluded.best_win_attempts,
                fastest_win_seconds = excluded.fastest_win_seconds
            """,
            (
                stats.guild_id,
                stats.user_id,
                stats.games_played,
                stats.games_won,
                stats.total_guesses,
                stats.win_attempts_sum,
                stats.best_win_attempts,
                stats.fastest_win_seconds,
            ),
        )
        await self.conn.commit()
        return stats

    async def get_guess_leaderboard_wins(
        self,
        guild_id: int,
        *,
        limit: int = 10,
    ) -> list[GuessStatsRecord]:
        """Top-N nach Siegen beim Zahlenraten."""
        cursor = await self.conn.execute(
            """
            SELECT * FROM guess_stats
            WHERE guild_id = ? AND games_won > 0
            ORDER BY games_won DESC, best_win_attempts ASC
            LIMIT ?
            """,
            (guild_id, limit),
        )
        rows = await cursor.fetchall()
        return [GuessStatsRecord.from_row(dict(row)) for row in rows]

    async def get_guess_leaderboard_attempts(
        self,
        guild_id: int,
        *,
        limit: int = 10,
    ) -> list[GuessStatsRecord]:
        """Top-N nach wenigsten Versuchen pro Sieg."""
        cursor = await self.conn.execute(
            """
            SELECT * FROM guess_stats
            WHERE guild_id = ? AND games_won > 0 AND win_attempts_sum > 0
            ORDER BY (win_attempts_sum * 1.0 / games_won) ASC, games_won DESC
            LIMIT ?
            """,
            (guild_id, limit),
        )
        rows = await cursor.fetchall()
        return [GuessStatsRecord.from_row(dict(row)) for row in rows]

    async def get_guess_leaderboard_fastest(
        self,
        guild_id: int,
        *,
        limit: int = 10,
    ) -> list[GuessStatsRecord]:
        """Top-N nach schnellstem Sieg in Sekunden."""
        cursor = await self.conn.execute(
            """
            SELECT * FROM guess_stats
            WHERE guild_id = ? AND fastest_win_seconds IS NOT NULL
            ORDER BY fastest_win_seconds ASC
            LIMIT ?
            """,
            (guild_id, limit),
        )
        rows = await cursor.fetchall()
        return [GuessStatsRecord.from_row(dict(row)) for row in rows]

    # ── Tägliche Aufgaben ───────────────────────────────────────────

    @staticmethod
    def _today_utc() -> str:
        """Heutiges Datum als ISO-String (UTC)."""
        return datetime.now(timezone.utc).date().isoformat()

    async def get_daily_challenges(
        self,
        guild_id: int,
        user_id: int,
        *,
        challenge_date: str | None = None,
    ) -> DailyChallengeRecord | None:
        """Lädt tägliche Aufgaben für ein Datum."""
        date_key = challenge_date or self._today_utc()
        cursor = await self.conn.execute(
            """
            SELECT * FROM daily_challenges
            WHERE guild_id = ? AND user_id = ? AND challenge_date = ?
            """,
            (guild_id, user_id, date_key),
        )
        row = await cursor.fetchone()
        return DailyChallengeRecord.from_row(dict(row)) if row else None

    async def save_daily_challenges(self, record: DailyChallengeRecord) -> DailyChallengeRecord:
        """Speichert tägliche Aufgaben."""
        payload = record.to_json()
        await self.conn.execute(
            """
            INSERT INTO daily_challenges (guild_id, user_id, challenge_date, challenges_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id, challenge_date) DO UPDATE SET
                challenges_json = excluded.challenges_json
            """,
            (record.guild_id, record.user_id, record.challenge_date, payload),
        )
        await self.conn.commit()
        return record

    # ── Tickets ─────────────────────────────────────────────────────

    async def _ensure_ticket_settings(self, guild_id: int) -> None:
        """Legt Standard-Ticket-Einstellungen an, falls noch nicht vorhanden."""
        cursor = await self.conn.execute(
            "SELECT guild_id FROM ticket_settings WHERE guild_id = ?",
            (guild_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            await self.conn.execute(
                "INSERT INTO ticket_settings (guild_id) VALUES (?)",
                (guild_id,),
            )
            await self.conn.commit()

    async def get_ticket_settings(self, guild_id: int) -> TicketSettings:
        """Lädt Ticket-Einstellungen für einen Server."""
        await self._ensure_ticket_settings(guild_id)
        cursor = await self.conn.execute(
            "SELECT * FROM ticket_settings WHERE guild_id = ?",
            (guild_id,),
        )
        row = await cursor.fetchone()
        assert row is not None
        return TicketSettings.from_row(dict(row))

    async def update_ticket_settings(self, guild_id: int, **fields: Any) -> TicketSettings:
        """Aktualisiert Ticket-Einstellungen."""
        await self._ensure_ticket_settings(guild_id)
        if not fields:
            return await self.get_ticket_settings(guild_id)

        columns = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [guild_id]
        await self.conn.execute(
            f"UPDATE ticket_settings SET {columns} WHERE guild_id = ?",
            values,
        )
        await self.conn.commit()
        return await self.get_ticket_settings(guild_id)

    async def create_ticket(
        self,
        guild_id: int,
        channel_id: int,
        opener_id: int,
        *,
        reason: str | None = None,
    ) -> TicketRecord:
        """Erstellt ein neues Ticket."""
        created_at = datetime.now(timezone.utc).isoformat()
        cursor = await self.conn.execute(
            """
            INSERT INTO tickets (
                guild_id, channel_id, opener_id, status, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (guild_id, channel_id, opener_id, TicketStatus.OPEN.value, reason, created_at),
        )
        await self.conn.commit()
        ticket = await self.get_ticket(cursor.lastrowid)
        assert ticket is not None
        return ticket

    async def get_ticket(self, ticket_id: int) -> TicketRecord | None:
        """Lädt Ticket per ID."""
        cursor = await self.conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        row = await cursor.fetchone()
        return TicketRecord.from_row(dict(row)) if row else None

    async def get_ticket_by_channel(self, channel_id: int) -> TicketRecord | None:
        """Lädt Ticket anhand des Kanals."""
        cursor = await self.conn.execute(
            "SELECT * FROM tickets WHERE channel_id = ?",
            (channel_id,),
        )
        row = await cursor.fetchone()
        return TicketRecord.from_row(dict(row)) if row else None

    async def get_open_ticket_by_user(self, guild_id: int, user_id: int) -> TicketRecord | None:
        """Prüft, ob ein Nutzer bereits ein offenes Ticket hat."""
        cursor = await self.conn.execute(
            """
            SELECT * FROM tickets
            WHERE guild_id = ? AND opener_id = ? AND status IN (?, ?)
            LIMIT 1
            """,
            (guild_id, user_id, TicketStatus.OPEN.value, TicketStatus.CLAIMED.value),
        )
        row = await cursor.fetchone()
        return TicketRecord.from_row(dict(row)) if row else None

    async def update_ticket(
        self,
        ticket_id: int,
        *,
        status: TicketStatus | None = None,
        claimed_by_id: int | None = None,
        clear_claimed_by: bool = False,
        reason: str | None = None,
        closed_at: datetime | None = None,
    ) -> TicketRecord | None:
        """Aktualisiert Ticket-Felder."""
        ticket = await self.get_ticket(ticket_id)
        if ticket is None:
            return None

        updates: dict[str, Any] = {}
        if status is not None:
            updates["status"] = status.value
        if clear_claimed_by:
            updates["claimed_by_id"] = None
        elif claimed_by_id is not None:
            updates["claimed_by_id"] = claimed_by_id
        if reason is not None:
            updates["reason"] = reason
        if closed_at is not None:
            updates["closed_at"] = closed_at.isoformat()

        if not updates:
            return ticket

        columns = ", ".join(f"{key} = ?" for key in updates)
        values = list(updates.values()) + [ticket_id]
        await self.conn.execute(
            f"UPDATE tickets SET {columns} WHERE id = ?",
            values,
        )
        await self.conn.commit()
        return await self.get_ticket(ticket_id)

    async def get_open_tickets_for_guild(self, guild_id: int) -> list[TicketRecord]:
        """Lädt alle offenen Tickets eines Servers."""
        cursor = await self.conn.execute(
            """
            SELECT * FROM tickets
            WHERE guild_id = ? AND status IN (?, ?)
            ORDER BY id
            """,
            (guild_id, TicketStatus.OPEN.value, TicketStatus.CLAIMED.value),
        )
        rows = await cursor.fetchall()
        return [TicketRecord.from_row(dict(row)) for row in rows]

    async def get_all_open_tickets(self) -> list[TicketRecord]:
        """Lädt alle offenen Tickets (für persistente Views nach Neustart)."""
        cursor = await self.conn.execute(
            """
            SELECT * FROM tickets
            WHERE status IN (?, ?)
            ORDER BY id
            """,
            (TicketStatus.OPEN.value, TicketStatus.CLAIMED.value),
        )
        rows = await cursor.fetchall()
        return [TicketRecord.from_row(dict(row)) for row in rows]

    # ── Pets ────────────────────────────────────────────────────────

    async def create_pet(self, pet: PetRecord) -> PetRecord:
        """Erstellt ein neues Pet."""
        now = datetime.now(timezone.utc).isoformat()
        adoption = pet.adoption_date.isoformat() if pet.adoption_date else now
        last = pet.last_interaction.isoformat() if pet.last_interaction else now
        cursor = await self.conn.execute(
            """
            INSERT INTO pets (
                owner_id, guild_id, name, species, level, xp, mood,
                favorite_activity, personality, catchphrase, adoption_date,
                last_interaction, total_interactions, evolution_stage, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pet.owner_id,
                pet.guild_id,
                pet.name,
                pet.species,
                pet.level,
                pet.xp,
                pet.mood,
                pet.favorite_activity,
                pet.personality,
                pet.catchphrase,
                adoption,
                last,
                pet.total_interactions,
                pet.evolution_stage,
                int(pet.is_active),
            ),
        )
        await self.conn.commit()
        created = await self.get_pet(cursor.lastrowid)
        assert created is not None
        return created

    async def get_pet(self, pet_id: int) -> PetRecord | None:
        """Lädt ein Pet anhand der ID."""
        cursor = await self.conn.execute("SELECT * FROM pets WHERE id = ?", (pet_id,))
        row = await cursor.fetchone()
        return PetRecord.from_row(dict(row)) if row else None

    async def get_pets_by_owner(self, guild_id: int, owner_id: int) -> list[PetRecord]:
        """Lädt alle Pets eines Besitzers."""
        cursor = await self.conn.execute(
            """
            SELECT * FROM pets
            WHERE guild_id = ? AND owner_id = ?
            ORDER BY is_active DESC, adoption_date ASC
            """,
            (guild_id, owner_id),
        )
        rows = await cursor.fetchall()
        return [PetRecord.from_row(dict(row)) for row in rows]

    async def get_active_pet(self, guild_id: int, owner_id: int) -> PetRecord | None:
        """Lädt das aktive Pet eines Besitzers."""
        cursor = await self.conn.execute(
            """
            SELECT * FROM pets
            WHERE guild_id = ? AND owner_id = ? AND is_active = 1
            LIMIT 1
            """,
            (guild_id, owner_id),
        )
        row = await cursor.fetchone()
        return PetRecord.from_row(dict(row)) if row else None

    async def set_active_pet(self, guild_id: int, owner_id: int, pet_id: int) -> PetRecord | None:
        """Setzt ein Pet als aktiv und deaktiviert alle anderen des Besitzers."""
        pet = await self.get_pet(pet_id)
        if pet is None or pet.guild_id != guild_id or pet.owner_id != owner_id:
            return None
        await self.conn.execute(
            "UPDATE pets SET is_active = 0 WHERE guild_id = ? AND owner_id = ?",
            (guild_id, owner_id),
        )
        await self.conn.execute(
            "UPDATE pets SET is_active = 1 WHERE id = ?",
            (pet_id,),
        )
        await self.conn.commit()
        return await self.get_pet(pet_id)

    async def save_pet(self, pet: PetRecord) -> PetRecord:
        """Speichert Pet-Daten."""
        adoption = pet.adoption_date.isoformat() if pet.adoption_date else None
        last = pet.last_interaction.isoformat() if pet.last_interaction else None
        await self.conn.execute(
            """
            UPDATE pets SET
                name = ?, species = ?, level = ?, xp = ?, mood = ?,
                favorite_activity = ?, personality = ?, catchphrase = ?,
                adoption_date = ?, last_interaction = ?, total_interactions = ?,
                evolution_stage = ?, is_active = ?
            WHERE id = ?
            """,
            (
                pet.name,
                pet.species,
                pet.level,
                pet.xp,
                pet.mood,
                pet.favorite_activity,
                pet.personality,
                pet.catchphrase,
                adoption,
                last,
                pet.total_interactions,
                pet.evolution_stage,
                int(pet.is_active),
                pet.id,
            ),
        )
        await self.conn.commit()
        return pet

    async def get_pet_leaderboard(
        self,
        guild_id: int,
        *,
        sort_by: str = "level",
        limit: int = 10,
    ) -> list[PetRecord]:
        """Top-N Pets eines Servers."""
        order_map = {
            "level": "level DESC, xp DESC, total_interactions DESC",
            "xp": "xp DESC, level DESC, total_interactions DESC",
            "interactions": "total_interactions DESC, level DESC, xp DESC",
        }
        order = order_map.get(sort_by, order_map["level"])
        cursor = await self.conn.execute(
            f"""
            SELECT * FROM pets
            WHERE guild_id = ?
            ORDER BY {order}
            LIMIT ?
            """,
            (guild_id, limit),
        )
        rows = await cursor.fetchall()
        return [PetRecord.from_row(dict(row)) for row in rows]

    async def get_pet_cooldown(
        self,
        guild_id: int,
        owner_id: int,
        cooldown_type: PetCooldownType,
    ) -> datetime | None:
        """Lädt Ablaufzeit eines Pet-Cooldowns."""
        cursor = await self.conn.execute(
            """
            SELECT expires_at FROM pet_cooldowns
            WHERE guild_id = ? AND owner_id = ? AND cooldown_type = ?
            """,
            (guild_id, owner_id, cooldown_type.value),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        raw = row["expires_at"]
        return datetime.fromisoformat(raw) if isinstance(raw, str) and raw else None

    async def set_pet_cooldown(
        self,
        guild_id: int,
        owner_id: int,
        cooldown_type: PetCooldownType,
        expires_at: datetime,
    ) -> None:
        """Speichert einen Pet-Cooldown."""
        await self.conn.execute(
            """
            INSERT INTO pet_cooldowns (guild_id, owner_id, cooldown_type, expires_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, owner_id, cooldown_type) DO UPDATE SET
                expires_at = excluded.expires_at
            """,
            (guild_id, owner_id, cooldown_type.value, expires_at.isoformat()),
        )
        await self.conn.commit()

    async def clear_pet_cooldown(
        self,
        guild_id: int,
        owner_id: int,
        cooldown_type: PetCooldownType,
    ) -> None:
        """Entfernt einen Pet-Cooldown."""
        await self.conn.execute(
            """
            DELETE FROM pet_cooldowns
            WHERE guild_id = ? AND owner_id = ? AND cooldown_type = ?
            """,
            (guild_id, owner_id, cooldown_type.value),
        )
        await self.conn.commit()

    # ── Turniere ────────────────────────────────────────────────────

    async def create_tournament(
        self,
        guild_id: int,
        name: str,
        game: str,
        max_teams: int,
        *,
        description: str = "",
    ) -> TournamentRecord:
        """Erstellt ein neues Turnier."""
        created_at = datetime.now(timezone.utc).isoformat()
        cursor = await self.conn.execute(
            """
            INSERT INTO turniere (guild_id, name, game, description, max_teams, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (guild_id, name, game, description, max_teams, TournamentStatus.OPEN.value, created_at),
        )
        await self.conn.commit()
        tournament = await self.get_tournament(cursor.lastrowid)
        assert tournament is not None
        return tournament

    async def get_tournament(self, tournament_id: int) -> TournamentRecord | None:
        """Lädt ein Turnier per ID."""
        cursor = await self.conn.execute("SELECT * FROM turniere WHERE id = ?", (tournament_id,))
        row = await cursor.fetchone()
        return TournamentRecord.from_row(dict(row)) if row else None

    async def get_tournaments_for_guild(self, guild_id: int) -> list[TournamentRecord]:
        """Listet alle Turniere eines Servers."""
        cursor = await self.conn.execute(
            "SELECT * FROM turniere WHERE guild_id = ? ORDER BY id DESC",
            (guild_id,),
        )
        rows = await cursor.fetchall()
        return [TournamentRecord.from_row(dict(row)) for row in rows]

    async def update_tournament_status(
        self,
        tournament_id: int,
        status: TournamentStatus,
    ) -> TournamentRecord | None:
        """Setzt den Turnier-Status."""
        await self.conn.execute(
            "UPDATE turniere SET status = ? WHERE id = ?",
            (status.value, tournament_id),
        )
        await self.conn.commit()
        return await self.get_tournament(tournament_id)

    async def update_tournament_interface(
        self,
        tournament_id: int,
        channel_id: int,
        message_id: int,
    ) -> None:
        """Speichert die öffentliche Turnier-Interface-Nachricht."""
        await self.conn.execute(
            """
            UPDATE turniere
            SET interface_channel_id = ?, interface_message_id = ?
            WHERE id = ?
            """,
            (channel_id, message_id, tournament_id),
        )
        await self.conn.commit()

    async def get_tournaments_with_interface(self) -> list[TournamentRecord]:
        """Lädt Turniere mit gespeichertem Interface-Embed."""
        cursor = await self.conn.execute(
            """
            SELECT * FROM turniere
            WHERE interface_message_id IS NOT NULL
            ORDER BY id DESC
            """
        )
        rows = await cursor.fetchall()
        return [TournamentRecord.from_row(dict(row)) for row in rows]

    async def delete_tournament(self, tournament_id: int) -> bool:
        """Löscht ein Turnier inkl. Teams, Maps und Matches."""
        cursor = await self.conn.execute("DELETE FROM turniere WHERE id = ?", (tournament_id,))
        await self.conn.commit()
        return cursor.rowcount > 0

    async def add_tournament_map(self, tournament_id: int, mapname: str) -> bool:
        """Fügt eine Map zum Turnier-Pool hinzu."""
        try:
            await self.conn.execute(
                "INSERT INTO turnier_maps (tournament_id, mapname) VALUES (?, ?)",
                (tournament_id, mapname),
            )
            await self.conn.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

    async def remove_tournament_map(self, tournament_id: int, mapname: str) -> bool:
        """Entfernt eine Map aus dem Pool."""
        cursor = await self.conn.execute(
            "DELETE FROM turnier_maps WHERE tournament_id = ? AND mapname = ?",
            (tournament_id, mapname),
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def get_tournament_maps(self, tournament_id: int) -> list[str]:
        """Gibt alle Maps eines Turniers zurück."""
        cursor = await self.conn.execute(
            "SELECT mapname FROM turnier_maps WHERE tournament_id = ? ORDER BY id",
            (tournament_id,),
        )
        rows = await cursor.fetchall()
        return [row["mapname"] for row in rows]

    async def create_tournament_team(
        self,
        tournament_id: int,
        name: str,
        captain_id: int,
    ) -> TournamentTeamRecord:
        """Erstellt ein Team mit Captain als erstem Mitglied."""
        cursor = await self.conn.execute(
            """
            INSERT INTO turnier_teams (tournament_id, name, captain_id, registered)
            VALUES (?, ?, ?, 0)
            """,
            (tournament_id, name, captain_id),
        )
        team_id = cursor.lastrowid
        await self.conn.execute(
            "INSERT INTO turnier_team_members (team_id, user_id) VALUES (?, ?)",
            (team_id, captain_id),
        )
        await self.conn.commit()
        team = await self.get_tournament_team(team_id)
        assert team is not None
        return team

    async def get_tournament_team(self, team_id: int) -> TournamentTeamRecord | None:
        """Lädt ein Team per ID."""
        cursor = await self.conn.execute("SELECT * FROM turnier_teams WHERE id = ?", (team_id,))
        row = await cursor.fetchone()
        return TournamentTeamRecord.from_row(dict(row)) if row else None

    async def get_tournament_team_by_name(
        self,
        tournament_id: int,
        name: str,
    ) -> TournamentTeamRecord | None:
        """Lädt ein Team anhand des Namens."""
        cursor = await self.conn.execute(
            "SELECT * FROM turnier_teams WHERE tournament_id = ? AND name = ? COLLATE NOCASE",
            (tournament_id, name),
        )
        row = await cursor.fetchone()
        return TournamentTeamRecord.from_row(dict(row)) if row else None

    async def get_tournament_teams(self, tournament_id: int) -> list[TournamentTeamRecord]:
        """Listet alle Teams eines Turniers."""
        cursor = await self.conn.execute(
            "SELECT * FROM turnier_teams WHERE tournament_id = ? ORDER BY id",
            (tournament_id,),
        )
        rows = await cursor.fetchall()
        return [TournamentTeamRecord.from_row(dict(row)) for row in rows]

    async def get_registered_teams(self, tournament_id: int) -> list[TournamentTeamRecord]:
        """Gibt angemeldete Teams zurück."""
        cursor = await self.conn.execute(
            "SELECT * FROM turnier_teams WHERE tournament_id = ? AND registered = 1 ORDER BY id",
            (tournament_id,),
        )
        rows = await cursor.fetchall()
        return [TournamentTeamRecord.from_row(dict(row)) for row in rows]

    async def count_registered_teams(self, tournament_id: int) -> int:
        """Zählt angemeldete Teams."""
        cursor = await self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM turnier_teams WHERE tournament_id = ? AND registered = 1",
            (tournament_id,),
        )
        row = await cursor.fetchone()
        return int(row["cnt"]) if row else 0

    async def register_tournament_team(self, team_id: int) -> None:
        """Meldet ein Team offiziell an."""
        await self.conn.execute(
            "UPDATE turnier_teams SET registered = 1 WHERE id = ?",
            (team_id,),
        )
        await self.conn.commit()

    async def add_team_member(self, team_id: int, user_id: int) -> bool:
        """Fügt ein Mitglied zu einem Team hinzu."""
        try:
            await self.conn.execute(
                "INSERT INTO turnier_team_members (team_id, user_id) VALUES (?, ?)",
                (team_id, user_id),
            )
            await self.conn.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

    async def remove_team_member(self, team_id: int, user_id: int) -> bool:
        """Entfernt ein Mitglied aus einem Team."""
        cursor = await self.conn.execute(
            "DELETE FROM turnier_team_members WHERE team_id = ? AND user_id = ?",
            (team_id, user_id),
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def get_team_members(self, team_id: int) -> list[int]:
        """Gibt User-IDs aller Teammitglieder zurück."""
        cursor = await self.conn.execute(
            "SELECT user_id FROM turnier_team_members WHERE team_id = ?",
            (team_id,),
        )
        rows = await cursor.fetchall()
        return [row["user_id"] for row in rows]

    async def is_team_member(self, team_id: int, user_id: int) -> bool:
        """Prüft Teammitgliedschaft."""
        cursor = await self.conn.execute(
            "SELECT 1 FROM turnier_team_members WHERE team_id = ? AND user_id = ?",
            (team_id, user_id),
        )
        return await cursor.fetchone() is not None

    async def user_in_tournament_team(self, tournament_id: int, user_id: int) -> bool:
        """Prüft, ob ein User bereits in einem Team des Turniers ist."""
        cursor = await self.conn.execute(
            """
            SELECT 1 FROM turnier_team_members m
            JOIN turnier_teams t ON t.id = m.team_id
            WHERE t.tournament_id = ? AND m.user_id = ?
            LIMIT 1
            """,
            (tournament_id, user_id),
        )
        return await cursor.fetchone() is not None

    async def update_team_message_id(self, team_id: int, message_id: int | None) -> None:
        """Speichert die Nachrichten-ID des Team-Interfaces."""
        await self.conn.execute(
            "UPDATE turnier_teams SET message_id = ? WHERE id = ?",
            (message_id, team_id),
        )
        await self.conn.commit()

    async def update_team_interface(
        self,
        team_id: int,
        *,
        message_id: int | None = None,
        interface_channel_id: int | None = None,
    ) -> None:
        """Speichert Kanal und Nachricht des Team-Interfaces."""
        fields: list[str] = []
        values: list[Any] = []
        if message_id is not None:
            fields.append("message_id = ?")
            values.append(message_id)
        if interface_channel_id is not None:
            fields.append("interface_channel_id = ?")
            values.append(interface_channel_id)
        if not fields:
            return
        values.append(team_id)
        await self.conn.execute(
            f"UPDATE turnier_teams SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        await self.conn.commit()

    async def get_teams_with_persistent_message(self) -> list[TournamentTeamRecord]:
        """Lädt Teams mit gespeichertem Interface (für persistente Views)."""
        cursor = await self.conn.execute(
            "SELECT * FROM turnier_teams WHERE message_id IS NOT NULL",
        )
        rows = await cursor.fetchall()
        return [TournamentTeamRecord.from_row(dict(row)) for row in rows]

    async def get_captain_teams_for_guild(
        self,
        guild_id: int,
        captain_id: int,
    ) -> list[TournamentTeamRecord]:
        """Teams eines Captains auf dem Server."""
        cursor = await self.conn.execute(
            """
            SELECT t.* FROM turnier_teams t
            JOIN turniere tr ON tr.id = t.tournament_id
            WHERE tr.guild_id = ? AND t.captain_id = ?
            ORDER BY t.id DESC
            """,
            (guild_id, captain_id),
        )
        rows = await cursor.fetchall()
        return [TournamentTeamRecord.from_row(dict(row)) for row in rows]

    async def get_open_tournaments_for_user(
        self,
        guild_id: int,
        user_id: int,
    ) -> list[TournamentRecord]:
        """Offene Turniere, in denen der User noch keinem Team angehört."""
        from database.models import TournamentStatus

        tournaments = await self.get_tournaments_for_guild(guild_id)
        result: list[TournamentRecord] = []
        for tournament in tournaments:
            if tournament.status != TournamentStatus.OPEN:
                continue
            if await self.user_in_tournament_team(tournament.id, user_id):
                continue
            result.append(tournament)
        return result

    async def create_tournament_match(
        self,
        tournament_id: int,
        round_num: int,
        team1_id: int | None,
        team2_id: int | None,
        *,
        map_name: str = "",
        status: TournamentMatchStatus = TournamentMatchStatus.OPEN,
        winner_id: int | None = None,
    ) -> TournamentMatchRecord:
        """Erstellt ein Match."""
        cursor = await self.conn.execute(
            """
            INSERT INTO turnier_matches (
                tournament_id, round, team1_id, team2_id, map,
                winner_id, status, message_id, reported_by_team_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL)
            """,
            (
                tournament_id,
                round_num,
                team1_id,
                team2_id,
                map_name,
                winner_id,
                status.value,
            ),
        )
        await self.conn.commit()
        match = await self.get_tournament_match(cursor.lastrowid)
        assert match is not None
        return match

    async def get_tournament_match(self, match_id: int) -> TournamentMatchRecord | None:
        """Lädt ein Match per ID."""
        cursor = await self.conn.execute("SELECT * FROM turnier_matches WHERE id = ?", (match_id,))
        row = await cursor.fetchone()
        return TournamentMatchRecord.from_row(dict(row)) if row else None

    async def get_tournament_matches(
        self,
        tournament_id: int,
        *,
        round_num: int | None = None,
    ) -> list[TournamentMatchRecord]:
        """Listet Matches eines Turniers."""
        if round_num is not None:
            cursor = await self.conn.execute(
                """
                SELECT * FROM turnier_matches
                WHERE tournament_id = ? AND round = ?
                ORDER BY id
                """,
                (tournament_id, round_num),
            )
        else:
            cursor = await self.conn.execute(
                "SELECT * FROM turnier_matches WHERE tournament_id = ? ORDER BY round, id",
                (tournament_id,),
            )
        rows = await cursor.fetchall()
        return [TournamentMatchRecord.from_row(dict(row)) for row in rows]

    async def get_active_tournament_matches(self) -> list[TournamentMatchRecord]:
        """Lädt alle nicht abgeschlossenen Matches (für View-Restore)."""
        cursor = await self.conn.execute(
            """
            SELECT * FROM turnier_matches
            WHERE status != ?
            ORDER BY id
            """,
            (TournamentMatchStatus.FINISHED.value,),
        )
        rows = await cursor.fetchall()
        return [TournamentMatchRecord.from_row(dict(row)) for row in rows]

    async def update_tournament_match(
        self,
        match_id: int,
        **fields: Any,
    ) -> TournamentMatchRecord | None:
        """Aktualisiert Match-Felder."""
        if "status" in fields and isinstance(fields["status"], TournamentMatchStatus):
            fields["status"] = fields["status"].value
        if not fields:
            return await self.get_tournament_match(match_id)
        columns = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [match_id]
        await self.conn.execute(
            f"UPDATE turnier_matches SET {columns} WHERE id = ?",
            values,
        )
        await self.conn.commit()
        return await self.get_tournament_match(match_id)

    async def redistribute_match_maps(
        self,
        tournament_id: int,
        maps: list[str],
    ) -> int:
        """Verteilt Maps round-robin auf offene Matches. Gibt Anzahl zurück."""
        cursor = await self.conn.execute(
            """
            SELECT id FROM turnier_matches
            WHERE tournament_id = ? AND status != ?
            ORDER BY round, id
            """,
            (tournament_id, TournamentMatchStatus.FINISHED.value),
        )
        rows = await cursor.fetchall()
        if not rows:
            return 0
        count = 0
        for index, row in enumerate(rows):
            map_name = maps[index % len(maps)] if maps else ""
            await self.conn.execute(
                "UPDATE turnier_matches SET map = ? WHERE id = ?",
                (map_name, row["id"]),
            )
            count += 1
        await self.conn.commit()
        return count

    async def delete_tournament_matches(self, tournament_id: int) -> list[int]:
        """Löscht alle Matches und gibt message_ids zurück."""
        cursor = await self.conn.execute(
            "SELECT message_id FROM turnier_matches WHERE tournament_id = ? AND message_id IS NOT NULL",
            (tournament_id,),
        )
        rows = await cursor.fetchall()
        message_ids = [row["message_id"] for row in rows if row["message_id"]]
        await self.conn.execute("DELETE FROM turnier_matches WHERE tournament_id = ?", (tournament_id,))
        await self.conn.commit()
        return message_ids

    async def tournament_has_matches(self, tournament_id: int) -> bool:
        """Prüft, ob das Turnier bereits Matches hat."""
        cursor = await self.conn.execute(
            "SELECT 1 FROM turnier_matches WHERE tournament_id = ? LIMIT 1",
            (tournament_id,),
        )
        return await cursor.fetchone() is not None

    async def get_max_round(self, tournament_id: int) -> int:
        """Gibt die höchste Rundennummer zurück."""
        cursor = await self.conn.execute(
            "SELECT MAX(round) AS max_round FROM turnier_matches WHERE tournament_id = ?",
            (tournament_id,),
        )
        row = await cursor.fetchone()
        return int(row["max_round"]) if row and row["max_round"] is not None else 0
