"""
Turnier-System mit Slash-Commands und button-basiertem Match-Management.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from database.database import Database
from database.models import (
    TournamentMatchRecord,
    TournamentMatchStatus,
    TournamentRecord,
    TournamentStatus,
)
from utils.embeds import apply_brand_footer, error_embed, info_embed, success_embed
from utils.helpers import truncate_text
from utils.permissions import bot_can_use_channel, is_admin
from utils.tournament_bracket import (
    create_pairings,
    create_round_one_pairings,
    distribute_maps,
)

logger = logging.getLogger(__name__)

TOURNAMENT_STATUS_LABELS = {
    TournamentStatus.OPEN: "Offen",
    TournamentStatus.CLOSED: "Geschlossen",
    TournamentStatus.FINISHED: "Beendet",
}

MATCH_STATUS_LABELS = {
    TournamentMatchStatus.OPEN: "Offen",
    TournamentMatchStatus.PENDING_CONFIRMATION: "Gemeldet – Bestätigung ausstehend",
    TournamentMatchStatus.DISPUTED: "Einspruch",
    TournamentMatchStatus.FINISHED: "Abgeschlossen",
}


def _normalize_team_name(name: str) -> str:
    return name.strip()[:50]


def _normalize_map_name(name: str) -> str:
    return name.strip()[:80]


class TournamentCog(commands.Cog):
    """Turnier-Verwaltung mit Teams, Bracket und Match-Buttons."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db

    async def cog_load(self) -> None:
        """Registriert persistente Match-Views nach Bot-Neustart."""
        matches = await self.db.get_active_tournament_matches()
        for match in matches:
            self.bot.add_view(MatchView(self, match.id))

    def _is_admin(self, member: discord.Member) -> bool:
        return member.guild_permissions.administrator

    async def _get_tournament_channel(
        self,
        guild: discord.Guild,
    ) -> discord.TextChannel | None:
        settings = await self.db.get_guild_settings(guild.id)
        if not settings.tournament_channel_id:
            return None
        channel = guild.get_channel(settings.tournament_channel_id)
        return channel if isinstance(channel, discord.TextChannel) else None

    async def _require_tournament_channel(
        self,
        interaction: discord.Interaction,
    ) -> discord.TextChannel | None:
        if interaction.guild is None:
            return None
        channel = await self._get_tournament_channel(interaction.guild)
        if channel is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Kein Turnier-Kanal",
                    "Ein Admin muss zuerst `/turnier_kanal_setzen` ausführen.",
                ),
                ephemeral=True,
            )
            return None
        allowed, msg = bot_can_use_channel(
            channel,
            send_messages=True,
            embed_links=True,
            view_channel=True,
        )
        if not allowed:
            await interaction.response.send_message(
                embed=error_embed("Kanal nicht nutzbar", msg or "Keine Berechtigung."),
                ephemeral=True,
            )
            return None
        return channel

    async def _get_tournament_for_guild(
        self,
        interaction: discord.Interaction,
        tournament_id: int,
    ) -> TournamentRecord | None:
        tournament = await self.db.get_tournament(tournament_id)
        if tournament is None or interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed("Nicht gefunden", f"Turnier #{tournament_id} existiert nicht."),
                ephemeral=True,
            )
            return None
        if tournament.guild_id != interaction.guild.id:
            await interaction.response.send_message(
                embed=error_embed(
                    "Nicht gefunden",
                    f"Turnier #{tournament_id} gehört nicht zu diesem Server.",
                ),
                ephemeral=True,
            )
            return None
        return tournament

    async def _team_name(self, guild: discord.Guild, team_id: int | None) -> str:
        if team_id is None:
            return "Freilos"
        team = await self.db.get_tournament_team(team_id)
        return team.name if team else f"Team #{team_id}"

    def _build_match_embed(
        self,
        match: TournamentMatchRecord,
        guild: discord.Guild,
        *,
        team1_name: str | None = None,
        team2_name: str | None = None,
        extra_note: str = "",
    ) -> discord.Embed:
        """Erstellt das Match-Embed."""
        status_text = MATCH_STATUS_LABELS.get(match.status, match.status.value)
        t1 = team1_name or "—"
        t2 = team2_name or "Freilos"
        description = f"**{t1}** vs **{t2}**"
        if extra_note:
            description += f"\n\n{extra_note}"
        if match.status == TournamentMatchStatus.FINISHED and match.winner_id:
            description += f"\n\n🏆 Sieger: **{t1 if match.winner_id == match.team1_id else t2}**"

        embed = info_embed(
            f"Match #{match.id} – Runde {match.round}",
            description,
            fields=[
                ("Map", match.map_name or "—", True),
                ("Status", status_text, True),
                ("Turnier", f"#{match.tournament_id}", True),
            ],
        )
        apply_brand_footer(embed, prefix=f"Match #{match.id}")
        return embed

    async def _refresh_match_message(
        self,
        match: TournamentMatchRecord,
        guild: discord.Guild,
        *,
        extra_note: str = "",
    ) -> None:
        """Aktualisiert die Match-Nachricht im Turnier-Kanal."""
        if not match.message_id:
            return
        channel = await self._get_tournament_channel(guild)
        if channel is None:
            return
        try:
            message = await channel.fetch_message(match.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return
        t1 = await self._team_name(guild, match.team1_id)
        t2 = await self._team_name(guild, match.team2_id)
        embed = self._build_match_embed(
            match,
            guild,
            team1_name=t1,
            team2_name=t2,
            extra_note=extra_note,
        )
        view = None if match.status == TournamentMatchStatus.FINISHED else MatchView(self, match.id)
        await message.edit(embed=embed, view=view)

    async def _post_match(
        self,
        match: TournamentMatchRecord,
        guild: discord.Guild,
        channel: discord.TextChannel,
        *,
        extra_note: str = "",
    ) -> TournamentMatchRecord:
        """Postet ein Match-Embed im Turnier-Kanal."""
        t1 = await self._team_name(guild, match.team1_id)
        t2 = await self._team_name(guild, match.team2_id)
        embed = self._build_match_embed(
            match,
            guild,
            team1_name=t1,
            team2_name=t2,
            extra_note=extra_note,
        )
        view = None if match.status == TournamentMatchStatus.FINISHED else MatchView(self, match.id)
        message = await channel.send(embed=embed, view=view)
        updated = await self.db.update_tournament_match(match.id, message_id=message.id)
        return updated or match

    async def _check_round_complete(self, tournament_id: int, guild: discord.Guild) -> None:
        """Generiert die nächste Runde oder krönt den Sieger."""
        max_round = await self.db.get_max_round(tournament_id)
        if max_round == 0:
            return
        round_matches = await self.db.get_tournament_matches(tournament_id, round_num=max_round)
        if not all(m.status == TournamentMatchStatus.FINISHED for m in round_matches):
            return

        winners = [m.winner_id for m in round_matches if m.winner_id is not None]
        if len(winners) <= 1:
            if len(winners) == 1:
                tournament = await self.db.get_tournament(tournament_id)
                team = await self.db.get_tournament_team(winners[0])
                channel = await self._get_tournament_channel(guild)
                await self.db.update_tournament_status(tournament_id, TournamentStatus.FINISHED)
                if channel and team and tournament:
                    embed = success_embed(
                        f"🏆 Turniersieger: {team.name}",
                        f"**{tournament.name}** ({tournament.game}) ist beendet!\n"
                        f"Glückwunsch an **{team.name}**!",
                    )
                    apply_brand_footer(embed, prefix=f"Turnier #{tournament_id}")
                    await channel.send(embed=embed)
            return

        maps = await self.db.get_tournament_maps(tournament_id)
        pairings = create_pairings(winners)
        map_list = distribute_maps(maps, len(pairings))
        channel = await self._get_tournament_channel(guild)
        if channel is None:
            return

        for index, (team1_id, team2_id) in enumerate(pairings):
            map_name = map_list[index] if index < len(map_list) else ""
            if team2_id is None:
                match = await self.db.create_tournament_match(
                    tournament_id,
                    max_round + 1,
                    team1_id,
                    None,
                    map_name=map_name,
                    status=TournamentMatchStatus.FINISHED,
                    winner_id=team1_id,
                )
                t1 = await self._team_name(guild, team1_id)
                embed = self._build_match_embed(
                    match,
                    guild,
                    team1_name=t1,
                    team2_name="Freilos",
                    extra_note="Freilos – automatisch weiter.",
                )
                message = await channel.send(embed=embed)
                await self.db.update_tournament_match(match.id, message_id=message.id)
            else:
                match = await self.db.create_tournament_match(
                    tournament_id,
                    max_round + 1,
                    team1_id,
                    team2_id,
                    map_name=map_name,
                )
                await self._post_match(match, guild, channel)

        await self._check_round_complete(tournament_id, guild)

    async def handle_report_win(
        self,
        interaction: discord.Interaction,
        match_id: int,
        reporting_team_id: int,
    ) -> None:
        """Team meldet Sieg."""
        match = await self.db.get_tournament_match(match_id)
        if match is None or interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Match nicht gefunden."),
                ephemeral=True,
            )
            return

        if match.status != TournamentMatchStatus.OPEN:
            await interaction.response.send_message(
                embed=error_embed("Nicht möglich", "Dieses Match ist nicht mehr offen."),
                ephemeral=True,
            )
            return

        if not await self.db.is_team_member(reporting_team_id, interaction.user.id):
            await interaction.response.send_message(
                embed=error_embed("Keine Berechtigung", "Du bist kein Mitglied dieses Teams."),
                ephemeral=True,
            )
            return

        team = await self.db.get_tournament_team(reporting_team_id)
        opponent_id = match.team2_id if reporting_team_id == match.team1_id else match.team1_id
        opponent = await self._team_name(interaction.guild, opponent_id)
        updated = await self.db.update_tournament_match(
            match_id,
            status=TournamentMatchStatus.PENDING_CONFIRMATION,
            reported_by_team_id=reporting_team_id,
        )
        assert updated is not None
        note = (
            f"**{team.name if team else 'Team'}** hat einen Sieg gemeldet.\n"
            f"**{opponent}** muss bestätigen oder Einspruch erheben."
        )
        await self._refresh_match_message(updated, interaction.guild, extra_note=note)
        await interaction.response.send_message(
            embed=success_embed("Sieg gemeldet", "Der Gegner muss bestätigen oder Einspruch erheben."),
            ephemeral=True,
        )

    async def handle_confirm(
        self,
        interaction: discord.Interaction,
        match_id: int,
    ) -> None:
        """Gegner bestätigt Siegmeldung."""
        match = await self.db.get_tournament_match(match_id)
        if match is None or interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Match nicht gefunden."),
                ephemeral=True,
            )
            return

        if match.status != TournamentMatchStatus.PENDING_CONFIRMATION:
            await interaction.response.send_message(
                embed=error_embed("Nicht möglich", "Es liegt keine offene Meldung vor."),
                ephemeral=True,
            )
            return

        reported = match.reported_by_team_id
        if reported is None:
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Keine Meldung vorhanden."),
                ephemeral=True,
            )
            return

        opponent_id = match.team2_id if reported == match.team1_id else match.team1_id
        if opponent_id is None or not await self.db.is_team_member(opponent_id, interaction.user.id):
            await interaction.response.send_message(
                embed=error_embed("Keine Berechtigung", "Nur das gegnerische Team kann bestätigen."),
                ephemeral=True,
            )
            return

        winner_id = reported
        updated = await self.db.update_tournament_match(
            match_id,
            status=TournamentMatchStatus.FINISHED,
            winner_id=winner_id,
            reported_by_team_id=None,
        )
        assert updated is not None
        await self._refresh_match_message(updated, interaction.guild)
        await interaction.response.send_message(
            embed=success_embed("Bestätigt", "Match abgeschlossen."),
            ephemeral=True,
        )
        await self._check_round_complete(match.tournament_id, interaction.guild)

    async def handle_dispute(
        self,
        interaction: discord.Interaction,
        match_id: int,
    ) -> None:
        """Gegner erhebt Einspruch."""
        match = await self.db.get_tournament_match(match_id)
        if match is None or interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Match nicht gefunden."),
                ephemeral=True,
            )
            return

        if match.status != TournamentMatchStatus.PENDING_CONFIRMATION:
            await interaction.response.send_message(
                embed=error_embed("Nicht möglich", "Es liegt keine offene Meldung vor."),
                ephemeral=True,
            )
            return

        reported = match.reported_by_team_id
        if reported is None:
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Keine Meldung vorhanden."),
                ephemeral=True,
            )
            return

        opponent_id = match.team2_id if reported == match.team1_id else match.team1_id
        if opponent_id is None or not await self.db.is_team_member(opponent_id, interaction.user.id):
            await interaction.response.send_message(
                embed=error_embed(
                    "Keine Berechtigung",
                    "Nur das gegnerische Team kann Einspruch erheben.",
                ),
                ephemeral=True,
            )
            return

        updated = await self.db.update_tournament_match(
            match_id,
            status=TournamentMatchStatus.DISPUTED,
        )
        assert updated is not None
        await self._refresh_match_message(
            updated,
            interaction.guild,
            extra_note="⚠️ Einspruch – ein Admin muss entscheiden.",
        )
        await interaction.response.send_message(
            embed=success_embed("Einspruch", "Ein Admin muss über den Admin-Button entscheiden."),
            ephemeral=True,
        )

    async def handle_admin_decision(
        self,
        interaction: discord.Interaction,
        match_id: int,
        decision: str,
    ) -> None:
        """Admin-Entscheidung nach Einspruch oder manuell."""
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return
        if not self._is_admin(interaction.user):
            await interaction.response.send_message(
                embed=error_embed("Keine Berechtigung", "Nur Administratoren."),
                ephemeral=True,
            )
            return

        match = await self.db.get_tournament_match(match_id)
        if match is None:
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Match nicht gefunden."),
                ephemeral=True,
            )
            return

        if decision == "rematch":
            updated = await self.db.update_tournament_match(
                match_id,
                status=TournamentMatchStatus.OPEN,
                winner_id=None,
                reported_by_team_id=None,
            )
            assert updated is not None
            await self._refresh_match_message(updated, interaction.guild, extra_note="Match wird wiederholt.")
            await interaction.response.send_message(
                embed=success_embed("Wiederholung", "Match zurückgesetzt."),
                ephemeral=True,
            )
            return

        if decision == "team_a":
            winner_id = match.team1_id
        elif decision == "team_b":
            winner_id = match.team2_id
        else:
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Ungültige Entscheidung."),
                ephemeral=True,
            )
            return

        if winner_id is None:
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Kein gültiges Team für diese Entscheidung."),
                ephemeral=True,
            )
            return

        updated = await self.db.update_tournament_match(
            match_id,
            status=TournamentMatchStatus.FINISHED,
            winner_id=winner_id,
            reported_by_team_id=None,
        )
        assert updated is not None
        await self._refresh_match_message(updated, interaction.guild)
        await interaction.response.send_message(
            embed=success_embed("Entscheidung", "Match abgeschlossen."),
            ephemeral=True,
        )
        await self._check_round_complete(match.tournament_id, interaction.guild)

    async def handle_map_change(
        self,
        interaction: discord.Interaction,
        match_id: int,
        new_map: str,
    ) -> None:
        """Admin ändert die Map eines Matches."""
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return
        if not self._is_admin(interaction.user):
            await interaction.response.send_message(
                embed=error_embed("Keine Berechtigung", "Nur Administratoren."),
                ephemeral=True,
            )
            return

        match = await self.db.get_tournament_match(match_id)
        if match is None:
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Match nicht gefunden."),
                ephemeral=True,
            )
            return

        map_name = _normalize_map_name(new_map)
        if not map_name:
            await interaction.response.send_message(
                embed=error_embed("Ungültig", "Map-Name darf nicht leer sein."),
                ephemeral=True,
            )
            return

        updated = await self.db.update_tournament_match(match_id, map=map_name)
        assert updated is not None
        await self._refresh_match_message(updated, interaction.guild)
        await interaction.response.send_message(
            embed=success_embed("Map geändert", f"Neue Map: **{map_name}**"),
            ephemeral=True,
        )

    # ── Slash-Commands ──────────────────────────────────────────────

    @app_commands.command(name="turnier_erstellen", description="Erstellt ein neues Turnier (Admin)")
    @app_commands.describe(
        name="Name des Turniers",
        spiel="Spielname",
        max_teams="Maximale Team-Anzahl",
        beschreibung="Optionale Beschreibung",
    )
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    @app_commands.guild_only()
    async def turnier_erstellen(
        self,
        interaction: discord.Interaction,
        name: str,
        spiel: str,
        max_teams: app_commands.Range[int, 2, 64],
        beschreibung: str = "",
    ) -> None:
        if interaction.guild is None:
            return
        name = name.strip()[:100]
        spiel = spiel.strip()[:80]
        if not name or not spiel:
            await interaction.response.send_message(
                embed=error_embed("Ungültig", "Name und Spiel dürfen nicht leer sein."),
                ephemeral=True,
            )
            return

        tournament = await self.db.create_tournament(
            interaction.guild.id,
            name,
            spiel,
            max_teams,
            description=beschreibung.strip()[:500],
        )
        embed = success_embed(
            f"Turnier #{tournament.id} erstellt",
            f"**{tournament.name}** ({tournament.game})\n"
            f"Max. Teams: **{tournament.max_teams}**\n"
            f"Status: **{TOURNAMENT_STATUS_LABELS[tournament.status]}**",
        )
        apply_brand_footer(embed, prefix=f"Turnier #{tournament.id}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    turnier_status_group = app_commands.Group(
        name="turnier_status",
        description="Turnier-Status verwalten",
    )

    @turnier_status_group.command(name="setzen", description="Setzt den Turnier-Status (Admin)")
    @app_commands.describe(
        turnier_id="ID des Turniers",
        status="Neuer Status",
    )
    @app_commands.choices(
        status=[
            app_commands.Choice(name="Offen", value="open"),
            app_commands.Choice(name="Geschlossen", value="closed"),
            app_commands.Choice(name="Beendet", value="finished"),
        ]
    )
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    @app_commands.guild_only()
    async def turnier_status_setzen(
        self,
        interaction: discord.Interaction,
        turnier_id: int,
        status: app_commands.Choice[str],
    ) -> None:
        tournament = await self._get_tournament_for_guild(interaction, turnier_id)
        if tournament is None:
            return
        new_status = TournamentStatus(status.value)
        await self.db.update_tournament_status(turnier_id, new_status)
        await interaction.response.send_message(
            embed=success_embed(
                "Status geändert",
                f"Turnier #{turnier_id} ist jetzt **{TOURNAMENT_STATUS_LABELS[new_status]}**.",
            ),
            ephemeral=True,
        )

    @app_commands.command(name="turnier_loeschen", description="Löscht ein Turnier (Admin, nur ohne Bracket)")
    @app_commands.describe(turnier_id="ID des Turniers")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    @app_commands.guild_only()
    async def turnier_loeschen(
        self,
        interaction: discord.Interaction,
        turnier_id: int,
    ) -> None:
        tournament = await self._get_tournament_for_guild(interaction, turnier_id)
        if tournament is None:
            return
        if await self.db.tournament_has_matches(turnier_id):
            await interaction.response.send_message(
                embed=error_embed(
                    "Nicht möglich",
                    "Turnier hat bereits Matches. Nutze `/turnier_abbrechen` oder warte bis zum Ende.",
                ),
                ephemeral=True,
            )
            return
        await self.db.delete_tournament(turnier_id)
        await interaction.response.send_message(
            embed=success_embed("Gelöscht", f"Turnier #{turnier_id} wurde entfernt."),
            ephemeral=True,
        )

    @app_commands.command(name="turnier_liste", description="Listet alle Turniere auf dem Server")
    @app_commands.guild_only()
    async def turnier_liste(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        tournaments = await self.db.get_tournaments_for_guild(interaction.guild.id)
        if not tournaments:
            await interaction.response.send_message(
                embed=info_embed("Turniere", "Keine Turniere vorhanden."),
                ephemeral=True,
            )
            return
        lines = [
            f"**#{t.id}** {t.name} ({t.game}) – {TOURNAMENT_STATUS_LABELS[t.status]}"
            for t in tournaments[:25]
        ]
        await interaction.response.send_message(
            embed=info_embed("Turniere", "\n".join(lines)),
            ephemeral=True,
        )

    @app_commands.command(name="turnier_info", description="Zeigt Details zu einem Turnier")
    @app_commands.describe(turnier_id="ID des Turniers")
    @app_commands.guild_only()
    async def turnier_info(
        self,
        interaction: discord.Interaction,
        turnier_id: int,
    ) -> None:
        tournament = await self._get_tournament_for_guild(interaction, turnier_id)
        if tournament is None:
            return
        teams = await self.db.get_tournament_teams(turnier_id)
        registered = sum(1 for t in teams if t.registered)
        maps = await self.db.get_tournament_maps(turnier_id)
        fields = [
            ("Spiel", tournament.game, True),
            ("Status", TOURNAMENT_STATUS_LABELS[tournament.status], True),
            ("Teams", f"{registered}/{tournament.max_teams} angemeldet", True),
            ("Maps", ", ".join(maps) if maps else "—", False),
        ]
        if tournament.description:
            fields.append(("Beschreibung", truncate_text(tournament.description, 900), False))
        team_lines = [
            f"{'✅' if t.registered else '⏳'} **{t.name}** (Captain: <@{t.captain_id}>)"
            for t in teams[:20]
        ]
        if team_lines:
            fields.append(("Teamliste", "\n".join(team_lines), False))
        embed = info_embed(f"Turnier #{tournament.id}: {tournament.name}", fields=fields)
        apply_brand_footer(embed, prefix=f"Turnier #{tournament.id}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="turnier_maps_hinzufuegen", description="Fügt Maps zum Pool hinzu (Admin)")
    @app_commands.describe(turnier_id="ID des Turniers", map1="Erste Map", map2="Zweite Map (optional)")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    @app_commands.guild_only()
    async def turnier_maps_hinzufuegen(
        self,
        interaction: discord.Interaction,
        turnier_id: int,
        map1: str,
        map2: str | None = None,
        map3: str | None = None,
        map4: str | None = None,
        map5: str | None = None,
    ) -> None:
        tournament = await self._get_tournament_for_guild(interaction, turnier_id)
        if tournament is None:
            return
        raw_maps = [map1, map2, map3, map4, map5]
        added: list[str] = []
        skipped: list[str] = []
        for raw in raw_maps:
            if raw is None:
                continue
            map_name = _normalize_map_name(raw)
            if not map_name:
                continue
            if await self.db.add_tournament_map(turnier_id, map_name):
                added.append(map_name)
            else:
                skipped.append(map_name)
        if not added:
            await interaction.response.send_message(
                embed=error_embed(
                    "Keine Maps",
                    "Keine neuen Maps hinzugefügt (leer oder bereits vorhanden).",
                ),
                ephemeral=True,
            )
            return
        msg = f"Hinzugefügt: **{', '.join(added)}**"
        if skipped:
            msg += f"\nBereits vorhanden: {', '.join(skipped)}"
        await interaction.response.send_message(embed=success_embed("Maps", msg), ephemeral=True)

    @app_commands.command(name="turnier_maps_entfernen", description="Entfernt eine Map aus dem Pool (Admin)")
    @app_commands.describe(turnier_id="ID des Turniers", mapname="Name der Map")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    @app_commands.guild_only()
    async def turnier_maps_entfernen(
        self,
        interaction: discord.Interaction,
        turnier_id: int,
        mapname: str,
    ) -> None:
        tournament = await self._get_tournament_for_guild(interaction, turnier_id)
        if tournament is None:
            return
        name = _normalize_map_name(mapname)
        if not await self.db.remove_tournament_map(turnier_id, name):
            await interaction.response.send_message(
                embed=error_embed("Nicht gefunden", f"Map **{name}** ist nicht im Pool."),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=success_embed("Entfernt", f"Map **{name}** wurde entfernt."),
            ephemeral=True,
        )

    @app_commands.command(name="turnier_maps_anzeigen", description="Zeigt den Map-Pool eines Turniers")
    @app_commands.describe(turnier_id="ID des Turniers")
    @app_commands.guild_only()
    async def turnier_maps_anzeigen(
        self,
        interaction: discord.Interaction,
        turnier_id: int,
    ) -> None:
        tournament = await self._get_tournament_for_guild(interaction, turnier_id)
        if tournament is None:
            return
        maps = await self.db.get_tournament_maps(turnier_id)
        text = "\n".join(f"• {m}" for m in maps) if maps else "Keine Maps im Pool."
        await interaction.response.send_message(
            embed=info_embed(f"Map-Pool – Turnier #{turnier_id}", text),
            ephemeral=True,
        )

    @app_commands.command(
        name="turnier_maps_neu_verteilen",
        description="Verteilt Maps neu auf offene Matches (Admin)",
    )
    @app_commands.describe(turnier_id="ID des Turniers")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    @app_commands.guild_only()
    async def turnier_maps_neu_verteilen(
        self,
        interaction: discord.Interaction,
        turnier_id: int,
    ) -> None:
        tournament = await self._get_tournament_for_guild(interaction, turnier_id)
        if tournament is None or interaction.guild is None:
            return
        maps = await self.db.get_tournament_maps(turnier_id)
        if not maps:
            await interaction.response.send_message(
                embed=error_embed("Keine Maps", "Zuerst Maps zum Pool hinzufügen."),
                ephemeral=True,
            )
            return
        count = await self.db.redistribute_match_maps(turnier_id, maps)
        if count == 0:
            await interaction.response.send_message(
                embed=error_embed("Keine Matches", "Keine offenen Matches zum Aktualisieren."),
                ephemeral=True,
            )
            return
        matches = await self.db.get_tournament_matches(turnier_id)
        for match in matches:
            if match.status != TournamentMatchStatus.FINISHED:
                await self._refresh_match_message(match, interaction.guild)
        await interaction.response.send_message(
            embed=success_embed("Verteilt", f"Maps auf **{count}** Match(es) neu verteilt."),
            ephemeral=True,
        )

    @app_commands.command(name="turnier_team_erstellen", description="Gründet ein Team (Captain)")
    @app_commands.describe(turnier_id="ID des Turniers", teamname="Name des Teams")
    @app_commands.guild_only()
    async def turnier_team_erstellen(
        self,
        interaction: discord.Interaction,
        turnier_id: int,
        teamname: str,
    ) -> None:
        tournament = await self._get_tournament_for_guild(interaction, turnier_id)
        if tournament is None or interaction.user is None:
            return
        if tournament.status != TournamentStatus.OPEN:
            await interaction.response.send_message(
                embed=error_embed("Geschlossen", "Das Turnier ist nicht mehr offen für neue Teams."),
                ephemeral=True,
            )
            return
        name = _normalize_team_name(teamname)
        if not name:
            await interaction.response.send_message(
                embed=error_embed("Ungültig", "Teamname darf nicht leer sein."),
                ephemeral=True,
            )
            return
        if await self.db.user_in_tournament_team(turnier_id, interaction.user.id):
            await interaction.response.send_message(
                embed=error_embed("Bereits im Team", "Du bist bereits in einem Team dieses Turniers."),
                ephemeral=True,
            )
            return
        existing = await self.db.get_tournament_team_by_name(turnier_id, name)
        if existing:
            await interaction.response.send_message(
                embed=error_embed("Name vergeben", f"Team **{name}** existiert bereits."),
                ephemeral=True,
            )
            return
        team = await self.db.create_tournament_team(turnier_id, name, interaction.user.id)
        await interaction.response.send_message(
            embed=success_embed(
                "Team erstellt",
                f"**{team.name}** (#{team.id}) – du bist Captain.\n"
                "Melde das Team mit `/turnier_anmelden` an.",
            ),
            ephemeral=True,
        )

    @app_commands.command(name="turnier_team_beitreten", description="Tritt einem Team bei")
    @app_commands.describe(turnier_id="ID des Turniers", teamname="Name des Teams")
    @app_commands.guild_only()
    async def turnier_team_beitreten(
        self,
        interaction: discord.Interaction,
        turnier_id: int,
        teamname: str,
    ) -> None:
        tournament = await self._get_tournament_for_guild(interaction, turnier_id)
        if tournament is None or interaction.user is None:
            return
        if tournament.status != TournamentStatus.OPEN:
            await interaction.response.send_message(
                embed=error_embed("Geschlossen", "Das Turnier ist nicht mehr offen."),
                ephemeral=True,
            )
            return
        team = await self.db.get_tournament_team_by_name(turnier_id, _normalize_team_name(teamname))
        if team is None:
            await interaction.response.send_message(
                embed=error_embed("Nicht gefunden", f"Team **{teamname}** existiert nicht."),
                ephemeral=True,
            )
            return
        if await self.db.user_in_tournament_team(turnier_id, interaction.user.id):
            await interaction.response.send_message(
                embed=error_embed("Bereits im Team", "Du bist bereits in einem Team dieses Turniers."),
                ephemeral=True,
            )
            return
        if not await self.db.add_team_member(team.id, interaction.user.id):
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Beitritt nicht möglich."),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=success_embed("Beigetreten", f"Du bist jetzt Mitglied von **{team.name}**."),
            ephemeral=True,
        )

    @app_commands.command(name="turnier_anmelden", description="Meldet dein Team offiziell an (Captain)")
    @app_commands.describe(turnier_id="ID des Turniers", teamname="Name deines Teams")
    @app_commands.guild_only()
    async def turnier_anmelden(
        self,
        interaction: discord.Interaction,
        turnier_id: int,
        teamname: str,
    ) -> None:
        tournament = await self._get_tournament_for_guild(interaction, turnier_id)
        if tournament is None or interaction.user is None:
            return
        if tournament.status != TournamentStatus.OPEN:
            await interaction.response.send_message(
                embed=error_embed("Geschlossen", "Anmeldungen sind nur bei offenem Turnier möglich."),
                ephemeral=True,
            )
            return
        team = await self.db.get_tournament_team_by_name(turnier_id, _normalize_team_name(teamname))
        if team is None:
            await interaction.response.send_message(
                embed=error_embed("Nicht gefunden", f"Team **{teamname}** existiert nicht."),
                ephemeral=True,
            )
            return
        if team.captain_id != interaction.user.id:
            await interaction.response.send_message(
                embed=error_embed("Kein Captain", "Nur der Captain kann das Team anmelden."),
                ephemeral=True,
            )
            return
        if team.registered:
            await interaction.response.send_message(
                embed=error_embed("Bereits angemeldet", f"**{team.name}** ist bereits angemeldet."),
                ephemeral=True,
            )
            return
        count = await self.db.count_registered_teams(turnier_id)
        if count >= tournament.max_teams:
            await interaction.response.send_message(
                embed=error_embed("Voll", f"Maximale Team-Anzahl ({tournament.max_teams}) erreicht."),
                ephemeral=True,
            )
            return
        await self.db.register_tournament_team(team.id)
        await interaction.response.send_message(
            embed=success_embed("Angemeldet", f"**{team.name}** ist offiziell angemeldet."),
            ephemeral=True,
        )

    @app_commands.command(name="turnier_team_zuweisen", description="Fügt einen User zu einem Team hinzu (Admin)")
    @app_commands.describe(turnier_id="ID des Turniers", teamname="Teamname", user="Mitglied")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    @app_commands.guild_only()
    async def turnier_team_zuweisen(
        self,
        interaction: discord.Interaction,
        turnier_id: int,
        teamname: str,
        user: discord.Member,
    ) -> None:
        tournament = await self._get_tournament_for_guild(interaction, turnier_id)
        if tournament is None:
            return
        if tournament.status != TournamentStatus.OPEN:
            await interaction.response.send_message(
                embed=error_embed("Geschlossen", "Team-Änderungen nur bei offenem Turnier."),
                ephemeral=True,
            )
            return
        team = await self.db.get_tournament_team_by_name(turnier_id, _normalize_team_name(teamname))
        if team is None:
            await interaction.response.send_message(
                embed=error_embed("Nicht gefunden", f"Team **{teamname}** existiert nicht."),
                ephemeral=True,
            )
            return
        if await self.db.user_in_tournament_team(turnier_id, user.id):
            await interaction.response.send_message(
                embed=error_embed("Bereits im Team", f"{user.mention} ist bereits in einem Team."),
                ephemeral=True,
            )
            return
        await self.db.add_team_member(team.id, user.id)
        await interaction.response.send_message(
            embed=success_embed("Zugewiesen", f"{user.mention} → **{team.name}**"),
            ephemeral=True,
        )

    @app_commands.command(name="turnier_team_entfernen", description="Entfernt einen User aus einem Team (Admin)")
    @app_commands.describe(turnier_id="ID des Turniers", teamname="Teamname", user="Mitglied")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    @app_commands.guild_only()
    async def turnier_team_entfernen(
        self,
        interaction: discord.Interaction,
        turnier_id: int,
        teamname: str,
        user: discord.Member,
    ) -> None:
        tournament = await self._get_tournament_for_guild(interaction, turnier_id)
        if tournament is None:
            return
        team = await self.db.get_tournament_team_by_name(turnier_id, _normalize_team_name(teamname))
        if team is None:
            await interaction.response.send_message(
                embed=error_embed("Nicht gefunden", f"Team **{teamname}** existiert nicht."),
                ephemeral=True,
            )
            return
        if team.captain_id == user.id:
            await interaction.response.send_message(
                embed=error_embed(
                    "Captain",
                    "Captain kann nicht entfernt werden – Team löschen oder Captain wechseln.",
                ),
                ephemeral=True,
            )
            return
        if not await self.db.remove_team_member(team.id, user.id):
            await interaction.response.send_message(
                embed=error_embed("Nicht im Team", f"{user.mention} ist nicht in **{team.name}**."),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=success_embed("Entfernt", f"{user.mention} aus **{team.name}** entfernt."),
            ephemeral=True,
        )

    @app_commands.command(name="turnier_baum_erstellen", description="Generiert Runde 1 und postet Matches (Admin)")
    @app_commands.describe(turnier_id="ID des Turniers")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    @app_commands.guild_only()
    async def turnier_baum_erstellen(
        self,
        interaction: discord.Interaction,
        turnier_id: int,
    ) -> None:
        tournament = await self._get_tournament_for_guild(interaction, turnier_id)
        if tournament is None or interaction.guild is None:
            return
        if tournament.status != TournamentStatus.CLOSED:
            await interaction.response.send_message(
                embed=error_embed(
                    "Status",
                    "Turnier muss **geschlossen** sein. Nutze `/turnier_status setzen`.",
                ),
                ephemeral=True,
            )
            return
        if await self.db.tournament_has_matches(turnier_id):
            await interaction.response.send_message(
                embed=error_embed("Bereits gestartet", "Bracket existiert bereits."),
                ephemeral=True,
            )
            return
        teams = await self.db.get_registered_teams(turnier_id)
        if len(teams) < 2:
            await interaction.response.send_message(
                embed=error_embed("Zu wenig Teams", "Mindestens 2 angemeldete Teams nötig."),
                ephemeral=True,
            )
            return
        channel = await self._require_tournament_channel(interaction)
        if channel is None:
            return

        await interaction.response.defer(ephemeral=True)
        team_ids = [t.id for t in teams]
        pairings = await create_round_one_pairings(team_ids)
        maps = await self.db.get_tournament_maps(turnier_id)
        map_list = distribute_maps(maps, len(pairings))

        posted = 0
        for index, (team1_id, team2_id) in enumerate(pairings):
            map_name = map_list[index] if index < len(map_list) else ""
            if team2_id is None:
                match = await self.db.create_tournament_match(
                    turnier_id,
                    1,
                    team1_id,
                    None,
                    map_name=map_name,
                    status=TournamentMatchStatus.FINISHED,
                    winner_id=team1_id,
                )
                t1 = await self._team_name(interaction.guild, team1_id)
                embed = self._build_match_embed(
                    match,
                    interaction.guild,
                    team1_name=t1,
                    team2_name="Freilos",
                    extra_note="Freilos – automatisch weiter.",
                )
                message = await channel.send(embed=embed)
                await self.db.update_tournament_match(match.id, message_id=message.id)
            else:
                match = await self.db.create_tournament_match(
                    turnier_id,
                    1,
                    team1_id,
                    team2_id,
                    map_name=map_name,
                )
                await self._post_match(match, interaction.guild, channel)
                posted += 1

        await self._check_round_complete(turnier_id, interaction.guild)
        await interaction.followup.send(
            embed=success_embed(
                "Bracket erstellt",
                f"Runde 1: **{posted}** Match(es) gepostet in {channel.mention}.",
            ),
            ephemeral=True,
        )

    @app_commands.command(name="turnier_baum_anzeigen", description="Zeigt alle Matches eines Turniers")
    @app_commands.describe(turnier_id="ID des Turniers")
    @app_commands.guild_only()
    async def turnier_baum_anzeigen(
        self,
        interaction: discord.Interaction,
        turnier_id: int,
    ) -> None:
        tournament = await self._get_tournament_for_guild(interaction, turnier_id)
        if tournament is None or interaction.guild is None:
            return
        matches = await self.db.get_tournament_matches(turnier_id)
        if not matches:
            await interaction.response.send_message(
                embed=info_embed("Bracket", "Noch keine Matches vorhanden."),
                ephemeral=True,
            )
            return
        lines: list[str] = []
        current_round = 0
        for match in matches:
            if match.round != current_round:
                current_round = match.round
                lines.append(f"\n**Runde {current_round}**")
            t1 = await self._team_name(interaction.guild, match.team1_id)
            t2 = await self._team_name(interaction.guild, match.team2_id)
            status = MATCH_STATUS_LABELS.get(match.status, match.status.value)
            lines.append(f"`#{match.id}` {t1} vs {t2} | {match.map_name or '—'} | {status}")
        await interaction.response.send_message(
            embed=info_embed(
                f"Bracket – Turnier #{turnier_id}",
                truncate_text("\n".join(lines), 3900),
            ),
            ephemeral=True,
        )

    @app_commands.command(name="turnier_abbrechen", description="Setzt Turnier zurück und löscht Matches (Admin)")
    @app_commands.describe(turnier_id="ID des Turniers")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    @app_commands.guild_only()
    async def turnier_abbrechen(
        self,
        interaction: discord.Interaction,
        turnier_id: int,
    ) -> None:
        tournament = await self._get_tournament_for_guild(interaction, turnier_id)
        if tournament is None or interaction.guild is None:
            return
        channel = await self._get_tournament_channel(interaction.guild)
        message_ids = await self.db.delete_tournament_matches(turnier_id)
        if channel:
            for msg_id in message_ids:
                try:
                    msg = await channel.fetch_message(msg_id)
                    await msg.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass
        await self.db.update_tournament_status(turnier_id, TournamentStatus.OPEN)
        await interaction.response.send_message(
            embed=success_embed(
                "Abgebrochen",
                f"Turnier #{turnier_id} zurückgesetzt (Status: offen, Matches gelöscht).",
            ),
            ephemeral=True,
        )

    @app_commands.command(name="turnier_kanal_setzen", description="Legt den Turnier-Kanal fest (Admin)")
    @app_commands.describe(channel="Kanal für Match-Nachrichten")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    @app_commands.guild_only()
    async def turnier_kanal_setzen(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ) -> None:
        if interaction.guild is None:
            return
        allowed, msg = bot_can_use_channel(
            channel,
            send_messages=True,
            embed_links=True,
            view_channel=True,
        )
        if not allowed:
            await interaction.response.send_message(
                embed=error_embed("Kanal nicht nutzbar", msg or "Keine Berechtigung."),
                ephemeral=True,
            )
            return
        await self.db.update_guild_settings(
            interaction.guild.id,
            tournament_channel_id=channel.id,
        )
        await interaction.response.send_message(
            embed=success_embed("Turnier-Kanal", f"Turnier-Nachrichten → {channel.mention}"),
            ephemeral=True,
        )

    @app_commands.command(name="turnier_match_info", description="Zeigt Details zu einem Match")
    @app_commands.describe(match_id="ID des Matches")
    @app_commands.guild_only()
    async def turnier_match_info(
        self,
        interaction: discord.Interaction,
        match_id: int,
    ) -> None:
        match = await self.db.get_tournament_match(match_id)
        if match is None or interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed("Nicht gefunden", f"Match #{match_id} existiert nicht."),
                ephemeral=True,
            )
            return
        tournament = await self.db.get_tournament(match.tournament_id)
        if tournament is None or tournament.guild_id != interaction.guild.id:
            await interaction.response.send_message(
                embed=error_embed(
                    "Nicht gefunden",
                    f"Match #{match_id} gehört nicht zu diesem Server.",
                ),
                ephemeral=True,
            )
            return
        t1 = await self._team_name(interaction.guild, match.team1_id)
        t2 = await self._team_name(interaction.guild, match.team2_id)
        winner = await self._team_name(interaction.guild, match.winner_id) if match.winner_id else "—"
        embed = info_embed(
            f"Match #{match.id}",
            fields=[
                ("Turnier", f"#{match.tournament_id} {tournament.name}", True),
                ("Runde", str(match.round), True),
                ("Status", MATCH_STATUS_LABELS.get(match.status, match.status.value), True),
                ("Team A", t1, True),
                ("Team B", t2, True),
                ("Map", match.map_name or "—", True),
                ("Sieger", winner, True),
            ],
        )
        apply_brand_footer(embed, prefix=f"Match #{match.id}")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class MatchView(discord.ui.View):
    """Persistente Buttons für Turnier-Matches."""

    def __init__(self, cog: TournamentCog, match_id: int) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.match_id = match_id
        self._add_buttons()

    def _add_buttons(self) -> None:
        mid = self.match_id
        report_a = discord.ui.Button(
            label="Team A meldet Sieg",
            style=discord.ButtonStyle.primary,
            emoji="🔵",
            custom_id=f"tournament:match:{mid}:report_a",
        )
        report_a.callback = self._report_a
        self.add_item(report_a)

        report_b = discord.ui.Button(
            label="Team B meldet Sieg",
            style=discord.ButtonStyle.danger,
            emoji="🔴",
            custom_id=f"tournament:match:{mid}:report_b",
        )
        report_b.callback = self._report_b
        self.add_item(report_b)

        confirm = discord.ui.Button(
            label="Bestätigen",
            style=discord.ButtonStyle.success,
            emoji="✅",
            custom_id=f"tournament:match:{mid}:confirm",
        )
        confirm.callback = self._confirm
        self.add_item(confirm)

        dispute = discord.ui.Button(
            label="Einspruch",
            style=discord.ButtonStyle.secondary,
            emoji="❌",
            custom_id=f"tournament:match:{mid}:dispute",
        )
        dispute.callback = self._dispute
        self.add_item(dispute)

        admin_decision = discord.ui.Button(
            label="Admin-Entscheidung",
            style=discord.ButtonStyle.secondary,
            emoji="⚖️",
            custom_id=f"tournament:match:{mid}:admin",
        )
        admin_decision.callback = self._admin_decision
        self.add_item(admin_decision)

        map_change = discord.ui.Button(
            label="Map ändern",
            style=discord.ButtonStyle.secondary,
            emoji="🗺️",
            custom_id=f"tournament:match:{mid}:map",
        )
        map_change.callback = self._map_change
        self.add_item(map_change)

    async def _get_match(self) -> TournamentMatchRecord | None:
        return await self.cog.db.get_tournament_match(self.match_id)

    async def _report_a(self, interaction: discord.Interaction) -> None:
        match = await self._get_match()
        if match is None or match.team1_id is None:
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Match nicht gefunden."),
                ephemeral=True,
            )
            return
        await self.cog.handle_report_win(interaction, self.match_id, match.team1_id)

    async def _report_b(self, interaction: discord.Interaction) -> None:
        match = await self._get_match()
        if match is None or match.team2_id is None:
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Kein Team B (Freilos)."),
                ephemeral=True,
            )
            return
        await self.cog.handle_report_win(interaction, self.match_id, match.team2_id)

    async def _confirm(self, interaction: discord.Interaction) -> None:
        await self.cog.handle_confirm(interaction, self.match_id)

    async def _dispute(self, interaction: discord.Interaction) -> None:
        await self.cog.handle_dispute(interaction, self.match_id)

    async def _admin_decision(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return
        if not self.cog._is_admin(interaction.user):
            await interaction.response.send_message(
                embed=error_embed("Keine Berechtigung", "Nur Administratoren."),
                ephemeral=True,
            )
            return
        view = AdminDecisionView(self.cog, self.match_id)
        await interaction.response.send_message(
            embed=info_embed("Admin-Entscheidung", "Wähle eine Option:"),
            view=view,
            ephemeral=True,
        )

    async def _map_change(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return
        if not self.cog._is_admin(interaction.user):
            await interaction.response.send_message(
                embed=error_embed("Keine Berechtigung", "Nur Administratoren."),
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(MapChangeModal(self.cog, self.match_id))


class AdminDecisionView(discord.ui.View):
    """Select-Menü für Admin-Entscheidungen."""

    def __init__(self, cog: TournamentCog, match_id: int) -> None:
        super().__init__(timeout=120)
        self.cog = cog
        self.match_id = match_id
        options = [
            discord.SelectOption(label="Team A gewinnt", value="team_a", emoji="🔵"),
            discord.SelectOption(label="Team B gewinnt", value="team_b", emoji="🔴"),
            discord.SelectOption(label="Match wiederholen", value="rematch", emoji="🔄"),
        ]
        select = discord.ui.Select(
            placeholder="Entscheidung wählen…",
            options=options,
            custom_id=f"tournament:admin:{match_id}",
        )
        select.callback = self._select
        self.add_item(select)

    async def _select(self, interaction: discord.Interaction) -> None:
        values = interaction.data.get("values", []) if interaction.data else []
        if not values:
            return
        await self.cog.handle_admin_decision(interaction, self.match_id, values[0])
        self.stop()


class MapChangeModal(discord.ui.Modal, title="Map ändern"):
    """Modal zur Eingabe einer neuen Map."""

    def __init__(self, cog: TournamentCog, match_id: int) -> None:
        super().__init__()
        self.cog = cog
        self.match_id = match_id
        self.map_input = discord.ui.TextInput(
            label="Neue Map",
            placeholder="z. B. Dust2",
            max_length=80,
        )
        self.add_item(self.map_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.handle_map_change(interaction, self.match_id, self.map_input.value)


async def setup(bot: commands.Bot) -> None:
    """Lädt den Turnier-Cog."""
    db: Database = bot.db  # type: ignore[attr-defined]
    await bot.add_cog(TournamentCog(bot, db))
