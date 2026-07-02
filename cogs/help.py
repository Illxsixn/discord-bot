"""
Help-Cog mit übersichtlicher Slash-Command-Hilfe.

Zeigt alle verfügbaren Befehle gruppiert nach Kategorie
und optional gefiltert nach Bereich. Mehrseitige Übersichten
werden per Buttons durchblättert.
"""

from __future__ import annotations

import enum
import logging

import discord
from discord import app_commands
from discord.ext import commands

from config import Config
from utils.embeds import BRAND_ICON_ATTACHMENT, apply_brand_footer, brand_name, error_embed, info_embed

logger = logging.getLogger(__name__)

DISCORD_FIELD_LIMIT = 1024
HELP_VIEW_TIMEOUT = 600.0


class HelpCategory(enum.Enum):
    """Verfügbare Help-Kategorien (Discord Choice-Werte)."""

    Allgemein = "general"
    Moderation = "moderation"
    Welcome = "welcome"
    Leave = "leave"
    Logs = "logs"
    AutoMod = "automod"
    Einstellungen = "settings"
    Levels = "levels"
    Pets = "pets"
    Spiele = "games"
    Challenges = "challenges"
    ReactionRoles = "reactionrole"
    Polls = "poll"
    Giveaways = "giveaway"
    Tickets = "ticket"
    Tournaments = "tournament"


HELP_CATEGORIES: dict[str, dict[str, object]] = {
    HelpCategory.Allgemein.value: {
        "label": "Allgemein",
        "emoji": "📋",
        "access": "Alle",
        "commands": [
            ("/help", "Alle Befehle nach Kategorie"),
            ("/changelog", "Bot-Updates und Versionshistorie"),
        ],
    },
    HelpCategory.Moderation.value: {
        "label": "Moderation",
        "emoji": "🛡️",
        "access": "Moderatoren",
        "commands": [
            ("/ban", "Bannt ein Mitglied vom Server"),
            ("/kick", "Kickt ein Mitglied vom Server"),
            ("/timeout", "Setzt ein Mitglied in Timeout"),
            ("/untimeout", "Hebt einen Timeout auf"),
            ("/warn", "Verwarnt ein Mitglied"),
            ("/unwarn", "Entfernt eine Verwarnung"),
            ("/warnings", "Zeigt Verwarnungen eines Mitglieds"),
            ("/clear", "Löscht Nachrichten in einem Kanal"),
            ("/slowmode", "Setzt Slowmode für den Kanal"),
            ("/lock", "Sperrt den Kanal für @everyone"),
            ("/unlock", "Entsperrt den Kanal"),
            ("/nickname", "Ändert den Nickname eines Mitglieds"),
            ("/mute", "Mutet ein Mitglied"),
            ("/unmute", "Hebt einen Mute auf"),
        ],
    },
    HelpCategory.Welcome.value: {
        "label": "Welcome",
        "emoji": "👋",
        "access": "Administratoren",
        "commands": [
            ("/welcome setup", "Richtet das Welcome-System ein"),
            ("/welcome channel", "Setzt den Welcome-Kanal"),
            ("/welcome message", "Passt die Willkommensnachricht an"),
            ("/welcome enable", "Aktiviert Welcome-Nachrichten"),
            ("/welcome disable", "Deaktiviert Welcome-Nachrichten"),
            ("/welcome test", "Sendet eine Test-Willkommensnachricht"),
        ],
    },
    HelpCategory.Leave.value: {
        "label": "Leave",
        "emoji": "🚪",
        "access": "Administratoren",
        "commands": [
            ("/leave setup", "Richtet das Leave-System ein"),
            ("/leave channel", "Setzt den Leave-Kanal"),
            ("/leave message", "Passt die Abschiedsnachricht an"),
            ("/leave enable", "Aktiviert Leave-Nachrichten"),
            ("/leave disable", "Deaktiviert Leave-Nachrichten"),
            ("/leave test", "Sendet eine Test-Abschiedsnachricht"),
        ],
    },
    HelpCategory.Logs.value: {
        "label": "Logs",
        "emoji": "📋",
        "access": "Administratoren",
        "commands": [
            ("/logs setup", "Richtet das Log-System ein"),
            ("/logs channel", "Setzt den Log-Kanal"),
            ("/logs enable", "Aktiviert Server-Logs"),
            ("/logs disable", "Deaktiviert Server-Logs"),
        ],
    },
    HelpCategory.AutoMod.value: {
        "label": "AutoMod",
        "emoji": "🤖",
        "access": "Administratoren",
        "commands": [
            ("/automod enable", "Aktiviert AutoMod"),
            ("/automod disable", "Deaktiviert AutoMod"),
            ("/automod spam", "Spam-Schutz ein-/ausschalten"),
            ("/automod invites", "Discord-Einladungen blockieren"),
            ("/automod links", "Links blockieren"),
            ("/automod badwords", "Verbotene Wörter verwalten"),
            ("/automod punishment", "Strafe bei Verstößen festlegen"),
        ],
    },
    HelpCategory.Einstellungen.value: {
        "label": "Einstellungen",
        "emoji": "⚙️",
        "access": "Administratoren",
        "commands": [
            ("/settings view", "Zeigt alle Server-Einstellungen"),
            ("/settings reset", "Setzt alle Einstellungen zurück"),
        ],
    },
    HelpCategory.Levels.value: {
        "label": "Level",
        "emoji": "📈",
        "access": "Alle / Admins (Config)",
        "commands": [
            ("/levels level", "Zeigt Level und XP"),
            ("/levels rank", "Alias für /levels level"),
            ("/levels leaderboard", "Server-Ranking anzeigen"),
            ("/levels enable", "Level-System aktivieren (Admin)"),
            ("/levels disable", "Level-System deaktivieren (Admin)"),
            ("/levels announce", "Level-Up Kanal konfigurieren"),
        ],
        "hints": [
            "5 XP pro Nachricht (10 Sekunden Cooldown)",
            "Bonus-XP durch Spiele und tägliche Aufgaben",
        ],
    },
    HelpCategory.Pets.value: {
        "label": "Pets",
        "emoji": "🐾",
        "access": "Alle",
        "commands": [
            ("/pet ei", "Öffnet ein Pet-Ei (1× täglich)"),
            ("/pets", "Zeigt deine Pet-Sammlung und wechselt das aktive Pet"),
            ("/pet dex", "Pet-Sammlungsbuch — alle 30 Arten (öffentlich)"),
            ("/pet info", "Infos über dein aktives Pet"),
            ("/pet display", "KI-Portrait deines Pets (Agnes, gecacht)"),
            ("/pet play", "Impuls-Rush — 3 schnelle Runden (5 Min. Cooldown)"),
            ("/pet rename", "Benennt dein aktives Pet um (7 Tage Cooldown)"),
            ("/pet leaderboard", "Pet-Rangliste des Servers"),
        ],
        "hints": [
            "Zero-Stress: Kein Hunger, kein Tod, kein Zwang",
            "Pet-XP durch Aktivität, Spiele, Aufgaben und /pet play",
            "Evolution bei Level 10, 25 und 50 — 🌱 Teen · ✨ Erwachsen · 👑 Meisterform (Farbe & Emoji)",
            "Seltenheits-Bonus (aktives Pet): Common +2 % • Uncommon +4 % • Rare +6 % • Epic +8 % • Legendary +10 % (Spieler- & Pet-XP)",
            "Pet-Befehle werden im Kanal angezeigt (für alle sichtbar)",
            "`/pet dex` — gesammelte ✅, fehlende ❓",
        ],
    },
    HelpCategory.Spiele.value: {
        "label": "Spiele",
        "emoji": "🎮",
        "access": "Alle",
        "commands": [
            ("/guess-start", "Startet Zahlenraten (1–100) im Kanal"),
            ("/guess", "Gibt einen Tipp ab (5 Min. Cooldown)"),
            ("/guess-leaderboard", "Bestenliste Zahlenraten"),
        ],
        "hints": [
            f"Gewinner erhalten **{Config.GAME_WIN_XP} XP** (wenn Level-System aktiv ist)",
            f"`/guess` hat einen Cooldown von **{Config.GUESS_COOLDOWN // 60} Minuten**",
        ],
    },
    HelpCategory.Challenges.value: {
        "label": "Tägliche Aufgaben",
        "emoji": "📅",
        "access": "Alle",
        "commands": [
            ("/daily-challenges", "Zeigt deine 4 Tagesaufgaben und Fortschritt"),
        ],
        "hints": [
            f"**{Config.DAILY_CHALLENGE_COUNT - Config.DAILY_PET_CHALLENGE_COUNT} Level-Aufgaben** "
            f"und **{Config.DAILY_PET_CHALLENGE_COUNT} Pet-Aufgaben** (Play, Info, Aktivitäts-XP)",
            f"Level-Belohnung pro Aufgabe: **{Config.CHALLENGE_XP_MIN}–{Config.CHALLENGE_XP_MAX} XP** (fest pro Tag, zufällig)",
            f"Pet-Belohnung pro Aufgabe: **{Config.CHALLENGE_PET_XP_MIN}–{Config.CHALLENGE_PET_XP_MAX} Pet-XP** (fest pro Tag, zufällig)",
            "Reset täglich um Mitternacht (UTC)",
        ],
    },
    HelpCategory.ReactionRoles.value: {
        "label": "Reaktionsrollen",
        "emoji": "🎭",
        "access": "Administratoren",
        "commands": [
            ("/reactionrole add", "Reaktionsrolle erstellen"),
            ("/reactionrole list", "Alle Reaktionsrollen anzeigen"),
            ("/reactionrole remove", "Reaktionsrolle entfernen"),
        ],
    },
    HelpCategory.Polls.value: {
        "label": "Umfragen",
        "emoji": "📊",
        "access": "Nachrichten verwalten",
        "commands": [
            ("/poll yesno", "Ja/Nein-Umfrage erstellen"),
            ("/poll multi", "Mehrfach-Umfrage erstellen"),
            ("/poll end", "Umfrage beenden und auswerten"),
        ],
    },
    HelpCategory.Giveaways.value: {
        "label": "Gewinnspiele",
        "emoji": "🎁",
        "access": "Server verwalten",
        "commands": [
            ("/giveaway create", "Gewinnspiel erstellen"),
            ("/giveaway end", "Gewinnspiel vorzeitig beenden"),
            ("/giveaway reroll", "Neue Gewinner auslosen"),
        ],
    },
    HelpCategory.Tickets.value: {
        "label": "Tickets",
        "emoji": "🎫",
        "access": "Alle / Staff / Admin",
        "commands": [
            ("/ticket setup", "Ticket-System interaktiv einrichten (Admin)"),
            ("/ticket message", "Panel- oder Ticket-Text anpassen (Admin)"),
            ("/ticket panel", "Ticket-Panel senden (Admin)"),
            ("/ticket close", "Ticket im Kanal schließen"),
            ("/ticket claim", "Ticket übernehmen (Staff)"),
            ("/ticket add", "Mitglied zum Ticket hinzufügen (Staff)"),
            ("/ticket remove", "Mitglied aus Ticket entfernen (Staff)"),
            ("/ticket list", "Offene Tickets anzeigen (Staff)"),
        ],
        "hints": [
            "Setup per Buttons: Staff-Rolle, Kategorie, Log-Kanal, Texte anpassen",
            "Platzhalter: `{user}`, `{server}`, `{ticket_id}`, `{button}`",
            "Nutzer erstellen Tickets über das Panel mit dem Button **Ticket erstellen**",
            "Pro Person ist jeweils ein offenes Ticket möglich",
        ],
    },
    HelpCategory.Tournaments.value: {
        "label": "Turniere",
        "emoji": "🏆",
        "access": "Alle / Administratoren",
        "commands": [
            ("/turnier_erstellen", "Neues Turnier anlegen (Admin)"),
            ("/turnier_status setzen", "Status offen/geschlossen/beendet (Admin)"),
            ("/turnier_loeschen", "Turnier löschen ohne Bracket (Admin)"),
            ("/turnier_liste", "Alle Turniere auflisten"),
            ("/turnier_info", "Turnier-Details und Teams"),
            ("/turnier_maps_hinzufuegen", "Maps zum Pool hinzufügen (Admin)"),
            ("/turnier_maps_entfernen", "Map aus Pool entfernen (Admin)"),
            ("/turnier_maps_anzeigen", "Map-Pool anzeigen"),
            ("/turnier_maps_neu_verteilen", "Maps auf Matches verteilen (Admin)"),
            ("/turnier_team_erstellen", "Team gründen (Captain)"),
            ("/turnier_team_beitreten", "Bestehendem Team beitreten"),
            ("/turnier_anmelden", "Team offiziell anmelden (Captain)"),
            ("/turnier_team_zuweisen", "User zu Team hinzufügen (Admin)"),
            ("/turnier_team_entfernen", "User aus Team entfernen (Admin)"),
            ("/turnier_baum_erstellen", "Runde 1 generieren (Admin)"),
            ("/turnier_baum_anzeigen", "Bracket-Übersicht"),
            ("/turnier_abbrechen", "Turnier zurücksetzen (Admin)"),
            ("/turnier_kanal_setzen", "Kanal für Match-Embeds (Admin)"),
            ("/turnier_match_info", "Details zu einem Match"),
        ],
        "hints": [
            "Ablauf: Turnier erstellen → Teams anmelden → Status schließen → Bracket erstellen",
            "Matches laufen per Buttons im Turnier-Kanal (Sieg melden, bestätigen, Einspruch)",
            "Admins entscheiden bei Einspruch; nächste Runde startet automatisch",
        ],
    },
}


def _format_hints(hints_list: list[str]) -> str:
    """Formatiert reine Hinweise ohne Command-Syntax."""
    return "\n".join(f"• {hint}" for hint in hints_list)


def _category_commands(category_key: str) -> list[tuple[str, str]]:
    """Gibt nur echte Befehle einer Kategorie zurück."""
    return list(HELP_CATEGORIES[category_key]["commands"])  # type: ignore[arg-type, return-value]


def _category_hints(category_key: str) -> list[str]:
    """Gibt optionale Hinweise einer Kategorie zurück."""
    hints = HELP_CATEGORIES[category_key].get("hints", [])
    return list(hints) if isinstance(hints, list) else []


def _append_hint_fields(
    category_key: str,
    fields: list[tuple[str, str, bool]],
) -> list[tuple[str, str, bool]]:
    """Fügt Hinweis-Feld hinzu, falls vorhanden."""
    hints = _category_hints(category_key)
    if hints:
        fields.append(("Hinweise", _format_hints(hints), False))
    return fields


def _format_commands(commands_list: list[tuple[str, str]]) -> str:
    """Formatiert Befehle als kompakte Liste."""
    return "\n".join(f"`{cmd}` — {desc}" for cmd, desc in commands_list)


def _split_command_fields(commands_list: list[tuple[str, str]]) -> list[tuple[str, str, bool]]:
    """
    Teilt lange Befehlslisten in mehrere Embed-Felder (Discord-Limit: 1024 Zeichen).

    Args:
        commands_list: Liste aus (Befehl, Beschreibung).

    Returns:
        Feld-Tupel für info_embed.
    """
    if not commands_list:
        return [("Befehle", "Keine Befehle in dieser Kategorie.", False)]

    fields: list[tuple[str, str, bool]] = []
    chunk: list[tuple[str, str]] = []
    chunk_len = 0
    part = 1

    for entry in commands_list:
        line = f"`{entry[0]}` — {entry[1]}"
        line_len = len(line) + (1 if chunk else 0)

        if chunk and chunk_len + line_len > DISCORD_FIELD_LIMIT:
            label = "Befehle" if part == 1 and len(commands_list) == len(chunk) else f"Befehle ({part})"
            fields.append((label, _format_commands(chunk), False))
            chunk = [entry]
            chunk_len = len(line)
            part += 1
        else:
            chunk.append(entry)
            chunk_len += line_len

    if chunk:
        label = "Befehle" if part == 1 else f"Befehle ({part})"
        fields.append((label, _format_commands(chunk), False))

    return fields


def _resolve_category_key(kategorie: HelpCategory | app_commands.Choice[str] | str | None) -> str | None:
    """
    Normalisiert den Kategorie-Parameter aus der Discord-Interaktion.

    Args:
        kategorie: Enum, Choice-Objekt, String oder None.

    Returns:
        Interner Kategorie-Schlüssel oder None für die Übersicht.
    """
    if kategorie is None:
        return None

    if isinstance(kategorie, HelpCategory):
        return kategorie.value

    if isinstance(kategorie, app_commands.Choice):
        kategorie = str(kategorie.value)

    if isinstance(kategorie, str) and kategorie in HELP_CATEGORIES:
        return kategorie

    return None


def _category_order() -> list[str]:
    """Gibt die feste Reihenfolge aller Help-Kategorien zurück."""
    return [member.value for member in HelpCategory]


def _total_command_count() -> int:
    """Zählt alle registrierten Befehle über alle Kategorien."""
    return sum(len(_category_commands(key)) for key in HELP_CATEGORIES)


def _apply_embed_meta(
    embed: discord.Embed,
    bot: commands.Bot,
    *,
    page: int,
    total_pages: int,
    command_count: int,
) -> discord.Embed:
    """Setzt Autor, Footer und Seitenangabe auf dem Help-Embed."""
    icon_url = f"attachment://{BRAND_ICON_ATTACHMENT}"
    embed.set_author(name=brand_name(), icon_url=icon_url)

    if total_pages > 1:
        prefix = f"Seite {page + 1}/{total_pages} • {command_count} Befehle • /help"
    else:
        prefix = f"{command_count} Befehle • /help"

    apply_brand_footer(embed, prefix=prefix)
    return embed


def _build_overview_page(bot: commands.Bot, page_index: int) -> discord.Embed:
    """Erstellt eine einzelne Übersichtsseite (frisch, für Pagination)."""
    total_cmds = _total_command_count()
    category_keys = _category_order()
    total_pages = len(category_keys)
    page_index = max(0, min(page_index, total_pages - 1))
    category_key = category_keys[page_index]
    data = HELP_CATEGORIES[category_key]
    cmds = _category_commands(category_key)
    fields = _split_command_fields(cmds)
    fields = _append_hint_fields(category_key, fields)

    embed = info_embed(
        f"{data['emoji']} {data['label']} — Befehle",
        f"**{total_cmds} Befehle** in **{len(HELP_CATEGORIES)} Kategorien**.\n"
        f"**Zugriff:** {data['access']}\n"
        "Nutze die Buttons, das Menü unten oder `/help kategorie:<Bereich>`.",
        fields=fields,
    )
    return _apply_embed_meta(
        embed,
        bot,
        page=page_index,
        total_pages=total_pages,
        command_count=len(cmds),
    )


def _build_overview_embeds(bot: commands.Bot) -> list[discord.Embed]:
    """
    Erstellt eine Help-Seite pro Kategorie mit allen Befehlen.

    Args:
        bot: Bot-Instanz für Name und Avatar.

    Returns:
        Liste der Übersichts-Embeds (eine Seite je Kategorie).
    """
    return [_build_overview_page(bot, page_index) for page_index in range(len(_category_order()))]


def _build_category_page(bot: commands.Bot, category: str, page_index: int) -> discord.Embed:
    """Erstellt eine einzelne Kategorie-Seite (frisch, für Pagination)."""
    data = HELP_CATEGORIES[category]
    cmds = _category_commands(category)
    field_groups = _split_command_fields(cmds)
    total_pages = max(len(field_groups), 1)
    page_index = max(0, min(page_index, total_pages - 1))

    description = f"**Zugriff:** {data['access']}"
    if total_pages > 1:
        description += f"\n**Abschnitt {page_index + 1}/{total_pages}**"

    fields = [field_groups[page_index]] if field_groups else [("Befehle", "Keine Befehle in dieser Kategorie.", False)]
    if page_index == total_pages - 1:
        fields = _append_hint_fields(category, fields)

    embed = info_embed(
        f"{data['emoji']} {data['label']} — Befehle",
        description,
        fields=fields,
    )
    return _apply_embed_meta(
        embed,
        bot,
        page=page_index,
        total_pages=total_pages,
        command_count=len(cmds),
    )


def _build_category_embeds(bot: commands.Bot, category: str) -> list[discord.Embed]:
    """
    Erstellt Help-Embeds für eine einzelne Kategorie (ggf. mehrere Seiten).

    Args:
        bot: Bot-Instanz.
        category: Kategorie-Schlüssel.

    Returns:
        Liste der Kategorie-Embeds.
    """
    field_groups = _split_command_fields(_category_commands(category))
    return [_build_category_page(bot, category, page_index) for page_index in range(max(len(field_groups), 1))]


def _build_help_embed(
    bot: commands.Bot,
    category: str | None = None,
    *,
    page: int = 0,
) -> discord.Embed:
    """
    Erstellt das Help-Embed für alle oder eine Kategorie.

    Args:
        bot: Bot-Instanz für Name und Avatar.
        category: Optionaler Kategorie-Schlüssel.

    Returns:
        Fertiges Help-Embed (Legacy-Helfer für einzelne Seite).
    """
    if category and category in HELP_CATEGORIES:
        embeds = _build_category_embeds(bot, category)
    else:
        embeds = _build_overview_embeds(bot)

    page_index = max(0, min(page, len(embeds) - 1))
    return embeds[page_index]


class HelpCategorySelect(discord.ui.Select):
    """Dropdown zum direkten Springen zu einer Help-Kategorie."""

    def __init__(self, paginator: "HelpPaginatorView") -> None:
        self.paginator = paginator
        options = [
            discord.SelectOption(
                label=str(HELP_CATEGORIES[key]["label"]),
                value=key,
                emoji=str(HELP_CATEGORIES[key]["emoji"]),
                default=index == paginator.current_page,
            )
            for index, key in enumerate(_category_order())
        ]
        super().__init__(
            placeholder="Kategorie wählen …",
            options=options,
            min_values=1,
            max_values=1,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """Springt zur gewählten Kategorie."""
        page = _category_order().index(self.values[0])
        await self.paginator.show_page(interaction, page)


class HelpPaginatorView(discord.ui.View):
    """Buttons und Kategorie-Menü zum Blättern durch Help-Embeds."""

    def __init__(
        self,
        bot: commands.Bot,
        *,
        author_id: int,
        current_page: int = 0,
        category: str | None = None,
        total_pages: int,
        timeout: float = HELP_VIEW_TIMEOUT,
    ) -> None:
        super().__init__(timeout=timeout)
        self.bot = bot
        self.author_id = author_id
        self.current_page = current_page
        self.category = category
        self.total_pages = total_pages
        self.is_overview = category is None

        if self.is_overview:
            self.add_item(HelpCategorySelect(self))

        self._sync_buttons()

    def build_embed(self) -> discord.Embed:
        """Erstellt das Embed für die aktuelle Seite neu."""
        if self.is_overview:
            return _build_overview_page(self.bot, self.current_page)
        return _build_category_page(self.bot, self.category, self.current_page)  # type: ignore[arg-type]

    def _sync_buttons(self) -> None:
        """Aktiviert/deaktiviert Vor- und Zurück-Button je nach Seite."""
        self.prev_page.disabled = self.current_page <= 0
        self.next_page.disabled = self.current_page >= self.total_pages - 1

    async def show_page(self, interaction: discord.Interaction, page: int) -> None:
        """Zeigt eine Help-Seite und ersetzt die View-Instanz."""
        self.current_page = max(0, min(page, self.total_pages - 1))
        new_view = HelpPaginatorView(
            self.bot,
            author_id=self.author_id,
            current_page=self.current_page,
            category=self.category,
            total_pages=self.total_pages,
        )
        embed = new_view.build_embed()

        try:
            await interaction.response.edit_message(embed=embed, view=new_view)
        except discord.HTTPException as exc:
            logger.warning("Help-Pagination edit fehlgeschlagen: %s", exc)
            if interaction.response.is_done():
                await interaction.followup.send(
                    embed=error_embed(
                        "Blättern fehlgeschlagen",
                        "Bitte führe `/help` erneut aus.",
                    ),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    embed=error_embed(
                        "Blättern fehlgeschlagen",
                        "Bitte führe `/help` erneut aus.",
                    ),
                    ephemeral=True,
                )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Nur der aufrufende Nutzer darf blättern."""
        if interaction.user.id == self.author_id:
            return True

        await interaction.response.send_message(
            embed=error_embed("Kein Zugriff", "Nur der Nutzer, der `/help` ausgeführt hat, kann blättern."),
            ephemeral=True,
        )
        return False

    async def on_timeout(self) -> None:
        """Deaktiviert Buttons nach Ablauf der Zeit."""
        for item in self.children:
            item.disabled = True  # type: ignore[union-attr]

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item,
    ) -> None:
        """Loggt View-Fehler und antwortet mit Hinweis."""
        logger.exception("Help-View Fehler (%s): %s", item, error)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    embed=error_embed("Help-Fehler", "Bitte führe `/help` erneut aus."),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    embed=error_embed("Help-Fehler", "Bitte führe `/help` erneut aus."),
                    ephemeral=True,
                )
        except discord.HTTPException:
            pass

    @discord.ui.button(label="◀ Zurück", style=discord.ButtonStyle.secondary, row=0)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Zeigt die vorherige Help-Seite."""
        await self.show_page(interaction, self.current_page - 1)

    @discord.ui.button(label="Weiter ▶", style=discord.ButtonStyle.secondary, row=0)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Zeigt die nächste Help-Seite."""
        await self.show_page(interaction, self.current_page + 1)


class HelpCog(commands.Cog):
    """Slash-Command-Hilfe für alle Bot-Befehle."""

    def __init__(self, bot: commands.Bot) -> None:
        """
        Initialisiert den Help-Cog.

        Args:
            bot: Bot-Instanz.
        """
        self.bot = bot

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Fängt Help-spezifische Fehler ab und antwortet immer sichtbar."""
        logger.exception("Help-Befehl Fehler: %s", error)
        embed = error_embed(
            "Help fehlgeschlagen",
            "Die Hilfe konnte nicht geladen werden. Bitte versuche es erneut.",
        )
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass

    @app_commands.command(name="help", description="Zeigt alle Slash Commands und ihre Funktionen.")
    @app_commands.describe(kategorie="Optional: nur Befehle einer Kategorie anzeigen")
    @app_commands.guild_only()
    async def help_command(
        self,
        interaction: discord.Interaction,
        kategorie: HelpCategory | None = None,
    ) -> None:
        """Sendet die Help-Übersicht."""
        category_key = _resolve_category_key(kategorie)
        logger.info(
            "Help angefordert von %s (%s), Kategorie: %s",
            interaction.user,
            interaction.user.id,
            category_key or "Übersicht",
        )

        embeds = (
            _build_category_embeds(self.bot, category_key)
            if category_key
            else _build_overview_embeds(self.bot)
        )

        view: HelpPaginatorView | None = None
        if len(embeds) > 1:
            view = HelpPaginatorView(
                self.bot,
                author_id=interaction.user.id,
                current_page=0,
                category=category_key,
                total_pages=len(embeds),
            )

        await interaction.response.send_message(
            embed=embeds[0] if view is None else view.build_embed(),
            view=view,
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    """Lädt den Help-Cog."""
    await bot.add_cog(HelpCog(bot))
