"""
Dungeon-Cog: Pet-Dungeons mit einfachem Raum-Ablauf.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from config import Config
from database.database import Database
from database.models import DungeonRunRecord, DungeonRunStatus
from utils.dungeon_embeds import (
    build_finished_embed,
    build_resume_embed,
    build_room_result_embed,
    build_start_embed,
    format_hp_bar,
)
from utils.dungeons import (
    apply_hp_regen,
    dungeon_cooldown_remaining,
    event_preview,
    finalize_run,
    generate_events,
    pet_hp_max,
    pet_in_recovery,
    player_hp_max,
    resolve_room,
)
from utils.embeds import error_embed, info_embed, success_embed, warning_embed

logger = logging.getLogger(__name__)


class DungeonContinueView(discord.ui.View):
    """Ein Button: Raum betreten / auflösen."""

    def __init__(self, cog: "DungeonsCog", run_id: int, owner_id: int) -> None:
        super().__init__(timeout=Config.DUNGEON_VIEW_TIMEOUT)
        self.cog = cog
        self.run_id = run_id
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                embed=error_embed("Nicht dein Dungeon", "Nur du kannst hier weitermachen."),
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Weiter", style=discord.ButtonStyle.primary, emoji="🚪")
    async def continue_room(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[discord.ui.View],
    ) -> None:
        await self.cog._advance_run(interaction, self.run_id)


class DungeonStatusView(discord.ui.View):
    """Status: Heilen oder Dungeon fortsetzen."""

    def __init__(
        self,
        cog: "DungeonsCog",
        owner_id: int,
        *,
        run_id: int | None = None,
        can_heal: bool = False,
    ) -> None:
        super().__init__(timeout=Config.DUNGEON_VIEW_TIMEOUT)
        self.cog = cog
        self.owner_id = owner_id
        self.run_id = run_id
        if can_heal:
            heal_btn = discord.ui.Button(
                label=f"Heilen ({Config.DUNGEON_HEAL_GOLD_COST} Gold)",
                style=discord.ButtonStyle.secondary,
                emoji="💊",
            )
            heal_btn.callback = self._heal_callback
            self.add_item(heal_btn)
        if run_id is not None:
            cont_btn = discord.ui.Button(label="Weiter", style=discord.ButtonStyle.primary, emoji="🚪")
            cont_btn.callback = self._continue_callback
            self.add_item(cont_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                embed=error_embed("Nicht dein Profil", "Das ist nicht dein Dungeon-Status."),
                ephemeral=True,
            )
            return False
        return True

    async def _heal_callback(self, interaction: discord.Interaction) -> None:
        await self.cog._heal(interaction, self.run_id)

    async def _continue_callback(self, interaction: discord.Interaction) -> None:
        if self.run_id is not None:
            await self.cog._advance_run(interaction, self.run_id)


class DungeonsCog(commands.GroupCog, group_name="dungeon", group_description="Pet-Dungeons erkunden"):
    """Einfache Dungeons mit aktivem Pet — getrennt vom Lootbox-System."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db

    async def cog_load(self) -> None:
        await self.db.abandon_stale_dungeon_runs(Config.DUNGEON_RUN_TIMEOUT)

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.CheckFailure):
            return
        logger.exception("Dungeon-Befehl Fehler: %s", error)
        embed = error_embed("Dungeon-Befehl fehlgeschlagen", str(error))
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass

    def _channel(self, interaction: discord.Interaction) -> discord.TextChannel | discord.Thread | None:
        if isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
            return interaction.channel
        return None

    async def _prepare_economy(self, guild_id: int, user_id: int, level: int):
        economy = await self.db.get_player_economy(guild_id, user_id)
        hp_max = player_hp_max(level)
        economy = apply_hp_regen(economy, hp_max)
        return economy, hp_max

    def _status_embed(
        self,
        member: discord.Member,
        economy,
        hp_max: int,
        *,
        run=None,
        pet=None,
        cooldown: int | None = None,
        recovery: int | None = None,
    ) -> discord.Embed:
        if run and pet:
            player_hp = run.player_hp
            player_max = run.player_hp_max
            pet_hp_text = format_hp_bar(run.pet_hp, run.pet_hp_max)
        else:
            player_hp = economy.player_hp
            player_max = hp_max
            pet_hp_text = "—"

        lines = [
            f"🪙 **Gold:** {economy.gold:,}",
            f"❤️ **Dungeon-HP:** {format_hp_bar(player_hp, player_max)}",
            f"🏆 **Dungeons:** {economy.dungeons_completed} abgeschlossen",
        ]
        if cooldown:
            lines.append(f"⏳ **Cooldown:** {cooldown // 60}:{cooldown % 60:02d}")
        if recovery and pet:
            lines.append(f"😴 **{pet.name}** erholt sich (~{recovery // 60} Min.)")
        if run and pet:
            lines.append(f"🗺️ **Aktiv:** Raum {run.current_room + 1}/{run.total_rooms} · Session **{run.session_gold}** Gold")

        embed = info_embed(f"Abenteuer — {member.display_name}", "\n".join(lines))
        if run and pet:
            embed.add_field(name=f"🐾 {pet.name}", value=pet_hp_text, inline=True)
        embed.set_footer(text="Lootboxen sind separat — Gold hier nur für Dungeons & Heilung")
        return embed

    async def _heal(self, interaction: discord.Interaction, run_id: int | None) -> None:
        assert interaction.guild is not None
        if not isinstance(interaction.user, discord.Member):
            return

        level = (await self.db.get_user_level(interaction.guild.id, interaction.user.id)).level
        economy, hp_max = await self._prepare_economy(
            interaction.guild.id, interaction.user.id, level
        )

        if economy.gold < Config.DUNGEON_HEAL_GOLD_COST:
            await interaction.response.send_message(
                embed=error_embed(
                    "Nicht genug Gold",
                    f"Heilung kostet **{Config.DUNGEON_HEAL_GOLD_COST}** 🪙 — sammle Gold in Dungeons oder Spielen.",
                ),
                ephemeral=True,
            )
            return

        run = await self.db.get_active_dungeon_run(interaction.guild.id, interaction.user.id)

        if run and run.status == DungeonRunStatus.ACTIVE.value:
            if run.player_hp >= run.player_hp_max and run.pet_hp >= run.pet_hp_max:
                await interaction.response.send_message(
                    embed=info_embed("Schon fit", "Du und dein Pet habt volle HP."),
                    ephemeral=True,
                )
                return
            economy.gold -= Config.DUNGEON_HEAL_GOLD_COST
            run.player_hp = run.player_hp_max
            run.pet_hp = run.pet_hp_max
            run.updated_at = datetime.now(timezone.utc)
            await self.db.save_dungeon_run(run)
            await self.db.save_player_economy(economy)
            pet = await self.db.get_pet(run.pet_id)
            if pet is None:
                await interaction.response.send_message(
                    embed=error_embed("Fehler", "Pet nicht gefunden."),
                    ephemeral=True,
                )
                return
            title, desc = event_preview(run.events[run.current_room], run.current_room, run.total_rooms)
            embed = build_start_embed(
                run,
                pet,
                title=title,
                description=f"**Geheilt!** Ihr seid wieder fit.\n\n_{desc}_\n\nKlicke **Weiter**.",
            )
            view = DungeonContinueView(self, run.id, interaction.user.id)
            if interaction.message:
                await interaction.response.edit_message(embed=embed, view=view)
            else:
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            return

        if economy.player_hp >= hp_max:
            await interaction.response.send_message(
                embed=info_embed("Schon fit", "Deine Dungeon-HP sind voll."),
                ephemeral=True,
            )
            return

        economy.gold -= Config.DUNGEON_HEAL_GOLD_COST
        economy.player_hp = hp_max
        economy.last_hp_regen_at = datetime.now(timezone.utc)
        await self.db.save_player_economy(economy)

        await interaction.response.send_message(
            embed=success_embed(
                "Geheilt",
                f"Volle HP (**{hp_max}**). Übrig: **{economy.gold:,}** 🪙",
            ),
            ephemeral=True,
        )

    async def _advance_run(self, interaction: discord.Interaction, run_id: int) -> None:
        assert interaction.guild is not None
        if not isinstance(interaction.user, discord.Member):
            return

        run = await self.db.get_dungeon_run(run_id)
        if run is None or run.status != DungeonRunStatus.ACTIVE.value:
            await interaction.response.send_message(
                embed=error_embed("Kein aktiver Run", "Starte mit `/dungeon start`."),
                ephemeral=True,
            )
            return
        if run.user_id != interaction.user.id or run.guild_id != interaction.guild.id:
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Das ist nicht dein Dungeon."),
                ephemeral=True,
            )
            return

        pet = await self.db.get_pet(run.pet_id)
        if pet is None:
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Pet nicht gefunden."),
                ephemeral=True,
            )
            return

        if not interaction.response.is_done():
            await interaction.response.defer()

        pet_xp_pending: list[int] = []
        outcome = resolve_room(run, pet_xp_callback=pet_xp_pending)
        run.updated_at = datetime.now(timezone.utc)

        level = (await self.db.get_user_level(interaction.guild.id, interaction.user.id)).level
        economy, hp_max = await self._prepare_economy(
            interaction.guild.id, interaction.user.id, level
        )
        channel = self._channel(interaction)

        if outcome.failed or outcome.completed:
            await finalize_run(
                self.db,
                self.bot,
                interaction.user,
                run,
                economy,
                outcome=outcome,
                player_hp_max_value=hp_max,
                channel=channel,
                pet_xp_pending=pet_xp_pending,
            )
            embed = build_finished_embed(
                run,
                pet,
                outcome.text,
                gold_received=run.session_gold,
                completed=outcome.completed,
            )
            await interaction.edit_original_response(embed=embed, view=None)
            return

        await self.db.save_dungeon_run(run)
        for xp in pet_xp_pending:
            from utils.pet_rewards import award_pet_xp

            await award_pet_xp(
                self.bot,
                interaction.user,
                xp,
                channel=channel,
                count_interaction=False,
                announce_evolution=True,
            )

        embed = build_room_result_embed(run, pet, outcome.text, last_event=outcome.event_type)
        await interaction.edit_original_response(
            embed=embed,
            view=DungeonContinueView(self, run.id, interaction.user.id),
        )

    @app_commands.command(name="start", description="Startet einen Dungeon mit deinem aktiven Pet")
    @app_commands.guild_only()
    async def start(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Nur Server-Mitglieder können Dungeons spielen."),
                ephemeral=True,
            )
            return

        active = await self.db.get_active_dungeon_run(interaction.guild.id, interaction.user.id)
        if active is not None:
            pet = await self.db.get_pet(active.pet_id)
            if pet:
                await interaction.response.send_message(
                    embed=build_resume_embed(active, pet),
                    view=DungeonContinueView(self, active.id, interaction.user.id),
                    ephemeral=True,
                )
                return

        pet = await self.db.get_active_pet(interaction.guild.id, interaction.user.id)
        if pet is None:
            await interaction.response.send_message(
                embed=error_embed("Kein aktives Pet", "Wähle zuerst ein Pet mit `/pets`."),
                ephemeral=True,
            )
            return

        level = (await self.db.get_user_level(interaction.guild.id, interaction.user.id)).level
        economy, hp_max = await self._prepare_economy(
            interaction.guild.id, interaction.user.id, level
        )

        recovery = pet_in_recovery(economy, pet.id)
        if recovery is not None:
            await interaction.response.send_message(
                embed=warning_embed(
                    "Pet erholt sich",
                    f"**{pet.name}** braucht noch ~**{max(1, recovery // 60)}** Min.\n"
                    "Kein Tod — nur eine kurze Pause.",
                ),
                ephemeral=True,
            )
            return

        cooldown = dungeon_cooldown_remaining(economy)
        if cooldown is not None:
            await interaction.response.send_message(
                embed=warning_embed(
                    "Kurz Pause",
                    f"Nächster Dungeon in **{cooldown // 60}:{cooldown % 60:02d}**.",
                ),
                ephemeral=True,
            )
            return

        if economy.player_hp <= 0:
            await interaction.response.send_message(
                embed=error_embed(
                    "Keine HP",
                    f"Heile dich über `/dungeon status` (**{Config.DUNGEON_HEAL_GOLD_COST}** Gold) "
                    "oder warte auf Regeneration.",
                ),
                ephemeral=True,
            )
            return

        now = datetime.now(timezone.utc)
        events = generate_events()
        p_max = pet_hp_max(pet)
        run = DungeonRunRecord(
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            pet_id=pet.id,
            status=DungeonRunStatus.ACTIVE.value,
            current_room=0,
            total_rooms=len(events),
            player_hp=economy.player_hp,
            player_hp_max=hp_max,
            pet_hp=p_max,
            pet_hp_max=p_max,
            events=events,
            started_at=now,
            updated_at=now,
        )
        run = await self.db.save_dungeon_run(run)

        title, desc = event_preview(events[0], 0, len(events))
        embed = build_start_embed(
            run,
            pet,
            title=title,
            description=f"_{desc}_\n\nDu und **{pet.name}** betreten den Dungeon.\nKlicke **Weiter**!",
        )

        await interaction.response.send_message(
            embed=embed,
            view=DungeonContinueView(self, run.id, interaction.user.id),
            ephemeral=True,
        )

    @app_commands.command(name="status", description="Gold, HP und aktuellen Dungeon anzeigen")
    @app_commands.guild_only()
    async def status(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        if not isinstance(interaction.user, discord.Member):
            return

        level = (await self.db.get_user_level(interaction.guild.id, interaction.user.id)).level
        economy, hp_max = await self._prepare_economy(
            interaction.guild.id, interaction.user.id, level
        )
        await self.db.save_player_economy(economy)

        run = await self.db.get_active_dungeon_run(interaction.guild.id, interaction.user.id)
        pet = await self.db.get_active_pet(interaction.guild.id, interaction.user.id)
        run_pet = await self.db.get_pet(run.pet_id) if run else pet

        cooldown = dungeon_cooldown_remaining(economy)
        recovery = pet_in_recovery(economy, pet.id) if pet else None

        can_heal = False
        if run:
            can_heal = run.player_hp < run.player_hp_max or run.pet_hp < run.pet_hp_max
        else:
            can_heal = economy.player_hp < hp_max

        heal_ok = can_heal and economy.gold >= Config.DUNGEON_HEAL_GOLD_COST

        embed = self._status_embed(
            interaction.user,
            economy,
            hp_max,
            run=run,
            pet=run_pet,
            cooldown=cooldown,
            recovery=recovery,
        )

        view = None
        if run and run_pet:
            view = DungeonStatusView(self, interaction.user.id, run_id=run.id, can_heal=heal_ok)
        elif heal_ok:
            view = DungeonStatusView(self, interaction.user.id, can_heal=True)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    db: Database = bot.db  # type: ignore[attr-defined]
    await bot.add_cog(DungeonsCog(bot, db))
