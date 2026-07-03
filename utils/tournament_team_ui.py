"""
Team-Interface für Turniere: Buttons für Mitglieder, Anmeldung und Status.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from database.models import TournamentStatus
from utils.embeds import apply_brand_footer, error_embed, info_embed, spaced_lines, success_embed

if TYPE_CHECKING:
    from cogs.tournament import TournamentCog


async def build_team_embed(cog: TournamentCog, guild: discord.Guild, team_id: int) -> discord.Embed:
    """Embed für das persistente Team-Interface."""
    from cogs.tournament import TOURNAMENT_STATUS_LABELS

    team = await cog.db.get_tournament_team(team_id)
    if team is None:
        return error_embed("Fehler", f"Team #{team_id} nicht gefunden.")

    tournament = await cog.db.get_tournament(team.tournament_id)
    if tournament is None:
        return error_embed("Fehler", "Turnier nicht gefunden.")

    members = await cog.db.get_team_members(team_id)
    member_text = ", ".join(f"<@{uid}>" for uid in members) or "—"
    registered = await cog.db.count_registered_teams(team.tournament_id)

    reg_status = "✅ Angemeldet" if team.registered else "⏳ Noch nicht angemeldet"
    next_steps = (
        "Captain: **Für Turnier anmelden** klicken, wenn das Team bereit ist."
        if not team.registered and tournament.status == TournamentStatus.OPEN
        else "Warte auf den Turnierstart durch die Admins."
        if team.registered
        else "Anmeldungen sind geschlossen."
    )

    fields: list[tuple[str, str, bool]] = [
        ("Turnier", f"#{tournament.id} **{tournament.name}** ({tournament.game})", False),
        (
            "Status",
            spaced_lines(
                f"Turnier: **{TOURNAMENT_STATUS_LABELS[tournament.status]}**",
                f"Team: **{reg_status}**",
                f"Plätze: **{registered}/{tournament.max_teams}**",
            ),
            False,
        ),
        ("Mitglieder", member_text, False),
        ("Nächste Schritte", next_steps, False),
    ]

    embed = info_embed(
        f"👥 Team **{team.name}**",
        spaced_lines(
            f"Captain: <@{team.captain_id}>",
            "Einladen: `/turnier_einladen @Spieler`",
        ),
        fields=fields,
    )
    apply_brand_footer(embed, prefix=f"Team #{team.id}")
    return embed


class TeamInterfaceView(discord.ui.View):
    """Persistente Buttons für Team-Verwaltung durch Spieler."""

    def __init__(self, cog: TournamentCog, team_id: int) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.team_id = team_id
        self._add_buttons()

    def _add_buttons(self) -> None:
        tid = self.team_id
        register = discord.ui.Button(
            label="Für Turnier anmelden",
            style=discord.ButtonStyle.success,
            emoji="✅",
            custom_id=f"tournament:team:{tid}:register",
            row=0,
        )
        register.callback = self._register
        self.add_item(register)

        remove = discord.ui.Button(
            label="Mitglied entfernen",
            style=discord.ButtonStyle.secondary,
            emoji="➖",
            custom_id=f"tournament:team:{tid}:remove",
            row=0,
        )
        remove.callback = self._remove_member
        self.add_item(remove)

    async def _get_team(self):
        return await self.cog.db.get_tournament_team(self.team_id)

    async def _refresh_message(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or interaction.message is None:
            return
        embed = await build_team_embed(self.cog, interaction.guild, self.team_id)
        await interaction.message.edit(embed=embed, view=self)

    async def _register(self, interaction: discord.Interaction) -> None:
        if interaction.user is None or interaction.guild is None:
            return
        team = await self._get_team()
        if team is None:
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Team nicht gefunden."),
                ephemeral=True,
            )
            return
        if team.captain_id != interaction.user.id:
            await interaction.response.send_message(
                embed=error_embed("Kein Captain", "Nur der Captain kann anmelden."),
                ephemeral=True,
            )
            return
        tournament = await self.cog.db.get_tournament(team.tournament_id)
        if tournament is None:
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Turnier nicht gefunden."),
                ephemeral=True,
            )
            return
        if tournament.status != TournamentStatus.OPEN:
            await interaction.response.send_message(
                embed=error_embed("Geschlossen", "Anmeldungen sind nicht mehr offen."),
                ephemeral=True,
            )
            return
        if team.registered:
            await interaction.response.send_message(
                embed=error_embed("Bereits angemeldet", f"**{team.name}** ist bereits registriert."),
                ephemeral=True,
            )
            return
        count = await self.cog.db.count_registered_teams(team.tournament_id)
        if count >= tournament.max_teams:
            await interaction.response.send_message(
                embed=error_embed("Voll", f"Maximale Team-Anzahl ({tournament.max_teams}) erreicht."),
                ephemeral=True,
            )
            return
        await self.cog.db.register_tournament_team(team.id)
        await interaction.response.defer()
        await self._refresh_message(interaction)
        await interaction.followup.send(
            embed=success_embed("Angemeldet", f"**{team.name}** ist offiziell angemeldet."),
        )

    async def _remove_member(self, interaction: discord.Interaction) -> None:
        if interaction.user is None:
            return
        team = await self._get_team()
        if team is None:
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Team nicht gefunden."),
                ephemeral=True,
            )
            return
        if team.captain_id != interaction.user.id:
            await interaction.response.send_message(
                embed=error_embed("Kein Captain", "Nur der Captain kann Mitglieder entfernen."),
                ephemeral=True,
            )
            return
        members = await self.cog.db.get_team_members(self.team_id)
        removable = [uid for uid in members if uid != team.captain_id]
        if not removable:
            await interaction.response.send_message(
                embed=info_embed("Keine Mitglieder", "Es gibt keine entfernbaren Mitglieder."),
                ephemeral=True,
            )
            return
        options = []
        for uid in removable[:25]:
            member = interaction.guild.get_member(uid) if interaction.guild else None
            label = member.display_name if member else f"User {uid}"
            options.append(discord.SelectOption(label=label[:100], value=str(uid)))
        view = discord.ui.View(timeout=120)
        team_id = self.team_id
        cog = self.cog

        async def on_select(select_interaction: discord.Interaction) -> None:
            values = select_interaction.data.get("values", []) if select_interaction.data else []
            if not values:
                return
            user_id = int(values[0])
            if not await cog.db.remove_team_member(team_id, user_id):
                await select_interaction.response.send_message(
                    embed=error_embed("Fehler", "Mitglied konnte nicht entfernt werden."),
                    ephemeral=True,
                )
                return
            await select_interaction.response.send_message(
                embed=success_embed("Entfernt", f"<@{user_id}> wurde aus dem Team entfernt."),
            )
            if select_interaction.guild is not None:
                await cog._refresh_team_interface(select_interaction.guild, team_id)

        select = discord.ui.Select(placeholder="Mitglied entfernen…", options=options)
        select.callback = on_select
        view.add_item(select)
        await interaction.response.send_message(
            embed=info_embed("Mitglied entfernen", f"Team **{team.name}**"),
            view=view,
            ephemeral=True,
        )


class CreateTeamNameModal(discord.ui.Modal, title="Team gründen"):
    """Teamname nach Turnier-Auswahl."""

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

        if interaction.guild is None or interaction.user is None:
            return
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Team-Interface nur in Textkanälen möglich."),
            )
            return
        name = _normalize_team_name(self.name_input.value)
        if not name:
            await interaction.response.send_message(
                embed=error_embed("Ungültig", "Teamname darf nicht leer sein."),
            )
            return
        if await self.cog.db.user_in_tournament_team(self.tournament_id, interaction.user.id):
            await interaction.response.send_message(
                embed=error_embed("Bereits im Team", "Du bist bereits in einem Team dieses Turniers."),
            )
            return
        if await self.cog.db.get_tournament_team_by_name(self.tournament_id, name):
            await interaction.response.send_message(
                embed=error_embed("Name vergeben", f"Team **{name}** existiert bereits."),
            )
            return
        team = await self.cog.db.create_tournament_team(
            self.tournament_id,
            name,
            interaction.user.id,
        )
        await interaction.response.defer()
        embed = await build_team_embed(self.cog, interaction.guild, team.id)
        view = TeamInterfaceView(self.cog, team.id)
        message = await interaction.channel.send(embed=embed, view=view, embed_persistent=True)
        await self.cog.db.update_team_interface(
            team.id,
            message_id=message.id,
            interface_channel_id=interaction.channel.id,
        )
        await interaction.followup.send(
            embed=success_embed(
                "Team erstellt",
                spaced_lines(
                    f"**{team.name}** (#{team.id}) – du bist Captain.",
                    "Nutze die Buttons unter dem Team-Interface.",
                ),
            ),
        )


class TournamentPickView(discord.ui.View):
    """Turnier-Auswahl vor Team-Erstellung."""

    def __init__(self, cog: TournamentCog, tournaments: list) -> None:
        super().__init__(timeout=120)
        self.cog = cog
        options = [
            discord.SelectOption(
                label=f"#{t.id} {t.name}"[:100],
                description=f"{t.game} · offen"[:100],
                value=str(t.id),
            )
            for t in tournaments[:25]
        ]
        select = discord.ui.Select(placeholder="Turnier wählen…", options=options)
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        values = interaction.data.get("values", []) if interaction.data else []
        if not values:
            return
        tournament_id = int(values[0])
        await interaction.response.send_modal(CreateTeamNameModal(self.cog, tournament_id))
