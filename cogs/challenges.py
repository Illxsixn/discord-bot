"""
Tägliche XP-Aufgaben mit automatischem Reset und Fortschritts-Tracking.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from config import Config
from database.database import Database
from database.models import ChallengeTask, ChallengeType, DailyChallengeRecord, is_pet_challenge_type
from utils.challenges import (
    format_challenge_task_line,
    generate_daily_challenges,
    normalize_daily_challenges,
    today_utc,
)
from utils.embeds import info_embed, spaced_lines
from utils.pet_rewards import award_pet_xp

logger = logging.getLogger(__name__)


class ChallengesCog(commands.Cog):
    """Tägliche Aufgaben für Bonus-XP."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db

    async def _ensure_today(self, guild_id: int, user_id: int) -> DailyChallengeRecord:
        """Lädt oder erzeugt die heutigen Aufgaben."""
        record = await self.db.get_daily_challenges(guild_id, user_id)
        if record is None or record.challenge_date != today_utc():
            record = generate_daily_challenges(guild_id, user_id)
            await self.db.save_daily_challenges(record)
            return record

        changed, record = normalize_daily_challenges(record)
        if changed:
            await self.db.save_daily_challenges(record)
        return record

    async def _complete_task(
        self,
        member: discord.Member,
        task: ChallengeTask,
        *,
        channel: discord.TextChannel | discord.Thread | None = None,
    ) -> bool:
        """Markiert Aufgabe als erledigt und vergibt XP."""
        if task.completed:
            return False
        task.completed = True
        task.progress = task.target
        levels = self.bot.get_cog("LevelsCog")
        if levels is not None and task.reward_xp > 0:
            await levels.award_xp(member, task.reward_xp, channel=channel)  # type: ignore[attr-defined]
        if task.reward_pet_xp > 0:
            await award_pet_xp(
                self.bot,
                member,
                task.reward_pet_xp,
                channel=channel,
                count_interaction=False,
                announce_evolution=True,
            )
        return True

    async def track_pet_play(
        self,
        member: discord.Member,
        *,
        channel: discord.TextChannel | discord.Thread | None = None,
    ) -> None:
        """Zählt abgeschlossene /pet-play-Runden."""
        await self._increment_task(
            member.guild.id,
            member.id,
            ChallengeType.PET_PLAY,
            member=member,
            channel=channel,
        )

    async def track_pet_info(
        self,
        member: discord.Member,
        *,
        channel: discord.TextChannel | discord.Thread | None = None,
    ) -> None:
        """Zählt /pet-info-Aufrufe."""
        await self._increment_task(
            member.guild.id,
            member.id,
            ChallengeType.PET_INFO,
            member=member,
            channel=channel,
        )

    async def track_pet_activity(
        self,
        member: discord.Member,
        *,
        channel: discord.TextChannel | discord.Thread | None = None,
    ) -> None:
        """Zählt vergebenes Pet-Aktivitäts-XP."""
        await self._increment_task(
            member.guild.id,
            member.id,
            ChallengeType.PET_ACTIVITY,
            member=member,
            channel=channel,
        )

    async def _increment_task(
        self,
        guild_id: int,
        user_id: int,
        challenge_type: ChallengeType,
        *,
        amount: int = 1,
        member: discord.Member | None = None,
        channel: discord.TextChannel | discord.Thread | None = None,
    ) -> None:
        """Erhöht Fortschritt einer Aufgabe und schließt sie bei Erreichen des Ziels ab."""
        record = await self._ensure_today(guild_id, user_id)
        changed = False
        for task in record.challenges:
            if task.type != challenge_type or task.completed:
                continue
            task.progress = min(task.target, task.progress + amount)
            if task.progress >= task.target and member is not None:
                await self._complete_task(member, task, channel=channel)
            changed = True
        if changed:
            await self.db.save_daily_challenges(record)

    @app_commands.command(name="daily-challenges", description="Zeigt deine täglichen Level- und Pet-Aufgaben.")
    @app_commands.guild_only()
    async def daily_challenges(self, interaction: discord.Interaction) -> None:
        """Zeigt aktive Tagesaufgaben."""
        await interaction.response.defer(ephemeral=True)
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return

        record = await self._ensure_today(interaction.guild.id, interaction.user.id)
        level_tasks = [task for task in record.challenges if not is_pet_challenge_type(task.type)]
        pet_tasks = [task for task in record.challenges if is_pet_challenge_type(task.type)]

        level_lines = [format_challenge_task_line(index, task) for index, task in enumerate(level_tasks, start=1)]
        pet_lines = [format_challenge_task_line(index, task) for index, task in enumerate(pet_tasks, start=1)]
        completed = sum(1 for task in record.challenges if task.completed)

        fields: list[tuple[str, str, bool]] = []
        for index, line in enumerate(level_lines, start=1):
            fields.append((f"🎮 Level · Aufgabe {index}", line, False))
        for index, line in enumerate(pet_lines, start=1):
            fields.append((f"🐾 Pet · Aufgabe {index}", line, False))

        embed = info_embed(
            "📅 Tägliche Aufgaben",
            spaced_lines(
                f"**Datum:** {record.challenge_date} (UTC)",
                f"**Fortschritt:** {completed}/{len(record.challenges)} erledigt",
            ),
            fields=fields,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Zählt Nachrichten für Aufgaben."""
        if message.author.bot or message.guild is None or not isinstance(message.author, discord.Member):
            return
        try:
            await self._increment_task(
                message.guild.id,
                message.author.id,
                ChallengeType.MESSAGES,
                member=message.author,
                channel=message.channel if isinstance(message.channel, (discord.TextChannel, discord.Thread)) else None,
            )
            await self._increment_task(
                message.guild.id,
                message.author.id,
                ChallengeType.ACTIVE,
                amount=1,
                member=message.author,
                channel=message.channel if isinstance(message.channel, (discord.TextChannel, discord.Thread)) else None,
            )
        except Exception as exc:
            logger.exception("Challenge Nachrichten-Tracking fehlgeschlagen: %s", exc)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """Zählt Reaktionen für Aufgaben."""
        if payload.guild_id is None or payload.user_id is None or payload.member and payload.member.bot:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        member = guild.get_member(payload.user_id)
        if member is None or member.bot:
            return
        try:
            await self._increment_task(payload.guild_id, payload.user_id, ChallengeType.REACTIONS, member=member)
        except Exception as exc:
            logger.exception("Challenge Reaktions-Tracking fehlgeschlagen: %s", exc)

    @commands.Cog.listener()
    async def on_app_command_completion(
        self,
        interaction: discord.Interaction,
        command: app_commands.Command,
    ) -> None:
        """Zählt genutzte Bot-Befehle für Aufgaben."""
        if interaction.guild is None or interaction.user is None or interaction.user.bot:
            return
        if not isinstance(interaction.user, discord.Member):
            return
        if command.name == "daily-challenges":
            return
        try:
            channel = interaction.channel if isinstance(interaction.channel, (discord.TextChannel, discord.Thread)) else None
            await self._increment_task(
                interaction.guild.id,
                interaction.user.id,
                ChallengeType.COMMANDS,
                member=interaction.user,
                channel=channel,
            )
        except Exception as exc:
            logger.exception("Challenge Befehls-Tracking fehlgeschlagen: %s", exc)


async def setup(bot: commands.Bot) -> None:
    """Lädt tägliche Aufgaben."""
    db: Database = bot.db  # type: ignore[attr-defined]
    await bot.add_cog(ChallengesCog(bot, db))
