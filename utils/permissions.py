"""
Berechtigungsprüfungen für Slash Commands und Moderationsaktionen.

Stellt wiederverwendbare Checks sicher, dass nur autorisierte Nutzer
Moderations- und Konfigurationsbefehle ausführen können.

Discord-seitige Sichtbarkeit (`default_permissions`) und Laufzeit-Checks
(`has_guild_permissions`, `is_moderator`) werden gemeinsam eingesetzt.
"""

from __future__ import annotations

from typing import Callable

import discord
from discord import app_commands

from utils.embeds import error_embed


def member_is_moderator(member: discord.Member) -> bool:
    """
    Prüft, ob ein Mitglied als Moderator gilt (AutoMod-Ausnahme etc.).

    Args:
        member: Zu prüfendes Servermitglied.

    Returns:
        True wenn Moderations- oder Nachrichtenverwaltungsrechte vorliegen.
    """
    perms = member.guild_permissions
    return (
        perms.administrator
        or perms.kick_members
        or perms.ban_members
        or perms.moderate_members
        or perms.manage_messages
    )


def has_guild_permissions(**perms: bool) -> Callable:
    """
    Erstellt einen app_commands.check für Discord-Berechtigungen.

    Args:
        **perms: Discord-Berechtigungsflags (z. B. ban_members=True).

    Returns:
        Check-Decorator für Slash Commands.
    """

    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            raise app_commands.CheckFailure("Dieser Befehl funktioniert nur auf Servern.")

        member = interaction.user
        if not isinstance(member, discord.Member):
            raise app_commands.CheckFailure("Mitgliedsdaten konnten nicht geladen werden.")

        missing = [perm for perm, required in perms.items() if required and not getattr(member.guild_permissions, perm)]
        if missing:
            readable = ", ".join(m.replace("_", " ").title() for m in missing)
            embed = error_embed(
                "Fehlende Berechtigung",
                f"Du benötigst folgende Berechtigungen: **{readable}**",
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        return True

    return app_commands.check(predicate)


def is_admin() -> Callable:
    """
    Prüft, ob der Nutzer Administrator-Rechte hat.

    Returns:
        Check-Decorator für Slash Commands.
    """
    return has_guild_permissions(administrator=True)


def can_manage_community() -> Callable:
    """
    Prüft Berechtigung für Umfragen und Community-Funktionen.

    Returns:
        Check-Decorator (Nachrichten verwalten oder Administrator).
    """
    return has_guild_permissions(manage_messages=True)


def can_manage_giveaways() -> Callable:
    """
    Prüft Berechtigung für Gewinnspiele.

    Returns:
        Check-Decorator (Server verwalten oder Administrator).
    """
    return has_guild_permissions(manage_guild=True)


def is_moderator() -> Callable:
    """
    Prüft Moderations-Berechtigungen (Kick, Ban, Timeout oder Nachrichtenverwaltung).

    Für Verwarnungsbefehle: breiter Check, da Warnungen typischerweise
    dem Moderationsteam gehören, nicht nur Timeout-Berechtigten.

    Returns:
        Check-Decorator für Slash Commands.
    """

    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            raise app_commands.CheckFailure("Dieser Befehl funktioniert nur auf Servern.")

        member = interaction.user
        if not isinstance(member, discord.Member):
            raise app_commands.CheckFailure("Mitgliedsdaten konnten nicht geladen werden.")

        if member_is_moderator(member):
            return True

        embed = error_embed(
            "Fehlende Berechtigung",
            "Du benötigst Moderationsrechte (Kick, Ban, Timeout oder Nachrichten verwalten).",
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
        return False

    return app_commands.check(predicate)


def bot_can_use_channel(
    channel: discord.abc.GuildChannel,
    *,
    send: bool = True,
    embed_links: bool = True,
    add_reactions: bool = False,
    manage_messages: bool = False,
    read_history: bool = False,
) -> tuple[bool, str | None]:
    """
    Prüft Bot-Berechtigungen in einem Kanal.

    Args:
        channel: Zielkanal.
        send: Nachrichten senden erforderlich.
        embed_links: Links einbetten erforderlich.
        add_reactions: Reaktionen hinzufügen erforderlich.
        manage_messages: Nachrichten verwalten erforderlich.
        read_history: Nachrichtenverlauf lesen erforderlich.

    Returns:
        Tuple (erlaubt, fehlermeldung).
    """
    guild = channel.guild
    me = guild.me
    if me is None:
        return False, "Bot-Mitgliedsdaten nicht verfügbar."

    perms = channel.permissions_for(me)
    missing: list[str] = []
    if send and not perms.send_messages:
        missing.append("Nachrichten senden")
    if embed_links and not perms.embed_links:
        missing.append("Links einbetten")
    if add_reactions and not perms.add_reactions:
        missing.append("Reaktionen hinzufügen")
    if manage_messages and not perms.manage_messages:
        missing.append("Nachrichten verwalten")
    if read_history and not perms.read_message_history:
        missing.append("Nachrichtenverlauf lesen")

    if missing:
        readable = ", ".join(missing)
        return False, f"Mir fehlen im Kanal {channel.mention} folgende Berechtigungen: **{readable}**"
    return True, None


def bot_can_moderate(member: discord.Member) -> tuple[bool, str | None]:
    """
    Prüft, ob der Bot ein Zielmitglied moderieren darf (Rollenhierarchie).

    Args:
        member: Zielmitglied.

    Returns:
        Tuple (erlaubt, fehlermeldung).
    """
    guild = member.guild
    bot_member = guild.me
    if bot_member is None:
        return False, "Bot-Mitgliedsdaten nicht verfügbar."

    if member.top_role >= bot_member.top_role:
        return False, "Ich kann dieses Mitglied nicht moderieren (Rollenhierarchie)."

    return True, None


def user_can_moderate(
    moderator: discord.Member,
    target: discord.Member,
) -> tuple[bool, str | None]:
    """
    Prüft, ob ein Moderator ein Ziel moderieren darf.

    Args:
        moderator: Ausführender Moderator.
        target: Zielmitglied.

    Returns:
        Tuple (erlaubt, fehlermeldung).
    """
    if moderator.id == target.id:
        return False, "Du kannst diese Aktion nicht an dir selbst ausführen."

    if target.guild.owner_id == target.id:
        return False, "Der Serverbesitzer kann nicht moderiert werden."

    if target.top_role >= moderator.top_role and moderator.id != target.guild.owner_id:
        return False, "Du kannst dieses Mitglied nicht moderieren (Rollenhierarchie)."

    allowed, msg = bot_can_moderate(target)
    if not allowed:
        return False, msg

    return True, None
