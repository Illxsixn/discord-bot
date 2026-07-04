"""
Admin-Wizard für Turniere: Schritt-für-Schritt mit Buttons und Fortschrittsanzeige.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

from database.models import TournamentStatus
from utils.embeds import error_embed, info_embed, spaced_lines, success_embed
from utils.permissions import bot_can_use_channel

if TYPE_CHECKING:
    from cogs.tournament import TournamentCog

STEP_LABELS = (
    "Turnier-Kanal",
    "Turnier erstellen",
    "Maps",
    "Teams & Kapazität",
    "Ablauf & Status",
    "Bracket starten",
)


@dataclass
class WizardState:
    """Fortschritt im Admin-Wizard."""

    channel: discord.TextChannel | None
    channel_ok: bool
    channel_error: str | None
    tournament_id: int | None
    tournament_name: str | None
    tournament_game: str | None
    tournament_status: TournamentStatus | None
    map_count: int
    maps: list[str]
    team_count: int
    registered_count: int
    max_teams: int
    has_matches: bool
    current_step: int
    next_step_label: str


class TournamentAdminView(discord.ui.View):
    """Basis-View mit Admin-Check für öffentliche Panel-Nachrichten."""

    def __init__(self, cog: TournamentCog, *, timeout: float | None = 180) -> None:
        super().__init__(timeout=timeout)
        self.cog = cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member) or not self.cog._is_admin(interaction.user):
            await interaction.response.send_message(
                embed=error_embed("Keine Berechtigung", "Nur Administratoren."),
                ephemeral=True,
            )
            return False
        return True


async def resolve_focus_tournament_id(
    cog: TournamentCog,
    guild_id: int,
    tournament_id: int | None = None,
) -> int | None:
    """Aktives Setup-Turnier (nicht beendet, ohne Bracket)."""
    if tournament_id is not None:
        tournament = await cog.db.get_tournament(tournament_id)
        if tournament is not None and tournament.guild_id == guild_id:
            return tournament.id
    tournaments = await cog.db.get_tournaments_for_guild(guild_id)
    for tournament in reversed(tournaments):
        if tournament.status == TournamentStatus.FINISHED:
            continue
        if await cog.db.tournament_has_matches(tournament.id):
            continue
        return tournament.id
    return None


async def compute_wizard_state(
    cog: TournamentCog,
    guild: discord.Guild,
    *,
    tournament_id: int | None = None,
) -> WizardState:
    """Ermittelt Wizard-Fortschritt und nächsten Schritt."""
    channel = await cog._get_tournament_channel(guild)
    channel_error: str | None = None
    channel_ok = channel is not None
    if channel is not None:
        allowed, msg = bot_can_use_channel(
            channel,
            send=True,
            embed_links=True,
        )
        if not allowed:
            channel_ok = False
            channel_error = msg

    focus_id = await resolve_focus_tournament_id(cog, guild.id, tournament_id)
    tournament = await cog.db.get_tournament(focus_id) if focus_id else None

    maps: list[str] = []
    map_count = 0
    team_count = 0
    registered_count = 0
    max_teams = 0
    has_matches = False
    tournament_name = None
    tournament_game = None
    tournament_status = None

    if tournament is not None:
        maps = await cog.db.get_tournament_maps(tournament.id)
        map_count = len(maps)
        teams = await cog.db.get_tournament_teams(tournament.id)
        team_count = len(teams)
        registered_count = sum(1 for t in teams if t.registered)
        max_teams = tournament.max_teams
        has_matches = await cog.db.tournament_has_matches(tournament.id)
        tournament_name = tournament.name
        tournament_game = tournament.game
        tournament_status = tournament.status

    if not channel_ok:
        current_step = 0
        next_label = "Wähle den Turnier-Kanal (Select oder `/turnier_kanal_setzen`)."
    elif tournament is None:
        current_step = 1
        next_label = "Erstelle ein neues Turnier (Name, Spiel, Max-Teams)."
    elif has_matches:
        current_step = 5
        next_label = "Bracket läuft – Matches im Turnier-Kanal verwalten."
    elif tournament_status == TournamentStatus.CLOSED and registered_count >= 2:
        current_step = 5
        next_label = "Starte das Bracket (Runde 1 wird im Turnier-Kanal gepostet)."
    elif tournament_status == TournamentStatus.CLOSED:
        current_step = 4
        next_label = "Mindestens 2 angemeldete Teams nötig, dann Bracket starten."
    elif map_count == 0 and team_count == 0:
        current_step = 2
        next_label = "Füge Maps hinzu (empfohlen) oder verwalte Teams."
    elif team_count == 0 or registered_count < 2:
        current_step = 3
        next_label = "Teams erstellen/zuweisen und mindestens 2 Teams anmelden."
    else:
        current_step = 4
        next_label = "Schließe Anmeldungen und poste die Ankündigung im Turnier-Kanal."

    return WizardState(
        channel=channel if channel_ok else None,
        channel_ok=channel_ok,
        channel_error=channel_error,
        tournament_id=focus_id,
        tournament_name=tournament_name,
        tournament_game=tournament_game,
        tournament_status=tournament_status,
        map_count=map_count,
        maps=maps,
        team_count=team_count,
        registered_count=registered_count,
        max_teams=max_teams,
        has_matches=has_matches,
        current_step=current_step,
        next_step_label=next_label,
    )


def _progress_line(state: WizardState) -> str:
    """Fortschritts-Checkliste für das Embed."""
    checks = [
        ("Kanal", state.channel_ok),
        ("Turnier", state.tournament_id is not None),
        ("Maps", state.map_count > 0),
        ("Teams", state.registered_count >= 2),
        ("Geschlossen", state.tournament_status == TournamentStatus.CLOSED),
        ("Bracket", state.has_matches),
    ]
    parts: list[str] = []
    for index, (label, done) in enumerate(checks):
        if done:
            icon = "✅"
        elif index == state.current_step:
            icon = "⏳"
        else:
            icon = "⬜"
        parts.append(f"{icon} {label}")
    return " · ".join(parts)


ADMIN_SLASH_HINT = (
    "Alternativ per Slash: `/turnier_maps_hinzufuegen`, `/turnier_maps_entfernen`, "
    "`/turnier_team_zuweisen`, `/turnier_team_entfernen`, `/turnier_status setzen`"
)


async def build_wizard_embed(
    cog: TournamentCog,
    guild: discord.Guild,
    *,
    tournament_id: int | None = None,
) -> discord.Embed:
    """Wizard-Embed mit Checkliste und nächstem Schritt."""
    state = await compute_wizard_state(cog, guild, tournament_id=tournament_id)

    channel_text = state.channel.mention if state.channel else "Nicht gesetzt"
    if state.channel_error:
        channel_text += f"\n⚠️ {state.channel_error}"

    lines = [
        f"**Fortschritt:** {_progress_line(state)}",
        f"**Schritt {state.current_step}:** {STEP_LABELS[state.current_step]}",
        f"**Nächster Schritt:** {state.next_step_label}",
        f"**Turnier-Kanal:** {channel_text}",
    ]

    if state.tournament_id is not None:
        from cogs.tournament import TOURNAMENT_STATUS_LABELS

        status_label = (
            TOURNAMENT_STATUS_LABELS[state.tournament_status]
            if state.tournament_status
            else "—"
        )
        lines.append(
            spaced_lines(
                f"**Aktives Turnier:** #{state.tournament_id} **{state.tournament_name}** ({state.tournament_game})",
                f"Status: **{status_label}** · Teams: **{state.registered_count}/{state.max_teams}** angemeldet",
            )
        )
        if state.maps:
            lines.append(f"**Map-Pool:** {', '.join(state.maps[:15])}")
        if state.tournament_id is not None and state.current_step >= 3:
            teams = await cog.db.get_tournament_teams(state.tournament_id)
            if teams:
                team_bits = []
                for team in teams[:8]:
                    flag = "✅" if team.registered else "⏳"
                    team_bits.append(f"{flag} **{team.name}**")
                lines.append(f"**Teams:** {', '.join(team_bits)}")
            lines.append(
                "Spieler gründen Teams mit **`/turnier_team`** · Captain: **`/turnier_einladen`**"
            )
        if state.current_step >= 2:
            lines.append(ADMIN_SLASH_HINT)
        if state.current_step == 4:
            lines.append(
                "**Ablauf:** Teams sammeln → Status schließen → Bracket → Matches per Buttons im Kanal"
            )

    return info_embed("🏆 Turnier-Admin · Wizard", spaced_lines(*lines))


async def build_tournament_interface_embed(
    cog: TournamentCog,
    guild: discord.Guild,
    tournament_id: int,
    *,
    bracket_started: bool = False,
) -> discord.Embed:
    """Öffentliches Turnier-Hub-Embed für den Turnier-Kanal."""
    from cogs.tournament import TOURNAMENT_STATUS_LABELS

    tournament = await cog.db.get_tournament(tournament_id)
    if tournament is None:
        return error_embed("Fehler", f"Turnier #{tournament_id} nicht gefunden.")

    registered = await cog.db.count_registered_teams(tournament_id)
    teams = await cog.db.get_tournament_teams(tournament_id)
    maps = await cog.db.get_tournament_maps(tournament_id)
    has_matches = await cog.db.tournament_has_matches(tournament_id)

    team_lines: list[str] = []
    for team in teams[:12]:
        flag = "✅" if team.registered else "⏳"
        team_lines.append(f"{flag} **{team.name}**")
    teams_text = ", ".join(team_lines) if team_lines else "Noch keine Teams"

    if has_matches or bracket_started:
        next_steps = spaced_lines(
            "Matches laufen in diesem Kanal — nutze die Buttons an den Match-Nachrichten.",
            "Übersicht: **`/turnier_baum_anzeigen`**",
        )
        headline = "🏆 Turnier läuft"
    elif tournament.status == TournamentStatus.OPEN:
        next_steps = spaced_lines(
            "Captain: **`/turnier_team`** — Team gründen & Interface-Buttons",
            "Einladen: **`/turnier_einladen @Spieler`**",
            "Anmelden: Button **Für Turnier anmelden** am Team-Interface",
        )
        headline = "🏆 Turnier — Anmeldung offen"
    elif tournament.status == TournamentStatus.CLOSED:
        next_steps = "Anmeldungen geschlossen — warte auf den Bracket-Start durch die Admins."
        headline = "🏆 Turnier — Anmeldung geschlossen"
    else:
        next_steps = "Turnier beendet."
        headline = "🏆 Turnier beendet"

    description = spaced_lines(
        f"**{tournament.name}** · {tournament.game}",
        tournament.description or "Melde dein Team an und kämpfe im Bracket!",
        f"Status: **{TOURNAMENT_STATUS_LABELS[tournament.status]}** · Teams: **{registered}/{tournament.max_teams}**",
    )

    fields: list[tuple[str, str, bool]] = [
        ("Teams", teams_text, False),
        ("Nächste Schritte", next_steps, False),
    ]
    if maps:
        fields.insert(1, ("Map-Pool", ", ".join(maps[:15]), False))

    return info_embed(
        headline,
        description,
        fields=fields,
        footer_prefix=f"Turnier #{tournament.id}",
    )


# Backwards-compatible alias
async def build_tournament_admin_embed(
    cog: TournamentCog,
    guild: discord.Guild,
    tournament_id: int,
) -> discord.Embed:
    return await build_wizard_embed(cog, guild, tournament_id=tournament_id)


class TournamentChannelSelect(discord.ui.ChannelSelect):
    """Schritt 0: Turnier-Kanal setzen."""

    def __init__(self, cog: TournamentCog, *, row: int = 0) -> None:
        super().__init__(
            placeholder="Turnier-Kanal wählen…",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
            row=row,
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        selected = self.values[0]
        channel = selected if isinstance(selected, discord.TextChannel) else interaction.guild.get_channel(selected.id)
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                embed=error_embed("Ungültig", "Bitte einen Textkanal wählen."),
            )
            return
        error = await self.cog._save_tournament_channel(interaction.guild, channel)
        if error:
            await interaction.response.send_message(embed=error_embed("Kanal nicht nutzbar", error))
            return
        await interaction.response.defer()
        await refresh_wizard_panel(interaction, self.cog)


class CreateTournamentModal(discord.ui.Modal, title="Neues Turnier"):
    """Schritt 1: Name, Spiel und Beschreibung."""

    def __init__(self, cog: TournamentCog) -> None:
        super().__init__()
        self.cog = cog
        self.name_input = discord.ui.TextInput(
            label="Turniername",
            placeholder="z. B. Sommer-Cup 2026",
            max_length=100,
        )
        self.game_input = discord.ui.TextInput(
            label="Spiel",
            placeholder="z. B. CS2, Valorant, …",
            max_length=80,
        )
        self.description_input = discord.ui.TextInput(
            label="Beschreibung (optional)",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=500,
        )
        self.add_item(self.name_input)
        self.add_item(self.game_input)
        self.add_item(self.description_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not self.cog._is_admin(interaction.user):
            await interaction.response.send_message(
                embed=error_embed("Keine Berechtigung", "Nur Administratoren."),
                ephemeral=True,
            )
            return
        name = self.name_input.value.strip()
        game = self.game_input.value.strip()
        if not name or not game:
            await interaction.response.send_message(
                embed=error_embed("Ungültig", "Name und Spiel dürfen nicht leer sein."),
            )
            return
        view = MaxTeamsPickView(
            self.cog,
            name=name,
            game=game,
            description=self.description_input.value.strip(),
        )
        await interaction.response.send_message(
            embed=info_embed(
                "Team-Limit wählen",
                spaced_lines(f"**{name}** · {game}", "Wie viele Teams dürfen maximal starten?"),
            ),
            view=view,
        )


class MaxTeamsPickView(TournamentAdminView):
    """Schritt 1b: Max-Teams per Button."""

    def __init__(
        self,
        cog: TournamentCog,
        *,
        name: str,
        game: str,
        description: str,
    ) -> None:
        super().__init__(cog, timeout=120)
        self.name = name
        self.game = game
        self.description = description
        for count in (4, 8, 16, 32):
            button = discord.ui.Button(label=str(count), style=discord.ButtonStyle.primary)
            button.callback = self._make_callback(count)
            self.add_item(button)

    def _make_callback(self, max_teams: int):
        async def callback(interaction: discord.Interaction) -> None:
            if interaction.guild is None:
                return
            tournament = await self.cog.db.create_tournament(
                interaction.guild.id,
                self.name,
                self.game,
                max_teams,
                description=self.description,
            )
            await interaction.response.defer(ephemeral=True)
            await refresh_wizard_panel(
                interaction,
                self.cog,
                tournament_id=tournament.id,
            )
            await interaction.followup.send(
                embed=success_embed(
                    f"Turnier #{tournament.id} erstellt",
                    spaced_lines(
                        f"**{tournament.name}** ({tournament.game})",
                        f"Max. Teams: **{max_teams}** — Wizard wurde aktualisiert.",
                    ),
                ),
                ephemeral=True,
            )

        return callback


class AddMapModal(discord.ui.Modal, title="Map hinzufügen"):
    """Map zum Pool hinzufügen."""

    def __init__(self, cog: TournamentCog, tournament_id: int) -> None:
        super().__init__()
        self.cog = cog
        self.tournament_id = tournament_id
        self.map_input = discord.ui.TextInput(
            label="Map-Name",
            placeholder="z. B. Dust2",
            max_length=80,
        )
        self.add_item(self.map_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        from cogs.tournament import _normalize_map_name

        map_name = _normalize_map_name(self.map_input.value)
        if not map_name:
            await interaction.response.send_message(
                embed=error_embed("Ungültig", "Map-Name darf nicht leer sein."),
            )
            return
        added = await self.cog.db.add_tournament_map(self.tournament_id, map_name)
        if not added:
            await interaction.response.send_message(
                embed=error_embed("Bereits vorhanden", f"**{map_name}** ist schon im Pool."),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        await refresh_wizard_panel(interaction, self.cog, tournament_id=self.tournament_id)
        await interaction.followup.send(
            embed=success_embed("Map hinzugefügt", f"**{map_name}** ist im Pool."),
            ephemeral=True,
        )


class CreateTeamModal(discord.ui.Modal, title="Team erstellen"):
    """Teamname — Captain per UserSelect."""

    def __init__(self, cog: TournamentCog, tournament_id: int) -> None:
        super().__init__()
        self.cog = cog
        self.tournament_id = tournament_id
        self.name_input = discord.ui.TextInput(
            label="Teamname",
            placeholder="z. B. Night Owls",
            max_length=50,
        )
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        from cogs.tournament import _normalize_team_name

        name = _normalize_team_name(self.name_input.value)
        if not name:
            await interaction.response.send_message(
                embed=error_embed("Ungültig", "Teamname darf nicht leer sein."),
            )
            return
        view = CaptainPickView(self.cog, self.tournament_id, name)
        await interaction.response.send_message(
            embed=info_embed("Captain wählen", f"Wer soll Captain von **{name}** werden?"),
            view=view,
        )


class CaptainPickView(TournamentAdminView):
    """Captain per UserSelect."""

    def __init__(self, cog: TournamentCog, tournament_id: int, team_name: str) -> None:
        super().__init__(cog, timeout=120)
        self.tournament_id = tournament_id
        self.team_name = team_name
        picker = discord.ui.UserSelect(
            placeholder="Captain wählen…",
            min_values=1,
            max_values=1,
        )
        picker.callback = self._on_pick
        self.add_item(picker)

    async def _on_pick(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        users = interaction.data.get("resolved", {}).get("users", {}) if interaction.data else {}
        if not users:
            await interaction.response.send_message(embed=error_embed("Fehler", "Kein User ausgewählt."))
            return
        captain_id = int(next(iter(users)))
        error = await self.cog._admin_create_team(
            interaction.guild,
            self.tournament_id,
            self.team_name,
            captain_id,
        )
        if error:
            await interaction.response.send_message(embed=error_embed("Nicht möglich", error), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await refresh_wizard_panel(interaction, self.cog, tournament_id=self.tournament_id)
        await interaction.followup.send(
            embed=success_embed("Team erstellt", f"**{self.team_name}** · Captain <@{captain_id}>"),
            ephemeral=True,
        )


class MapRemoveSelect(discord.ui.Select):
    """Map aus dem Pool entfernen — direkt im Wizard."""

    def __init__(self, cog: TournamentCog, tournament_id: int, maps: list[str]) -> None:
        options = [
            discord.SelectOption(label=map_name[:100], value=map_name[:100])
            for map_name in maps[:25]
        ]
        super().__init__(placeholder="Map entfernen…", options=options, row=1)
        self.cog = cog
        self.tournament_id = tournament_id

    async def callback(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not self.cog._is_admin(interaction.user):
            await interaction.response.send_message(
                embed=error_embed("Keine Berechtigung", "Nur Administratoren."),
                ephemeral=True,
            )
            return
        map_name = self.values[0]
        if not await self.cog.db.remove_tournament_map(self.tournament_id, map_name):
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Map konnte nicht entfernt werden."),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        await refresh_wizard_panel(interaction, self.cog, tournament_id=self.tournament_id)
        await interaction.followup.send(
            embed=success_embed("Entfernt", f"**{map_name}** aus dem Pool entfernt."),
            ephemeral=True,
        )


async def build_wizard_view(
    cog: TournamentCog,
    guild: discord.Guild,
    *,
    tournament_id: int | None = None,
) -> TournamentWizardView:
    state = await compute_wizard_state(cog, guild, tournament_id=tournament_id)
    return TournamentWizardView(cog, state)


class TournamentWizardView(TournamentAdminView):
    """Haupt-Wizard: Buttons nur für den aktuellen Schritt."""

    def __init__(self, cog: TournamentCog, state: WizardState) -> None:
        super().__init__(cog, timeout=600)
        self.state = state
        self.tournament_id = state.tournament_id
        self._build_buttons()

    def _build_buttons(self) -> None:
        step = self.state.current_step
        tid = self.state.tournament_id

        if step == 0:
            self.add_item(TournamentChannelSelect(self.cog, row=0))
        elif step == 1:
            btn = discord.ui.Button(
                label="Turnier erstellen",
                style=discord.ButtonStyle.success,
                emoji="➕",
                row=0,
            )
            btn.callback = self._create_tournament
            self.add_item(btn)
        elif step == 2 and tid is not None:
            add_map = discord.ui.Button(label="Map hinzufügen", style=discord.ButtonStyle.success, emoji="🗺️", row=0)
            add_map.callback = self._add_map
            self.add_item(add_map)
            if self.state.maps:
                self.add_item(MapRemoveSelect(self.cog, tid, self.state.maps))
        elif step == 3 and tid is not None:
            create_team = discord.ui.Button(
                label="Admin-Team erstellen",
                style=discord.ButtonStyle.success,
                emoji="➕",
                row=0,
            )
            create_team.callback = self._create_admin_team
            self.add_item(create_team)
        elif step == 4 and tid is not None:
            close_btn = discord.ui.Button(
                label="Anmeldungen schließen",
                style=discord.ButtonStyle.danger,
                emoji="🔒",
                row=0,
                disabled=self.state.tournament_status == TournamentStatus.CLOSED,
            )
            close_btn.callback = self._close_registrations
            self.add_item(close_btn)
            announce_btn = discord.ui.Button(
                label="Ankündigung posten",
                style=discord.ButtonStyle.secondary,
                emoji="📢",
                row=0,
            )
            announce_btn.callback = self._announce
            self.add_item(announce_btn)
        elif step == 5 and tid is not None and not self.state.has_matches:
            bracket_btn = discord.ui.Button(
                label="Bracket starten",
                style=discord.ButtonStyle.success,
                emoji="🌳",
                row=0,
                disabled=not (
                    self.state.channel_ok
                    and self.state.tournament_status == TournamentStatus.CLOSED
                    and self.state.registered_count >= 2
                ),
            )
            bracket_btn.callback = self._start_bracket
            self.add_item(bracket_btn)

        refresh_btn = discord.ui.Button(label="Aktualisieren", style=discord.ButtonStyle.secondary, emoji="🔄", row=2)
        refresh_btn.callback = self._refresh
        self.add_item(refresh_btn)

    async def _create_tournament(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(CreateTournamentModal(self.cog))

    async def _add_map(self, interaction: discord.Interaction) -> None:
        if self.tournament_id is None:
            return
        await interaction.response.send_modal(AddMapModal(self.cog, self.tournament_id))

    async def _create_admin_team(self, interaction: discord.Interaction) -> None:
        if self.tournament_id is None:
            return
        tournament = await self.cog.db.get_tournament(self.tournament_id)
        if tournament is None or tournament.status != TournamentStatus.OPEN:
            await interaction.response.send_message(
                embed=error_embed("Geschlossen", "Teams nur bei offenem Turnier."),
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(CreateTeamModal(self.cog, self.tournament_id))

    async def _close_registrations(self, interaction: discord.Interaction) -> None:
        if self.tournament_id is None:
            return
        await interaction.response.defer()
        await self.cog.db.update_tournament_status(self.tournament_id, TournamentStatus.CLOSED)
        await refresh_wizard_panel(interaction, self.cog, tournament_id=self.tournament_id)

    async def _announce(self, interaction: discord.Interaction) -> None:
        if self.tournament_id is None:
            return
        await interaction.response.defer()
        error = await self.cog._admin_announce_tournament(interaction, self.tournament_id)
        if error:
            await interaction.followup.send(embed=error_embed("Nicht möglich", error))
            return
        await interaction.followup.send(
            embed=success_embed("Ankündigung", "Turnier im Turnier-Kanal gepostet."),
        )
        await refresh_wizard_panel(interaction, self.cog, tournament_id=self.tournament_id)

    async def _start_bracket(self, interaction: discord.Interaction) -> None:
        if self.tournament_id is None:
            return
        await interaction.response.defer()
        error, posted = await self.cog._admin_start_bracket(interaction, self.tournament_id)
        if error:
            await interaction.followup.send(embed=error_embed("Nicht möglich", error))
            return
        channel = self.state.channel
        channel_ref = channel.mention if channel else "Turnier-Kanal"
        await interaction.followup.send(
            embed=success_embed("Bracket", f"Runde 1: **{posted}** Match(es) in {channel_ref}."),
        )
        await refresh_wizard_panel(interaction, self.cog, tournament_id=self.tournament_id)

    async def _refresh(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        await interaction.response.defer()
        await refresh_wizard_panel(interaction, self.cog, tournament_id=self.tournament_id)


async def refresh_wizard_panel(
    interaction: discord.Interaction,
    cog: TournamentCog,
    *,
    tournament_id: int | None = None,
    message: discord.Message | None = None,
) -> None:
    """Aktualisiert Wizard-Embed und View."""
    if interaction.guild is None:
        return
    focus_id = tournament_id or await resolve_focus_tournament_id(cog, interaction.guild.id)
    embed = await build_wizard_embed(cog, interaction.guild, tournament_id=focus_id)
    view = await build_wizard_view(cog, interaction.guild, tournament_id=focus_id)

    target = message
    if target is None:
        target = await cog.fetch_wizard_panel_message(interaction.guild, interaction.channel)
    if target is None and interaction.message is not None:
        target = interaction.message

    try:
        if target is not None:
            await target.edit(embed=embed, view=view)
            if isinstance(interaction.channel, discord.abc.GuildChannel):
                cog.register_wizard_panel(interaction.guild.id, interaction.channel.id, target.id)
        elif interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.response.edit_message(embed=embed, view=view)
    except discord.HTTPException:
        pass


# Legacy aliases für bestehende Imports
TournamentAdminHubView = TournamentWizardView
TournamentManageView = TournamentWizardView
