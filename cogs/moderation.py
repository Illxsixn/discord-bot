"""
Moderations-Cog mit Slash Commands.

Enthält Ban, Kick, Timeout, Warn, Clear, Slowmode, Lock/Unlock,
Nickname, Mute/Unmute und integriertes Logging.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from config import Config
from database.database import Database
from utils.embeds import error_embed, info_embed, moderation_embed, success_embed, warn_embed
from utils.helpers import parse_duration_minutes
from utils.permissions import has_guild_permissions, user_can_moderate

if TYPE_CHECKING:
    from cogs.logs import LogsCog

logger = logging.getLogger(__name__)


class ModerationCog(commands.Cog):
    """Slash-Commands für Server-Moderation."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        """
        Initialisiert den Moderation-Cog.

        Args:
            bot: Bot-Instanz.
            db: Datenbank-Instanz.
        """
        self.bot = bot
        self.db = db

    def _get_logs_cog(self) -> "LogsCog | None":
        """Holt den Logs-Cog für Moderations-Logging."""
        cog = self.bot.get_cog("LogsCog")
        return cog  # type: ignore[return-value]

    async def _get_or_create_mute_role(self, guild: discord.Guild) -> discord.Role:
        """
        Holt oder erstellt die Mute-Rolle für einen Server.

        Args:
            guild: Discord-Server.

        Returns:
            Mute-Rolle.
        """
        settings = await self.db.get_guild_settings(guild.id)
        if settings.mute_role_id:
            role = guild.get_role(settings.mute_role_id)
            if role:
                return role

        # Rolle erstellen
        role = await guild.create_role(
            name="Muted",
            reason="Automatische Mute-Rolle für Moderations-Bot",
            permissions=discord.Permissions(send_messages=False, speak=False, add_reactions=False),
        )

        # Kanal-Overrides setzen
        for channel in guild.channels:
            if isinstance(channel, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel)):
                try:
                    await channel.set_permissions(role, send_messages=False, speak=False)
                except discord.Forbidden:
                    pass

        await self.db.update_guild_settings(guild.id, mute_role_id=role.id)
        return role

    @app_commands.command(name="ban", description="Bannt ein Mitglied vom Server.")
    @app_commands.describe(user="Zu bannendes Mitglied", reason="Optionaler Grund")
    @app_commands.default_permissions(ban_members=True)
    @has_guild_permissions(ban_members=True)
    @app_commands.checks.cooldown(1, Config.DEFAULT_COOLDOWN)
    async def ban(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str | None = None,
    ) -> None:
        """Bannt ein Servermitglied."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None or not isinstance(interaction.user, discord.Member):
                return

            allowed, msg = user_can_moderate(interaction.user, user)
            if not allowed:
                await interaction.followup.send(embed=error_embed("Moderation fehlgeschlagen", msg), ephemeral=True)
                return

            reason_text = reason or "Kein Grund angegeben"
            await user.ban(reason=f"{reason_text} | Von: {interaction.user}", delete_message_days=0)

            embed = moderation_embed("Ban", user, interaction.user, reason_text, color=Config.COLOR_ERROR)
            await interaction.followup.send(embed=success_embed("Mitglied gebannt", f"{user.mention} wurde gebannt."), ephemeral=True)

            logs = self._get_logs_cog()
            if logs:
                await logs.send_log(interaction.guild, embed)

        except discord.Forbidden:
            await interaction.followup.send(embed=error_embed("Fehler", "Keine Berechtigung zum Bannen."), ephemeral=True)
        except Exception as exc:
            logger.exception("Ban fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="kick", description="Kickt ein Mitglied vom Server.")
    @app_commands.describe(user="Zu kickendes Mitglied", reason="Optionaler Grund")
    @app_commands.default_permissions(kick_members=True)
    @has_guild_permissions(kick_members=True)
    @app_commands.checks.cooldown(1, Config.DEFAULT_COOLDOWN)
    async def kick(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str | None = None,
    ) -> None:
        """Kickt ein Servermitglied."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None or not isinstance(interaction.user, discord.Member):
                return

            allowed, msg = user_can_moderate(interaction.user, user)
            if not allowed:
                await interaction.followup.send(embed=error_embed("Moderation fehlgeschlagen", msg), ephemeral=True)
                return

            reason_text = reason or "Kein Grund angegeben"
            await user.kick(reason=f"{reason_text} | Von: {interaction.user}")

            embed = moderation_embed("Kick", user, interaction.user, reason_text, color=Config.COLOR_WARNING)
            await interaction.followup.send(embed=success_embed("Mitglied gekickt", f"{user.mention} wurde gekickt."), ephemeral=True)

            logs = self._get_logs_cog()
            if logs:
                await logs.send_log(interaction.guild, embed)

        except discord.Forbidden:
            await interaction.followup.send(embed=error_embed("Fehler", "Keine Berechtigung zum Kicken."), ephemeral=True)
        except Exception as exc:
            logger.exception("Kick fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="timeout", description="Setzt ein Mitglied in Timeout.")
    @app_commands.describe(user="Mitglied", minutes="Dauer in Minuten (1-40320)", reason="Optionaler Grund")
    @app_commands.default_permissions(moderate_members=True)
    @has_guild_permissions(moderate_members=True)
    @app_commands.checks.cooldown(1, Config.DEFAULT_COOLDOWN)
    async def timeout(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        minutes: app_commands.Range[int, 1, 40320],
        reason: str | None = None,
    ) -> None:
        """Timeout für ein Mitglied."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None or not isinstance(interaction.user, discord.Member):
                return

            allowed, msg = user_can_moderate(interaction.user, user)
            if not allowed:
                await interaction.followup.send(embed=error_embed("Moderation fehlgeschlagen", msg), ephemeral=True)
                return

            duration = parse_duration_minutes(minutes)
            reason_text = reason or "Kein Grund angegeben"
            await user.timeout(duration, reason=f"{reason_text} | Von: {interaction.user}")

            embed = moderation_embed(
                "Timeout",
                user,
                interaction.user,
                f"{reason_text}\nDauer: {minutes} Min.",
                color=Config.COLOR_WARNING,
            )
            await interaction.followup.send(
                embed=success_embed("Timeout gesetzt", f"{user.mention} für **{minutes}** Min. in Timeout."),
                ephemeral=True,
            )

            logs = self._get_logs_cog()
            if logs:
                await logs.send_log(interaction.guild, embed)

        except discord.Forbidden:
            await interaction.followup.send(embed=error_embed("Fehler", "Keine Berechtigung für Timeout."), ephemeral=True)
        except Exception as exc:
            logger.exception("Timeout fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="untimeout", description="Hebt den Timeout eines Mitglieds auf.")
    @app_commands.describe(user="Mitglied", reason="Optionaler Grund")
    @app_commands.default_permissions(moderate_members=True)
    @has_guild_permissions(moderate_members=True)
    @app_commands.checks.cooldown(1, Config.DEFAULT_COOLDOWN)
    async def untimeout(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str | None = None,
    ) -> None:
        """Hebt Timeout auf."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None or not isinstance(interaction.user, discord.Member):
                return

            allowed, msg = user_can_moderate(interaction.user, user)
            if not allowed:
                await interaction.followup.send(embed=error_embed("Moderation fehlgeschlagen", msg), ephemeral=True)
                return

            reason_text = reason or "Kein Grund angegeben"
            await user.timeout(None, reason=f"{reason_text} | Von: {interaction.user}")

            embed = moderation_embed("Timeout aufgehoben", user, interaction.user, reason_text)
            await interaction.followup.send(embed=success_embed("Timeout aufgehoben", f"Timeout von {user.mention} entfernt."), ephemeral=True)

            logs = self._get_logs_cog()
            if logs:
                await logs.send_log(interaction.guild, embed)

        except Exception as exc:
            logger.exception("Untimeout fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="warn", description="Verwarnt ein Mitglied.")
    @app_commands.describe(user="Mitglied", reason="Grund der Verwarnung")
    @app_commands.default_permissions(moderate_members=True)
    @has_guild_permissions(moderate_members=True)
    @app_commands.checks.cooldown(1, Config.DEFAULT_COOLDOWN)
    async def warn(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str | None = None,
    ) -> None:
        """Speichert eine Verwarnung in der Datenbank."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None or not isinstance(interaction.user, discord.Member):
                return

            allowed, msg = user_can_moderate(interaction.user, user)
            if not allowed:
                await interaction.followup.send(embed=error_embed("Moderation fehlgeschlagen", msg), ephemeral=True)
                return

            reason_text = reason or "Kein Grund angegeben"
            record = await self.db.add_warning(
                interaction.guild.id,
                user.id,
                interaction.user.id,
                reason_text,
            )
            count = await self.db.count_warnings(interaction.guild.id, user.id)

            embed = warn_embed(
                user,
                interaction.user,
                interaction.guild,
                reason_text,
                warning_id=record.id,
                total_warnings=count,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

            logs = self._get_logs_cog()
            if logs:
                log_embed = moderation_embed(
                    "Verwarnung",
                    user,
                    interaction.user,
                    reason_text,
                    color=Config.COLOR_WARNING,
                )
                log_embed.add_field(name="Warn-ID", value=str(record.id), inline=True)
                log_embed.add_field(name="Gesamt", value=f"{count} Warnung(en)", inline=True)
                await logs.send_log(interaction.guild, log_embed)

            try:
                await user.send(embed=embed)
            except discord.Forbidden:
                pass

        except Exception as exc:
            logger.exception("Warn fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="unwarn", description="Entfernt eine Verwarnung anhand der ID.")
    @app_commands.describe(warning_id="ID der Verwarnung")
    @app_commands.default_permissions(moderate_members=True)
    @has_guild_permissions(moderate_members=True)
    @app_commands.checks.cooldown(1, Config.DEFAULT_COOLDOWN)
    async def unwarn(self, interaction: discord.Interaction, warning_id: int) -> None:
        """Entfernt eine Warnung."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return

            removed = await self.db.remove_warning(interaction.guild.id, warning_id)
            if removed:
                await interaction.followup.send(
                    embed=success_embed("Verwarnung entfernt", f"Warnung **#{warning_id}** wurde gelöscht."),
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    embed=error_embed("Nicht gefunden", f"Keine Warnung mit ID **{warning_id}**."),
                    ephemeral=True,
                )
        except Exception as exc:
            logger.exception("Unwarn fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="warnings", description="Zeigt alle Verwarnungen eines Mitglieds.")
    @app_commands.describe(user="Mitglied")
    @app_commands.default_permissions(moderate_members=True)
    @has_guild_permissions(moderate_members=True)
    async def warnings(self, interaction: discord.Interaction, user: discord.Member) -> None:
        """Listet Warnungen eines Users."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None:
                return

            records = await self.db.get_warnings(
                interaction.guild.id,
                user.id,
                limit=Config.MAX_WARNINGS_DISPLAY,
            )
            if not records:
                await interaction.followup.send(
                    embed=info_embed("Keine Warnungen", f"{user.mention} hat keine Verwarnungen."),
                    ephemeral=True,
                )
                return

            lines = []
            for w in records:
                mod = interaction.guild.get_member(w.moderator_id) or f"`{w.moderator_id}`"
                lines.append(f"**#{w.id}** • {w.created_at.strftime('%d.%m.%Y')} • {mod}\n> {w.reason}")

            embed = info_embed(
                f"Warnungen – {user.display_name}",
                f"Anzahl: **{len(records)}**",
                fields=[("Einträge", "\n\n".join(lines), False)],
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as exc:
            logger.exception("Warnings fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="clear", description="Löscht Nachrichten in einem Kanal.")
    @app_commands.describe(amount="Anzahl (1-100)", user="Optional: nur Nachrichten dieses Users")
    @app_commands.default_permissions(manage_messages=True)
    @has_guild_permissions(manage_messages=True)
    @app_commands.checks.cooldown(1, 5.0)
    async def clear(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100],
        user: discord.Member | None = None,
    ) -> None:
        """Bulk-Löschung von Nachrichten."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None or not isinstance(interaction.channel, discord.TextChannel):
                await interaction.followup.send(embed=error_embed("Fehler", "Nur in Textkanälen nutzbar."), ephemeral=True)
                return

            purge_kwargs: dict = {"limit": amount}
            if user is not None:
                purge_kwargs["check"] = lambda msg, uid=user.id: msg.author.id == uid
            deleted = await interaction.channel.purge(**purge_kwargs)
            await interaction.followup.send(
                embed=success_embed("Nachrichten gelöscht", f"**{len(deleted)}** Nachricht(en) entfernt."),
                ephemeral=True,
            )

            logs = self._get_logs_cog()
            if logs:
                from utils.embeds import log_event_embed

                embed = log_event_embed(
                    "Nachrichten gelöscht",
                    f"**{len(deleted)}** Nachricht(en) in {interaction.channel.mention}",
                    fields=[
                        ("Moderator", interaction.user.mention, True),
                        ("Kanal", interaction.channel.mention, True),
                    ],
                )
                await logs.send_log(interaction.guild, embed)

        except discord.Forbidden:
            await interaction.followup.send(embed=error_embed("Fehler", "Keine Berechtigung zum Löschen."), ephemeral=True)
        except Exception as exc:
            logger.exception("Clear fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="slowmode", description="Setzt Slowmode für den aktuellen Kanal.")
    @app_commands.describe(seconds="Sekunden (0 = aus, max 21600)")
    @app_commands.default_permissions(manage_channels=True)
    @has_guild_permissions(manage_channels=True)
    @app_commands.checks.cooldown(1, Config.DEFAULT_COOLDOWN)
    async def slowmode(
        self,
        interaction: discord.Interaction,
        seconds: app_commands.Range[int, 0, 21600],
    ) -> None:
        """Konfiguriert Kanal-Slowmode."""
        await interaction.response.defer(ephemeral=True)
        try:
            if not isinstance(interaction.channel, discord.TextChannel):
                await interaction.followup.send(embed=error_embed("Fehler", "Nur in Textkanälen."), ephemeral=True)
                return

            await interaction.channel.edit(slowmode_delay=seconds)
            if seconds == 0:
                msg = "Slowmode deaktiviert."
            else:
                msg = f"Slowmode auf **{seconds}** Sek. gesetzt."
            await interaction.followup.send(embed=success_embed("Slowmode", msg), ephemeral=True)

        except Exception as exc:
            logger.exception("Slowmode fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="lock", description="Sperrt den aktuellen Kanal für @everyone.")
    @app_commands.default_permissions(manage_channels=True)
    @has_guild_permissions(manage_channels=True)
    @app_commands.checks.cooldown(1, Config.DEFAULT_COOLDOWN)
    async def lock(self, interaction: discord.Interaction) -> None:
        """Sperrt einen Textkanal."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None or not isinstance(interaction.channel, discord.TextChannel):
                return

            overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
            overwrite.send_messages = False
            await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
            await interaction.followup.send(embed=success_embed("Kanal gesperrt", f"{interaction.channel.mention} ist gesperrt."), ephemeral=True)

        except Exception as exc:
            logger.exception("Lock fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="unlock", description="Entsperrt den aktuellen Kanal für @everyone.")
    @app_commands.default_permissions(manage_channels=True)
    @has_guild_permissions(manage_channels=True)
    @app_commands.checks.cooldown(1, Config.DEFAULT_COOLDOWN)
    async def unlock(self, interaction: discord.Interaction) -> None:
        """Entsperrt einen Textkanal."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None or not isinstance(interaction.channel, discord.TextChannel):
                return

            overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
            overwrite.send_messages = True
            await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
            await interaction.followup.send(embed=success_embed("Kanal entsperrt", f"{interaction.channel.mention} ist wieder offen."), ephemeral=True)

        except Exception as exc:
            logger.exception("Unlock fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="nickname", description="Ändert den Nickname eines Mitglieds.")
    @app_commands.describe(user="Mitglied", nickname="Neuer Nickname (leer = zurücksetzen)")
    @app_commands.default_permissions(manage_nicknames=True)
    @has_guild_permissions(manage_nicknames=True)
    @app_commands.checks.cooldown(1, Config.DEFAULT_COOLDOWN)
    async def nickname(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        nickname: str | None = None,
    ) -> None:
        """Setzt Nickname."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None or not isinstance(interaction.user, discord.Member):
                return

            allowed, msg = user_can_moderate(interaction.user, user)
            if not allowed:
                await interaction.followup.send(embed=error_embed("Fehler", msg), ephemeral=True)
                return

            await user.edit(nick=nickname or None, reason=f"Von {interaction.user}")
            display = nickname or user.name
            await interaction.followup.send(
                embed=success_embed("Nickname geändert", f"Nickname von {user.mention}: **{display}**"),
                ephemeral=True,
            )

        except Exception as exc:
            logger.exception("Nickname fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="mute", description="Mutet ein Mitglied (entzieht Sprech-/Schreibrechte).")
    @app_commands.describe(user="Mitglied", reason="Optionaler Grund")
    @app_commands.default_permissions(moderate_members=True)
    @has_guild_permissions(moderate_members=True)
    @app_commands.checks.cooldown(1, Config.DEFAULT_COOLDOWN)
    async def mute(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str | None = None,
    ) -> None:
        """Vergibt Mute-Rolle."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None or not isinstance(interaction.user, discord.Member):
                return

            allowed, msg = user_can_moderate(interaction.user, user)
            if not allowed:
                await interaction.followup.send(embed=error_embed("Fehler", msg), ephemeral=True)
                return

            role = await self._get_or_create_mute_role(interaction.guild)
            await user.add_roles(role, reason=reason or f"Mute von {interaction.user}")

            embed = moderation_embed("Mute", user, interaction.user, reason, color=Config.COLOR_WARNING)
            await interaction.followup.send(embed=success_embed("Gemutet", f"{user.mention} wurde gemutet."), ephemeral=True)

            logs = self._get_logs_cog()
            if logs:
                await logs.send_log(interaction.guild, embed)

        except Exception as exc:
            logger.exception("Mute fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)

    @app_commands.command(name="unmute", description="Hebt den Mute eines Mitglieds auf.")
    @app_commands.describe(user="Mitglied", reason="Optionaler Grund")
    @app_commands.default_permissions(moderate_members=True)
    @has_guild_permissions(moderate_members=True)
    @app_commands.checks.cooldown(1, Config.DEFAULT_COOLDOWN)
    async def unmute(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str | None = None,
    ) -> None:
        """Entfernt Mute-Rolle."""
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild is None or not isinstance(interaction.user, discord.Member):
                return

            allowed, msg = user_can_moderate(interaction.user, user)
            if not allowed:
                await interaction.followup.send(embed=error_embed("Moderation fehlgeschlagen", msg), ephemeral=True)
                return

            settings = await self.db.get_guild_settings(interaction.guild.id)
            if not settings.mute_role_id:
                await interaction.followup.send(embed=error_embed("Fehler", "Keine Mute-Rolle konfiguriert."), ephemeral=True)
                return

            role = interaction.guild.get_role(settings.mute_role_id)
            if role and role in user.roles:
                await user.remove_roles(role, reason=reason or f"Unmute von {interaction.user}")

            embed = moderation_embed("Unmute", user, interaction.user, reason)
            await interaction.followup.send(embed=success_embed("Unmute", f"{user.mention} kann wieder schreiben."), ephemeral=True)

            logs = self._get_logs_cog()
            if logs:
                await logs.send_log(interaction.guild, embed)

        except Exception as exc:
            logger.exception("Unmute fehlgeschlagen: %s", exc)
            await interaction.followup.send(embed=error_embed("Fehler", str(exc)), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Lädt den Moderation-Cog."""
    db: Database = bot.db  # type: ignore[attr-defined]
    await bot.add_cog(ModerationCog(bot, db))
