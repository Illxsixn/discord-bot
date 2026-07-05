"""
Ticket-System Cog.

Support-Tickets mit Panel, privaten Kanälen, Staff-Verwaltung und Logs.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Callable

import discord
from discord import app_commands
from discord.ext import commands

from database.database import Database
from database.models import (
    DEFAULT_TICKET_PANEL_BUTTON,
    DEFAULT_TICKET_PANEL_MESSAGE,
    DEFAULT_TICKET_PANEL_TITLE,
    DEFAULT_TICKET_WELCOME_MESSAGE,
    TicketRecord,
    TicketSettings,
    TicketStatus,
)
from utils.embeds import error_embed, info_embed, log_event_embed, spaced_lines, split_embed_fields, success_embed
from utils.helpers import format_placeholders, truncate_text
from utils.permissions import bot_can_use_channel, is_admin

logger = logging.getLogger(__name__)

STATUS_LABELS = {
    TicketStatus.OPEN: "Offen",
    TicketStatus.CLAIMED: "Übernommen",
    TicketStatus.CLOSED: "Geschlossen",
}


def ticket_staff_only() -> Callable:
    """Check für Ticket-Staff oder Administratoren."""

    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            raise app_commands.CheckFailure("Dieser Befehl funktioniert nur auf Servern.")

        member = interaction.user
        if not isinstance(member, discord.Member):
            raise app_commands.CheckFailure("Mitgliedsdaten konnten nicht geladen werden.")

        cog = interaction.client.get_cog("TicketsCog")
        if not isinstance(cog, TicketsCog):
            raise app_commands.CheckFailure("Ticket-System nicht geladen.")

        settings = await cog.db.get_ticket_settings(interaction.guild.id)
        if cog._is_ticket_staff(member, settings):
            return True

        embed = error_embed(
            "Keine Berechtigung",
            "Du benötigst die Ticket-Staff-Rolle oder Administrator-Rechte.",
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
        return False

    return app_commands.check(predicate)


def _sanitize_channel_name(name: str) -> str:
    """Erzeugt einen gültigen Discord-Kanalnamen."""
    cleaned = name.lower().replace(" ", "-")
    cleaned = re.sub(r"[^a-z0-9\-]", "", cleaned)
    cleaned = cleaned.strip("-") or "user"
    return cleaned[:90]


def _status_label(status: TicketStatus) -> str:
    return STATUS_LABELS.get(status, status.value)


def _format_panel_message(settings: TicketSettings, guild: discord.Guild) -> str:
    """Formatiert die Panel-Beschreibung mit Platzhaltern."""
    text = settings.panel_message or DEFAULT_TICKET_PANEL_MESSAGE
    text = text.replace("{button}", settings.panel_button_label or DEFAULT_TICKET_PANEL_BUTTON)
    text = text.replace("{server}", guild.name)
    text = text.replace("{membercount}", str(guild.member_count or len(guild.members)))
    return text


def _format_welcome_message(
    settings: TicketSettings,
    guild: discord.Guild,
    member: discord.Member,
    *,
    ticket_id: int,
) -> str:
    """Formatiert die Ticket-Begrüßung mit Platzhaltern."""
    text = settings.welcome_message or DEFAULT_TICKET_WELCOME_MESSAGE
    text = format_placeholders(text, member, guild)
    return text.replace("{ticket_id}", str(ticket_id))


def _build_ticket_embed(
    ticket: TicketRecord,
    guild: discord.Guild,
    settings: TicketSettings,
    *,
    member: discord.Member | None = None,
) -> discord.Embed:
    """Erstellt das Begrüßungs-Embed im Ticket-Kanal."""
    opener = member or guild.get_member(ticket.opener_id)
    opener_name = opener.mention if opener else f"<@{ticket.opener_id}>"
    claimed = (
        guild.get_member(ticket.claimed_by_id).mention
        if ticket.claimed_by_id and guild.get_member(ticket.claimed_by_id)
        else "—"
    )
    if opener is not None:
        description = _format_welcome_message(settings, guild, opener, ticket_id=ticket.id)
    else:
        description = (settings.welcome_message or DEFAULT_TICKET_WELCOME_MESSAGE).replace(
            "{ticket_id}", str(ticket.id)
        )

    return info_embed(
        f"Ticket #{ticket.id}",
        description,
        fields=[
            ("Status", _status_label(ticket.status), True),
            ("Erstellt von", opener_name, True),
            ("Übernommen von", claimed, True),
        ],
        footer_prefix=f"Ticket #{ticket.id}",
    )


def _build_panel_embed(guild: discord.Guild, settings: TicketSettings) -> discord.Embed:
    """Erstellt das öffentliche Ticket-Panel."""
    return info_embed(
        settings.panel_title or DEFAULT_TICKET_PANEL_TITLE,
        _format_panel_message(settings, guild),
        footer_prefix=guild.name,
    )


def _build_setup_status_embed(guild: discord.Guild, settings: TicketSettings) -> discord.Embed:
    """Zeigt den aktuellen Ticket-Setup-Status."""
    staff = guild.get_role(settings.staff_role_id) if settings.staff_role_id else None
    category = guild.get_channel(settings.category_id) if settings.category_id else None
    log_channel = guild.get_channel(settings.log_channel_id) if settings.log_channel_id else None

    status = "✅ Aktiv" if settings.enabled else "⏸️ Noch nicht aktiviert"
    fields = [
        ("Status", status, True),
        ("Staff-Rolle", staff.mention if staff else "—", True),
        (
            "Kategorie",
            category.mention if isinstance(category, discord.CategoryChannel) else "Keine",
            True,
        ),
        (
            "Log-Kanal",
            log_channel.mention if isinstance(log_channel, discord.TextChannel) else "Kein Log",
            True,
        ),
        ("Panel-Titel", settings.panel_title or DEFAULT_TICKET_PANEL_TITLE, False),
        (
            "Panel-Text",
            truncate_text(_format_panel_message(settings, guild), 900),
            False,
        ),
        ("Button-Text", settings.panel_button_label or DEFAULT_TICKET_PANEL_BUTTON, True),
        (
            "Ticket-Text",
            truncate_text(
                (settings.welcome_message or DEFAULT_TICKET_WELCOME_MESSAGE).replace(
                    "{user}", "@User"
                ),
                900,
            ),
            False,
        ),
    ]
    return info_embed(
        "Ticket-Setup",
        "Wähle unten die Einstellungen aus.\n"
        "Änderungen werden **sofort gespeichert**.\n\n"
        "**Platzhalter Panel:** `{server}`, `{membercount}`, `{button}`\n"
        "**Platzhalter Ticket:** `{user}`, `{username}`, `{server}`, `{ticket_id}`",
        fields=fields,
        footer_prefix="Setup",
    )


class TicketPanelView(discord.ui.View):
    """Persistentes Panel zum Erstellen von Tickets."""

    def __init__(
        self,
        cog: TicketsCog,
        *,
        button_label: str = DEFAULT_TICKET_PANEL_BUTTON,
    ) -> None:
        super().__init__(timeout=None)
        self.cog = cog

        create = discord.ui.Button(
            label=button_label[:80],
            style=discord.ButtonStyle.primary,
            emoji="🎫",
            custom_id="ticket:panel:create",
        )
        create.callback = self.create_ticket
        self.add_item(create)

    async def create_ticket(self, interaction: discord.Interaction) -> None:
        await self.cog.handle_panel_create(interaction)


class PanelMessageModal(discord.ui.Modal, title="Panel-Nachricht bearbeiten"):
    """Modal für Panel-Titel, Text und Button."""

    def __init__(self, cog: TicketsCog, settings: TicketSettings) -> None:
        super().__init__()
        self.cog = cog
        self.guild_id = settings.guild_id
        self.title_input = discord.ui.TextInput(
            label="Panel-Titel",
            default=settings.panel_title or DEFAULT_TICKET_PANEL_TITLE,
            max_length=100,
        )
        self.message_input = discord.ui.TextInput(
            label="Panel-Text",
            style=discord.TextStyle.paragraph,
            default=settings.panel_message or DEFAULT_TICKET_PANEL_MESSAGE,
            max_length=1500,
        )
        self.button_input = discord.ui.TextInput(
            label="Button-Text",
            default=settings.panel_button_label or DEFAULT_TICKET_PANEL_BUTTON,
            max_length=80,
        )
        self.add_item(self.title_input)
        self.add_item(self.message_input)
        self.add_item(self.button_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.db.update_ticket_settings(
            self.guild_id,
            panel_title=self.title_input.value.strip(),
            panel_message=self.message_input.value.strip(),
            panel_button_label=self.button_input.value.strip(),
        )
        await interaction.response.send_message(
            embed=success_embed("Gespeichert", "Panel-Nachricht wurde aktualisiert."),
            ephemeral=True,
        )


class WelcomeMessageModal(discord.ui.Modal, title="Ticket-Nachricht bearbeiten"):
    """Modal für die Begrüßung im Ticket-Kanal."""

    def __init__(self, cog: TicketsCog, settings: TicketSettings) -> None:
        super().__init__()
        self.cog = cog
        self.guild_id = settings.guild_id
        self.message_input = discord.ui.TextInput(
            label="Ticket-Begrüßung",
            style=discord.TextStyle.paragraph,
            default=settings.welcome_message or DEFAULT_TICKET_WELCOME_MESSAGE,
            max_length=1500,
        )
        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.db.update_ticket_settings(
            self.guild_id,
            welcome_message=self.message_input.value.strip(),
        )
        await interaction.response.send_message(
            embed=success_embed("Gespeichert", "Ticket-Nachricht wurde aktualisiert."),
            ephemeral=True,
        )


class TicketSetupView(discord.ui.View):
    """Interaktives Setup mit Auswahlmenüs und Buttons."""

    def __init__(
        self,
        cog: TicketsCog,
        guild: discord.Guild,
        *,
        panel_channel_id: int | None = None,
    ) -> None:
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.panel_channel_id = panel_channel_id
        self.add_item(StaffRoleSelect())
        self.add_item(CategorySelect())
        self.add_item(LogChannelSelect())

        panel_btn = discord.ui.Button(
            label="Panel-Text",
            style=discord.ButtonStyle.secondary,
            emoji="📝",
            row=3,
        )
        panel_btn.callback = self.edit_panel_message
        self.add_item(panel_btn)

        welcome_btn = discord.ui.Button(
            label="Ticket-Text",
            style=discord.ButtonStyle.secondary,
            emoji="💬",
            row=3,
        )
        welcome_btn.callback = self.edit_welcome_message
        self.add_item(welcome_btn)

        activate_btn = discord.ui.Button(
            label="Aktivieren",
            style=discord.ButtonStyle.success,
            emoji="✅",
            row=4,
        )
        activate_btn.callback = self.activate
        self.add_item(activate_btn)

        send_panel_btn = discord.ui.Button(
            label="Panel senden",
            style=discord.ButtonStyle.primary,
            emoji="🎫",
            row=4,
        )
        send_panel_btn.callback = self.send_panel
        self.add_item(send_panel_btn)

    async def _refresh(self, interaction: discord.Interaction) -> None:
        settings = await self.cog.db.get_ticket_settings(self.guild.id)
        embed = _build_setup_status_embed(self.guild, settings)
        await interaction.response.edit_message(embed=embed, view=self)

    async def edit_panel_message(self, interaction: discord.Interaction) -> None:
        settings = await self.cog.db.get_ticket_settings(self.guild.id)
        await interaction.response.send_modal(PanelMessageModal(self.cog, settings))

    async def edit_welcome_message(self, interaction: discord.Interaction) -> None:
        settings = await self.cog.db.get_ticket_settings(self.guild.id)
        await interaction.response.send_modal(WelcomeMessageModal(self.cog, settings))

    async def activate(self, interaction: discord.Interaction) -> None:
        settings = await self.cog.db.get_ticket_settings(self.guild.id)
        if settings.staff_role_id is None:
            await interaction.response.send_message(
                embed=error_embed("Staff-Rolle fehlt", "Wähle zuerst eine Staff-Rolle aus."),
                ephemeral=True,
            )
            return

        await self.cog.db.update_ticket_settings(self.guild.id, enabled=1)
        await interaction.response.send_message(
            embed=success_embed(
                "Ticket-System aktiv",
                "Das Ticket-System ist jetzt aktiv.\n"
                "Sende als Nächstes das Panel mit **Panel senden**.",
            ),
            ephemeral=True,
        )

    async def send_panel(self, interaction: discord.Interaction) -> None:
        settings = await self.cog.db.get_ticket_settings(self.guild.id)
        if settings.staff_role_id is None:
            await interaction.response.send_message(
                embed=error_embed("Staff-Rolle fehlt", "Wähle zuerst eine Staff-Rolle aus."),
                ephemeral=True,
            )
            return

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            if self.panel_channel_id:
                channel = self.guild.get_channel(self.panel_channel_id)
            if not isinstance(channel, discord.TextChannel):
                await interaction.response.send_message(
                    embed=error_embed("Fehler", "Panel kann nur in Textkanälen gesendet werden."),
                    ephemeral=True,
                )
                return

        allowed, msg = bot_can_use_channel(channel)
        if not allowed:
            await interaction.response.send_message(
                embed=error_embed("Fehler", msg or "Keine Berechtigung."),
                ephemeral=True,
            )
            return

        await self.cog.db.update_ticket_settings(self.guild.id, enabled=1)
        await self.cog._send_panel_to_channel(channel, self.guild)
        settings = await self.cog.db.get_ticket_settings(self.guild.id)
        await interaction.response.edit_message(
            embed=_build_setup_status_embed(self.guild, settings),
            view=self,
        )


class StaffRoleSelect(discord.ui.RoleSelect):
    """Staff-Rolle für Tickets."""

    def __init__(self) -> None:
        super().__init__(
            placeholder="Staff-Rolle wählen…",
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, TicketSetupView):
            return
        role = self.values[0]
        await view.cog.db.update_ticket_settings(view.guild.id, staff_role_id=role.id)
        await view._refresh(interaction)


class CategorySelect(discord.ui.ChannelSelect):
    """Kategorie für Ticket-Kanäle."""

    def __init__(self) -> None:
        super().__init__(
            placeholder="Kategorie wählen (optional)…",
            channel_types=[discord.ChannelType.category],
            min_values=1,
            max_values=1,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, TicketSetupView):
            return
        category = self.values[0]
        await view.cog.db.update_ticket_settings(view.guild.id, category_id=category.id)
        await view._refresh(interaction)


class LogChannelSelect(discord.ui.ChannelSelect):
    """Log-Kanal für Ticket-Ereignisse."""

    def __init__(self) -> None:
        super().__init__(
            placeholder="Log-Kanal wählen (optional)…",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, TicketSetupView):
            return
        channel = self.values[0]
        await view.cog.db.update_ticket_settings(view.guild.id, log_channel_id=channel.id)
        await view._refresh(interaction)


class TicketControlView(discord.ui.View):
    """Buttons zum Schließen und Übernehmen im Ticket-Kanal."""

    def __init__(self, cog: TicketsCog, ticket_id: int) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.ticket_id = ticket_id

        claim = discord.ui.Button(
            label="Übernehmen",
            style=discord.ButtonStyle.success,
            emoji="✋",
            custom_id=f"ticket:control:{ticket_id}:claim",
        )
        claim.callback = self.claim
        self.add_item(claim)

        close = discord.ui.Button(
            label="Schließen",
            style=discord.ButtonStyle.danger,
            emoji="🔒",
            custom_id=f"ticket:control:{ticket_id}:close",
        )
        close.callback = self.close
        self.add_item(close)

    async def claim(self, interaction: discord.Interaction) -> None:
        await self.cog.handle_claim(interaction, self.ticket_id)

    async def close(self, interaction: discord.Interaction) -> None:
        await self.cog.handle_close(interaction, self.ticket_id)


class TicketsCog(commands.GroupCog, group_name="ticket", group_description="Support-Tickets verwalten"):
    """Ticket-System mit Panel, Kanälen und Logs."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db

    async def cog_load(self) -> None:
        """Registriert persistente Ticket-Views nach Bot-Neustart."""
        self.bot.add_view(TicketPanelView(self))
        count = 0
        for ticket in await self.db.get_all_open_tickets():
            try:
                self.bot.add_view(TicketControlView(self, ticket.id))
                count += 1
            except Exception:
                logger.exception("Ticket-View konnte nicht registriert werden (Ticket %s)", ticket.id)
        if count:
            logger.info("Tickets: %d persistente Control-View(s) wiederhergestellt.", count)

    @staticmethod
    def _is_ticket_staff(member: discord.Member, settings: TicketSettings) -> bool:
        """Prüft, ob ein Mitglied Ticket-Staff ist."""
        if member.guild_permissions.administrator:
            return True
        if settings.staff_role_id is None:
            return False
        return any(role.id == settings.staff_role_id for role in member.roles)

    def _staff_check(self) -> Callable:
        """Legacy-Hilfsmethode — nutze ticket_staff_only() als Decorator."""
        return ticket_staff_only()

    async def _refresh_ticket_message(self, ticket: TicketRecord, guild: discord.Guild) -> None:
        """Aktualisiert das Ticket-Begrüßungs-Embed im Kanal."""
        channel = guild.get_channel(ticket.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        settings = await self.db.get_ticket_settings(guild.id)
        embed = _build_ticket_embed(ticket, guild, settings)
        view = TicketControlView(self, ticket.id)
        self.bot.add_view(view)

        try:
            async for message in channel.history(limit=20):
                if message.author.id == self.bot.user.id and message.embeds:
                    title = message.embeds[0].title or ""
                    if f"Ticket #{ticket.id}" in title:
                        await message.edit(embed=embed, view=view)
                        return
        except discord.HTTPException:
            logger.warning("Ticket-Nachricht #%s konnte nicht aktualisiert werden.", ticket.id)

    async def _send_ticket_log(
        self,
        guild: discord.Guild,
        event_name: str,
        description: str,
        *,
        fields: list[tuple[str, str, bool]] | None = None,
    ) -> None:
        """Sendet ein Log-Embed in den konfigurierten Ticket-Log-Kanal."""
        settings = await self.db.get_ticket_settings(guild.id)
        if not settings.log_channel_id:
            return

        channel = guild.get_channel(settings.log_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        allowed, _ = bot_can_use_channel(channel)
        if not allowed:
            return

        embed = log_event_embed(event_name, description, fields=fields)
        try:
            await channel.send(embed=embed, embed_persistent=True)
        except discord.HTTPException:
            logger.warning("Ticket-Log konnte nicht gesendet werden (Guild %s).", guild.id)

    async def _get_ticket_channel(
        self,
        interaction: discord.Interaction,
    ) -> tuple[TicketRecord, discord.TextChannel] | None:
        """Lädt Ticket und Kanal aus dem aktuellen Interaktions-Kanal."""
        if interaction.guild is None or interaction.channel is None:
            return None
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Dieser Befehl ist nur in Ticket-Kanälen nutzbar."),
                ephemeral=True,
            )
            return None

        ticket = await self.db.get_ticket_by_channel(interaction.channel.id)
        if ticket is None or ticket.status == TicketStatus.CLOSED:
            await interaction.response.send_message(
                embed=error_embed("Kein Ticket", "In diesem Kanal ist kein offenes Ticket aktiv."),
                ephemeral=True,
            )
            return None

        return ticket, interaction.channel

    async def _create_ticket_channel(
        self,
        guild: discord.Guild,
        member: discord.Member,
        settings: TicketSettings,
    ) -> discord.TextChannel:
        """Erstellt einen privaten Ticket-Kanal."""
        category = guild.get_channel(settings.category_id) if settings.category_id else None
        if category is not None and not isinstance(category, discord.CategoryChannel):
            category = None

        overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
            ),
        }
        if settings.staff_role_id:
            staff_role = guild.get_role(settings.staff_role_id)
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                )

        base_name = _sanitize_channel_name(member.display_name)
        channel_name = f"ticket-{base_name}"
        return await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            reason=f"Ticket erstellt von {member} ({member.id})",
        )

    async def _send_panel_to_channel(
        self,
        channel: discord.TextChannel,
        guild: discord.Guild,
    ) -> discord.Message:
        """Sendet das Ticket-Panel in einen Kanal."""
        settings = await self.db.get_ticket_settings(guild.id)
        view = TicketPanelView(self, button_label=settings.panel_button_label)
        self.bot.add_view(view)
        message = await channel.send(embed=_build_panel_embed(guild, settings), view=view, embed_persistent=True)
        self.bot.add_view(view, message_id=message.id)
        await self.db.update_ticket_settings(
            guild.id,
            panel_channel_id=channel.id,
            panel_message_id=message.id,
        )
        return message

    async def handle_panel_create(self, interaction: discord.Interaction) -> None:
        """Erstellt ein Ticket nach Klick auf das Panel."""
        await interaction.response.defer(ephemeral=True)
        if interaction.guild is None:
            return

        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if member is None:
            return

        settings = await self.db.get_ticket_settings(interaction.guild.id)
        if not settings.enabled:
            await interaction.followup.send(
                embed=error_embed("Deaktiviert", "Das Ticket-System ist auf diesem Server nicht aktiv."),
                ephemeral=True,
            )
            return

        existing = await self.db.get_open_ticket_by_user(interaction.guild.id, member.id)
        if existing is not None:
            channel = interaction.guild.get_channel(existing.channel_id)
            link = channel.mention if isinstance(channel, discord.TextChannel) else f"<#{existing.channel_id}>"
            await interaction.followup.send(
                embed=error_embed(
                    "Bereits offen",
                    f"Du hast bereits ein offenes Ticket: {link}\n"
                    "Schließe es zuerst mit `/ticket close` oder dem Button im Kanal.",
                ),
                ephemeral=True,
            )
            return

        try:
            channel = await self._create_ticket_channel(interaction.guild, member, settings)
        except discord.Forbidden:
            await interaction.followup.send(
                embed=error_embed(
                    "Fehler",
                    "Ich kann keinen Ticket-Kanal erstellen. Prüfe meine Berechtigungen und die Kategorie.",
                ),
                ephemeral=True,
            )
            return
        except discord.HTTPException as exc:
            logger.exception("Ticket-Kanal konnte nicht erstellt werden: %s", exc)
            await interaction.followup.send(
                embed=error_embed("Fehler", "Der Ticket-Kanal konnte nicht erstellt werden."),
                ephemeral=True,
            )
            return

        ticket = await self.db.create_ticket(interaction.guild.id, channel.id, member.id)
        view = TicketControlView(self, ticket.id)
        self.bot.add_view(view)
        embed = _build_ticket_embed(ticket, interaction.guild, settings, member=member)
        await channel.send(content=member.mention, embed=embed, view=view, embed_persistent=True)

        await self._send_ticket_log(
            interaction.guild,
            "Ticket erstellt",
            f"Neues Ticket **#{ticket.id}** von {member.mention}",
            fields=[
                ("Kanal", channel.mention, True),
                ("Ersteller", member.mention, True),
            ],
        )

        await interaction.followup.send(
            embed=success_embed("Ticket erstellt", f"Dein Ticket: {channel.mention}"),
            ephemeral=True,
        )

    async def handle_claim(self, interaction: discord.Interaction, ticket_id: int) -> None:
        """Staff übernimmt ein Ticket per Button."""
        if interaction.guild is None:
            return

        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if member is None:
            return

        settings = await self.db.get_ticket_settings(interaction.guild.id)
        if not self._is_ticket_staff(member, settings):
            await interaction.response.send_message(
                embed=error_embed("Keine Berechtigung", "Nur Ticket-Staff kann Tickets übernehmen."),
                ephemeral=True,
            )
            return

        ticket = await self.db.get_ticket(ticket_id)
        if ticket is None or ticket.guild_id != interaction.guild.id:
            await interaction.response.send_message(
                embed=error_embed("Nicht gefunden", "Dieses Ticket existiert nicht mehr."),
                ephemeral=True,
            )
            return

        if ticket.status == TicketStatus.CLOSED:
            await interaction.response.send_message(
                embed=error_embed("Geschlossen", "Dieses Ticket ist bereits geschlossen."),
                ephemeral=True,
            )
            return

        if ticket.claimed_by_id == member.id:
            await interaction.response.send_message(
                embed=error_embed("Bereits übernommen", "Du hast dieses Ticket bereits übernommen."),
                ephemeral=True,
            )
            return

        if ticket.claimed_by_id and ticket.claimed_by_id != member.id:
            await interaction.response.send_message(
                embed=error_embed(
                    "Bereits übernommen",
                    f"Dieses Ticket wurde bereits von <@{ticket.claimed_by_id}> übernommen.",
                ),
                ephemeral=True,
            )
            return

        is_component_interaction = (
            interaction.type is discord.InteractionType.component and interaction.message is not None
        )
        if not is_component_interaction and not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        updated = await self.db.update_ticket(
            ticket.id,
            status=TicketStatus.CLAIMED,
            claimed_by_id=member.id,
        )
        assert updated is not None
        settings = await self.db.get_ticket_settings(interaction.guild.id)
        embed = _build_ticket_embed(updated, interaction.guild, settings)

        if is_component_interaction:
            await interaction.response.edit_message(embed=embed)
        else:
            await self._refresh_ticket_message(updated, interaction.guild)
            await interaction.followup.send(
                embed=success_embed("Ticket übernommen", f"Du hast Ticket **#{ticket.id}** übernommen."),
                ephemeral=True,
            )

        await self._send_ticket_log(
            interaction.guild,
            "Ticket übernommen",
            f"Ticket **#{ticket.id}** wurde von {member.mention} übernommen.",
            fields=[("Staff", member.mention, True)],
        )

    async def handle_close(
        self,
        interaction: discord.Interaction,
        ticket_id: int,
        *,
        skip_permission_check: bool = False,
    ) -> None:
        """Schließt ein Ticket und löscht den Kanal."""
        if interaction.guild is None:
            return

        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if member is None:
            return

        ticket = await self.db.get_ticket(ticket_id)
        if ticket is None or ticket.guild_id != interaction.guild.id:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    embed=error_embed("Nicht gefunden", "Dieses Ticket existiert nicht mehr."),
                    ephemeral=True,
                )
            return

        if ticket.status == TicketStatus.CLOSED:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    embed=error_embed("Geschlossen", "Dieses Ticket ist bereits geschlossen."),
                    ephemeral=True,
                )
            return

        settings = await self.db.get_ticket_settings(interaction.guild.id)
        if not skip_permission_check:
            is_opener = member.id == ticket.opener_id
            is_staff = self._is_ticket_staff(member, settings)
            if not is_opener and not is_staff:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        embed=error_embed(
                            "Keine Berechtigung",
                            "Nur der Ersteller oder Ticket-Staff kann dieses Ticket schließen.",
                        ),
                        ephemeral=True,
                    )
                return

        channel = interaction.guild.get_channel(ticket.channel_id)
        if not isinstance(channel, discord.TextChannel):
            channel = interaction.channel if isinstance(interaction.channel, discord.TextChannel) else None

        now = datetime.now(timezone.utc)
        await self.db.update_ticket(ticket.id, status=TicketStatus.CLOSED, closed_at=now)

        await self._send_ticket_log(
            interaction.guild,
            "Ticket geschlossen",
            f"Ticket **#{ticket.id}** wurde von {member.mention} geschlossen.",
            fields=[
                ("Ersteller", f"<@{ticket.opener_id}>", True),
                ("Geschlossen von", member.mention, True),
            ],
        )

        if not interaction.response.is_done():
            await interaction.response.send_message(
                embed=success_embed("Ticket geschlossen", "Dieser Kanal wird gleich gelöscht."),
                ephemeral=False,
            )

        # Kanal löschen statt archivieren: einfacher, keine Archiv-Kategorie nötig,
        # und verhindert Permission-Müll in der Kanalliste.
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.delete(reason=f"Ticket #{ticket.id} geschlossen von {member}")
            except discord.HTTPException:
                logger.warning("Ticket-Kanal #%s konnte nicht gelöscht werden.", ticket.channel_id)

    @app_commands.command(name="setup", description="Richtet das Ticket-System interaktiv ein.")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    async def setup(self, interaction: discord.Interaction) -> None:
        """Öffnet das interaktive Setup mit Buttons und Auswahlmenüs."""
        await interaction.response.defer(ephemeral=True)
        if interaction.guild is None:
            return

        settings = await self.db.get_ticket_settings(interaction.guild.id)
        panel_channel_id = (
            interaction.channel.id if isinstance(interaction.channel, discord.TextChannel) else None
        )
        view = TicketSetupView(self, interaction.guild, panel_channel_id=panel_channel_id)
        await interaction.followup.send(
            embed=_build_setup_status_embed(interaction.guild, settings),
            view=view,
            ephemeral=True,
        )

    @app_commands.command(name="message", description="Passt Panel- oder Ticket-Nachrichten an.")
    @app_commands.guild_only()
    @app_commands.describe(typ="Welche Nachricht soll bearbeitet werden?")
    @app_commands.choices(
        typ=[
            app_commands.Choice(name="Panel-Nachricht", value="panel"),
            app_commands.Choice(name="Ticket-Nachricht", value="welcome"),
        ]
    )
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    async def message(
        self,
        interaction: discord.Interaction,
        typ: str,
    ) -> None:
        """Öffnet ein Modal zum Bearbeiten der Texte."""
        if interaction.guild is None:
            return

        settings = await self.db.get_ticket_settings(interaction.guild.id)
        if typ == "panel":
            await interaction.response.send_modal(PanelMessageModal(self, settings))
        else:
            await interaction.response.send_modal(WelcomeMessageModal(self, settings))

    @app_commands.command(name="panel", description="Sendet das Ticket-Panel in den aktuellen Kanal.")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    async def panel(self, interaction: discord.Interaction) -> None:
        """Sendet das öffentliche Ticket-Panel."""
        await interaction.response.defer(ephemeral=True)
        if interaction.guild is None or interaction.channel is None:
            return

        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.followup.send(
                embed=error_embed("Fehler", "Das Panel kann nur in Textkanälen gesendet werden."),
                ephemeral=True,
            )
            return

        settings = await self.db.get_ticket_settings(interaction.guild.id)
        if not settings.enabled:
            await interaction.followup.send(
                embed=error_embed("Nicht eingerichtet", "Nutze zuerst `/ticket setup`."),
                ephemeral=True,
            )
            return

        allowed, msg = bot_can_use_channel(interaction.channel)
        if not allowed:
            await interaction.followup.send(embed=error_embed("Fehler", msg or "Keine Berechtigung."), ephemeral=True)
            return

        await self.db.update_ticket_settings(interaction.guild.id, enabled=1)
        try:
            message = await self._send_panel_to_channel(interaction.channel, interaction.guild)
        except discord.HTTPException as exc:
            logger.warning("Ticket-Panel konnte nicht gesendet werden: %s", exc)
            await interaction.followup.send(
                embed=error_embed("Fehler", "Ticket-Panel konnte nicht gesendet werden."),
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            embed=success_embed("Panel gesendet", f"Ticket-Panel in {message.channel.mention} erstellt."),
            ephemeral=True,
        )

    @app_commands.command(name="close", description="Schließt das Ticket in diesem Kanal.")
    @app_commands.guild_only()
    async def close(self, interaction: discord.Interaction) -> None:
        """Schließt das aktuelle Ticket."""
        if interaction.guild is None or interaction.channel is None:
            return
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Dieser Befehl ist nur in Ticket-Kanälen nutzbar."),
                ephemeral=True,
            )
            return

        ticket = await self.db.get_ticket_by_channel(interaction.channel.id)
        if ticket is None or ticket.status == TicketStatus.CLOSED:
            await interaction.response.send_message(
                embed=error_embed("Kein Ticket", "In diesem Kanal ist kein offenes Ticket aktiv."),
                ephemeral=True,
            )
            return

        await self.handle_close(interaction, ticket.id)

    @app_commands.command(name="claim", description="Übernimmt das Ticket in diesem Kanal.")
    @app_commands.guild_only()
    @ticket_staff_only()
    async def claim(self, interaction: discord.Interaction) -> None:
        """Staff übernimmt das Ticket per Slash-Command."""
        if interaction.guild is None or interaction.channel is None:
            return
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Dieser Befehl ist nur in Ticket-Kanälen nutzbar."),
                ephemeral=True,
            )
            return

        ticket = await self.db.get_ticket_by_channel(interaction.channel.id)
        if ticket is None or ticket.status == TicketStatus.CLOSED:
            await interaction.response.send_message(
                embed=error_embed("Kein Ticket", "In diesem Kanal ist kein offenes Ticket aktiv."),
                ephemeral=True,
            )
            return

        await self.handle_claim(interaction, ticket.id)

    @app_commands.command(name="add", description="Fügt ein Mitglied zum Ticket hinzu.")
    @app_commands.guild_only()
    @app_commands.describe(user="Mitglied, das Zugriff erhalten soll")
    @ticket_staff_only()
    async def add(self, interaction: discord.Interaction, user: discord.Member) -> None:
        """Gibt einem Mitglied Zugriff auf den Ticket-Kanal."""
        result = await self._get_ticket_channel(interaction)
        if result is None:
            return

        ticket, channel = result
        await interaction.response.defer(ephemeral=True)

        overwrite = channel.overwrites_for(user)
        overwrite.view_channel = True
        overwrite.send_messages = True
        overwrite.read_message_history = True

        try:
            await channel.set_permissions(user, overwrite=overwrite, reason=f"Zu Ticket #{ticket.id} hinzugefügt")
        except discord.Forbidden:
            await interaction.followup.send(
                embed=error_embed("Fehler", "Ich kann die Berechtigungen nicht ändern."),
                ephemeral=True,
            )
            return

        await channel.send(
            embed=info_embed("Mitglied hinzugefügt", f"{user.mention} hat Zugriff auf dieses Ticket."),
            embed_persistent=True,
        )
        await self._send_ticket_log(
            interaction.guild,  # type: ignore[arg-type]
            "Mitglied hinzugefügt",
            f"{user.mention} wurde zu Ticket **#{ticket.id}** hinzugefügt.",
            fields=[("Hinzugefügt von", interaction.user.mention, True)],
        )
        await interaction.followup.send(
            embed=success_embed("Hinzugefügt", f"{user.mention} hat Zugriff auf {channel.mention}."),
            ephemeral=True,
        )

    @app_commands.command(name="remove", description="Entfernt ein Mitglied aus dem Ticket.")
    @app_commands.guild_only()
    @app_commands.describe(user="Mitglied, das entfernt werden soll")
    @ticket_staff_only()
    async def remove(self, interaction: discord.Interaction, user: discord.Member) -> None:
        """Entzieht einem Mitglied den Zugriff auf den Ticket-Kanal."""
        result = await self._get_ticket_channel(interaction)
        if result is None:
            return

        ticket, channel = result
        if user.id == ticket.opener_id:
            await interaction.response.send_message(
                embed=error_embed("Nicht erlaubt", "Der Ticket-Ersteller kann nicht entfernt werden."),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            await channel.set_permissions(user, overwrite=None, reason=f"Aus Ticket #{ticket.id} entfernt")
        except discord.Forbidden:
            await interaction.followup.send(
                embed=error_embed("Fehler", "Ich kann die Berechtigungen nicht ändern."),
                ephemeral=True,
            )
            return

        await channel.send(
            embed=info_embed("Mitglied entfernt", f"{user.mention} wurde aus diesem Ticket entfernt."),
            embed_persistent=True,
        )
        await self._send_ticket_log(
            interaction.guild,  # type: ignore[arg-type]
            "Mitglied entfernt",
            f"{user.mention} wurde aus Ticket **#{ticket.id}** entfernt.",
            fields=[("Entfernt von", interaction.user.mention, True)],
        )
        await interaction.followup.send(
            embed=success_embed("Entfernt", f"{user.mention} hat keinen Zugriff mehr auf {channel.mention}."),
            ephemeral=True,
        )

    @app_commands.command(name="list", description="Zeigt alle offenen Tickets auf dem Server.")
    @app_commands.guild_only()
    @ticket_staff_only()
    async def list(self, interaction: discord.Interaction) -> None:
        """Listet offene Tickets für Staff."""
        await interaction.response.defer(ephemeral=True)
        if interaction.guild is None:
            return

        tickets = await self.db.get_open_tickets_for_guild(interaction.guild.id)
        if not tickets:
            await interaction.followup.send(
                embed=info_embed("Keine Tickets", "Es gibt derzeit keine offenen Tickets."),
                ephemeral=True,
            )
            return

        lines = []
        for ticket in tickets:
            channel = interaction.guild.get_channel(ticket.channel_id)
            channel_ref = channel.mention if isinstance(channel, discord.TextChannel) else f"<#{ticket.channel_id}>"
            opener = interaction.guild.get_member(ticket.opener_id)
            opener_name = opener.mention if opener else f"<@{ticket.opener_id}>"
            claimed = (
                interaction.guild.get_member(ticket.claimed_by_id).mention
                if ticket.claimed_by_id and interaction.guild.get_member(ticket.claimed_by_id)
                else "—"
            )
            lines.append(
                spaced_lines(
                    f"**#{ticket.id}** · {channel_ref}",
                    f"Status: **{_status_label(ticket.status)}**",
                    f"Ersteller: {opener_name}",
                    f"Staff: {claimed}",
                )
            )

        await interaction.followup.send(
            embed=info_embed(
                f"Offene Tickets — {interaction.guild.name}",
                f"**{len(tickets)}** offene(s) Ticket(s)",
                fields=split_embed_fields("Tickets", lines),
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    """Lädt das Ticket-System."""
    db: Database = bot.db  # type: ignore[attr-defined]
    await bot.add_cog(TicketsCog(bot, db))
