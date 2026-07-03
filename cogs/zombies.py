"""
Zombie Survival Cog: Wellen, Kampf, Shop und Profil.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from config import Config
from database.database import Database
from database.models import (
    ZombieCooldownType,
    ZombieRunRecord,
    ZombieRunStatus,
)
from utils.embeds import error_embed, info_embed, spaced_lines, warning_embed
from utils.game_locks import game_lock
from utils.game_gates import is_zombie_mode_active
from utils.pet_play import PET_IMPULSES
from utils.zombie_assets import attach_zombie_visual
from utils.zombie_combat import (
    advance_to_next_wave,
    perform_melee,
    perform_pet_action,
    spawn_wave,
)
from utils.zombie_content import get_zombie, player_max_hp
from utils.zombie_embeds import (
    build_between_waves_embed,
    build_defeat_embed,
    build_expired_embed,
    build_help_embed,
    build_idle_status_embed,
    build_interface_embed,
    build_pet_impulse_embed,
    build_profile_embed,
    build_run_embed,
    build_victory_embed,
)
from utils.zombie_rewards import finalize_expired_run, finalize_zombie_run, zombie_cooldown_remaining

logger = logging.getLogger(__name__)


class ZombieInterfaceView(discord.ui.View):
    """Steuerzentrale mit Schnellbuttons."""

    def __init__(self, cog: "ZombiesCog", owner_id: int) -> None:
        super().__init__(timeout=180.0)
        self.cog = cog
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                embed=error_embed("Nicht dein Interface", "Das ist nicht deine Steuerzentrale."),
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Shop", style=discord.ButtonStyle.secondary, emoji="🏪")
    async def open_shop(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[discord.ui.View],
    ) -> None:
        shop_cog = self.cog.bot.get_cog("ShopCog")
        if shop_cog is None:
            await interaction.response.send_message(
                embed=info_embed("Shop", "Nutze **`/shop`** für Lootboxen und Produkte."),
                ephemeral=True,
            )
            return
        await shop_cog.send_shop(interaction)  # type: ignore[attr-defined]

    @discord.ui.button(label="Profil", style=discord.ButtonStyle.secondary, emoji="📊")
    async def open_profile(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[discord.ui.View],
    ) -> None:
        await self.cog._send_profile(interaction)

    @discord.ui.button(label="Status", style=discord.ButtonStyle.primary, emoji="🧟")
    async def open_status(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[discord.ui.View],
    ) -> None:
        await self.cog._send_status(interaction)


class ZombiePetImpulseView(discord.ui.View):
    """Separates Fenster: Impuls-Auswahl für den Pet-Bonusangriff."""

    def __init__(self, cog: "ZombiesCog", run_id: int, owner_id: int) -> None:
        super().__init__(timeout=60.0)
        self.cog = cog
        self.run_id = run_id
        self.owner_id = owner_id
        for impulse_id, emoji, label in PET_IMPULSES:
            button = discord.ui.Button(
                label=label,
                emoji=emoji,
                style=discord.ButtonStyle.secondary,
            )
            button.callback = self._make_callback(impulse_id)
            self.add_item(button)

    def _make_callback(self, impulse_id: str):
        async def callback(interaction: discord.Interaction) -> None:
            await self.cog._handle_pet_impulse(interaction, self.run_id, impulse_id)

        return callback

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                embed=error_embed("Nicht dein Run", "Das ist nicht dein Run."),
                ephemeral=True,
            )
            return False
        return True


class ZombieRunView(discord.ui.View):
    """Persistente Run-Buttons — Zustand kommt aus der DB."""

    def __init__(
        self,
        cog: "ZombiesCog",
        run_id: int,
        owner_id: int,
        *,
        has_pet: bool = True,
        pet_on_cooldown: bool = False,
        include_legacy_shop: bool = False,
    ) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.run_id = run_id
        self.owner_id = owner_id

        melee = discord.ui.Button(
            label="Nahkampf",
            style=discord.ButtonStyle.danger,
            emoji="🗡️",
            custom_id=f"zombies:melee:{run_id}",
        )
        melee.callback = self._melee_callback
        self.add_item(melee)

        pet_btn = discord.ui.Button(
            label="Pet-Angriff",
            style=discord.ButtonStyle.primary,
            emoji="🐾",
            custom_id=f"zombies:pet:{run_id}",
            disabled=not has_pet or pet_on_cooldown,
        )
        pet_btn.callback = self._pet_callback
        self.add_item(pet_btn)

        nxt = discord.ui.Button(
            label="Nächste Welle",
            style=discord.ButtonStyle.success,
            emoji="➡️",
            custom_id=f"zombies:next_wave:{run_id}",
        )
        nxt.callback = self._next_wave_callback
        self.add_item(nxt)

        pause = discord.ui.Button(
            label="Wellenpause",
            style=discord.ButtonStyle.secondary,
            emoji="⏸️",
            custom_id=f"zombies:pause:{run_id}",
        )
        pause.callback = self._pause_callback
        self.add_item(pause)

        if include_legacy_shop:
            legacy = discord.ui.Button(
                label="Wellenpause",
                style=discord.ButtonStyle.secondary,
                emoji="⏸️",
                custom_id=f"zombies:shop:{run_id}",
            )
            legacy.callback = self._pause_callback
            self.add_item(legacy)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                embed=error_embed("Nicht dein Run", "Das ist nicht dein Run."),
                ephemeral=True,
            )
            return False
        return True

    async def _melee_callback(self, interaction: discord.Interaction) -> None:
        await self.cog._handle_run_action(interaction, self.run_id, "melee")

    async def _pet_callback(self, interaction: discord.Interaction) -> None:
        await self.cog._open_pet_impulse_window(interaction, self.run_id)

    async def _next_wave_callback(self, interaction: discord.Interaction) -> None:
        await self.cog._handle_run_action(interaction, self.run_id, "next_wave")

    async def _pause_callback(self, interaction: discord.Interaction) -> None:
        await self.cog._handle_run_action(interaction, self.run_id, "pause")


class ZombiesCog(commands.GroupCog, group_name="zombies", group_description="Zombie Survival — Wellen, Gold & Pets"):
    """Zombie Survival RPG — kein Abbrechen, persistenter Run-Zustand."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db

    async def _ensure_zombie_mode(self, interaction: discord.Interaction) -> bool:
        """Prüft, ob Zombie Survival über das Level-System freigeschaltet ist."""
        assert interaction.guild is not None
        if await is_zombie_mode_active(self.db, interaction.guild.id):
            return True
        embed = error_embed(
            "Zombie-Modus inaktiv",
            spaced_lines(
                "Zombie Survival ist an das **Level-System** gekoppelt.",
                "Ein Admin aktiviert beides mit **`/levels enable`**.",
            ),
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
        return False

    async def cog_load(self) -> None:
        stale = await self.db.get_stale_active_zombie_runs(Config.ZOMBIE_RUN_INACTIVITY)
        if stale:
            logger.info("%d Zombie-Run(s) wegen Inaktivität abgelaufen.", len(stale))
        for run in stale:
            await self._finalize_stale_run(run)
        for run in await self.db.get_all_active_zombie_runs():
            if run.message_id:
                view = await self._build_persistent_run_view(run)
                self.bot.add_view(view, message_id=run.message_id)

    async def _finalize_stale_run(self, run: ZombieRunRecord) -> None:
        """Schließt inaktive Runs beim Start ab — inkl. Trostbelohnung."""
        profile = await self.db.get_zombie_player(run.guild_id, run.user_id)
        member: discord.Member | None = None
        guild = self.bot.get_guild(run.guild_id)
        if guild is not None:
            member = guild.get_member(run.user_id)
            if member is None:
                try:
                    member = await guild.fetch_member(run.user_id)
                except (discord.NotFound, discord.HTTPException):
                    member = None
        await finalize_expired_run(self.db, self.bot, run, profile, member=member)

    async def _build_persistent_run_view(self, run: ZombieRunRecord) -> ZombieRunView:
        """View für persistente Nachrichten nach Bot-Neustart."""
        pet = await self.db.get_active_pet(run.guild_id, run.user_id)
        return ZombieRunView(
            self,
            run.id,
            run.user_id,
            has_pet=pet is not None,
            pet_on_cooldown=run.pet_action_cooldown > 0,
            include_legacy_shop=True,
        )

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.CheckFailure):
            return
        logger.exception("Zombie-Befehl Fehler: %s", error)
        embed = error_embed("Zombie-Befehl fehlgeschlagen", str(error))
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

    async def _get_cooldown(self, guild_id: int, user_id: int) -> int | None:
        expires = await self.db.get_zombie_cooldown(guild_id, user_id, ZombieCooldownType.RUN.value)
        return zombie_cooldown_remaining(expires)

    async def _check_expired_run(
        self,
        member: discord.Member,
        run: ZombieRunRecord,
    ) -> ZombieRunRecord | None:
        """Prüft 12h-Inaktivität und markiert Run als abgelaufen."""
        elapsed = (datetime.now(timezone.utc) - run.updated_at).total_seconds()
        if elapsed < Config.ZOMBIE_RUN_INACTIVITY:
            return run
        profile = await self.db.get_zombie_player(member.guild.id, member.id)
        await finalize_expired_run(self.db, self.bot, run, profile, member=member)
        return None

    async def _build_run_message(
        self,
        member: discord.Member,
        run: ZombieRunRecord,
    ) -> tuple[discord.Embed, discord.File | None, ZombieRunView]:
        profile = await self.db.get_zombie_player(member.guild.id, member.id)
        economy = await self.db.get_player_economy(member.guild.id, member.id)
        level = (await self.db.get_user_level(member.guild.id, member.id)).level
        pet = await self.db.get_active_pet(member.guild.id, member.id)

        embed = build_run_embed(
            run,
            pet=pet,
            economy=economy,
            player_level=level,
        )
        file: discord.File | None = None
        if run.in_combat and run.current_zombie_key:
            zombie = get_zombie(run.current_zombie_key)
            if zombie:
                file = attach_zombie_visual(embed, run.current_zombie_key, is_boss=zombie.is_boss)

        view = ZombieRunView(
            self,
            run.id,
            member.id,
            has_pet=pet is not None,
            pet_on_cooldown=run.pet_action_cooldown > 0,
        )
        return embed, file, view

    async def _refresh_stored_run_message(
        self,
        run: ZombieRunRecord,
        member: discord.Member,
        *,
        final_embed: discord.Embed | None = None,
    ) -> None:
        """Aktualisiert die gespeicherte Run-Nachricht (Haupt-Kampf-Embed)."""
        if not run.message_id or not run.channel_id:
            return
        guild = self.bot.get_guild(run.guild_id)
        if guild is None:
            return
        channel = guild.get_channel(run.channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        try:
            message = await channel.fetch_message(run.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
            logger.warning("Run-Nachricht %s nicht ladbar: %s", run.message_id, exc)
            return

        if final_embed is not None:
            try:
                await message.edit(embed=final_embed, view=None, attachments=[])
            except (discord.NotFound, discord.HTTPException) as exc:
                logger.warning("Run-Abschluss-Update fehlgeschlagen: %s", exc)
            return

        embed, file, view = await self._build_run_message(member, run)
        try:
            if file:
                await message.edit(embed=embed, view=view, attachments=[file])
            else:
                await message.edit(embed=embed, view=view, attachments=[])
            self.bot.add_view(view, message_id=message.id)
        except (discord.NotFound, discord.HTTPException) as exc:
            logger.warning("Run-Nachricht Refresh fehlgeschlagen: %s", exc)

    async def _update_run_message(
        self,
        interaction: discord.Interaction,
        run: ZombieRunRecord,
        member: discord.Member,
        *,
        final_embed: discord.Embed | None = None,
    ) -> None:
        channel = self._channel(interaction)
        if final_embed is not None:
            try:
                if interaction.response.is_done():
                    await interaction.edit_original_response(embed=final_embed, view=None, attachments=[])
                elif interaction.message:
                    await interaction.response.edit_message(embed=final_embed, view=None, attachments=[])
                else:
                    await interaction.response.send_message(embed=final_embed, ephemeral=True)
            except (discord.NotFound, discord.HTTPException):
                if channel:
                    await channel.send(embed=final_embed)
            return

        embed, file, view = await self._build_run_message(member, run)
        kwargs: dict = {"embed": embed, "view": view}
        if file:
            kwargs["file"] = file

        try:
            if interaction.response.is_done():
                if file:
                    await interaction.edit_original_response(embed=embed, view=view, attachments=[file])
                else:
                    await interaction.edit_original_response(embed=embed, view=view, attachments=[])
            elif interaction.message:
                if file:
                    await interaction.response.edit_message(embed=embed, view=view, attachments=[file])
                else:
                    await interaction.response.edit_message(embed=embed, view=view, attachments=[])
            else:
                msg = await interaction.response.send_message(**kwargs, ephemeral=True)
                if run.id and interaction.guild:
                    saved = await self.db.get_zombie_run(run.id)
                    if saved:
                        saved.channel_id = channel.id if channel else None
                        if isinstance(msg, discord.InteractionCallbackResponse):
                            pass
                        elif hasattr(msg, "id"):
                            saved.message_id = msg.id
                        await self.db.save_zombie_run(saved)
                        self.bot.add_view(view, message_id=saved.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
            logger.warning("Run-Nachricht Update fehlgeschlagen: %s", exc)
            if channel:
                sent = await channel.send(**kwargs)
                run.channel_id = channel.id
                run.message_id = sent.id
                await self.db.save_zombie_run(run)
                self.bot.add_view(view, message_id=sent.id)

    async def _handle_run_action(
        self,
        interaction: discord.Interaction,
        run_id: int,
        action: str,
    ) -> None:
        assert interaction.guild is not None
        if not isinstance(interaction.user, discord.Member):
            return
        if not await self._ensure_zombie_mode(interaction):
            return

        if action == "shop":
            action = "pause"

        async with game_lock(run_id):
            run = await self.db.get_zombie_run(run_id)
            if run is None or run.status != ZombieRunStatus.ACTIVE.value:
                await interaction.response.send_message(
                    embed=error_embed("Kein aktiver Run", "Starte mit `/zombies start`."),
                    ephemeral=True,
                )
                return
            if run.user_id != interaction.user.id:
                await interaction.response.send_message(
                    embed=error_embed("Nicht dein Run", "Das ist nicht dein Run."),
                    ephemeral=True,
                )
                return

            checked = await self._check_expired_run(interaction.user, run)
            if checked is None:
                await interaction.response.send_message(embed=build_expired_embed(), ephemeral=True)
                return
            run = checked

            if not interaction.response.is_done():
                await interaction.response.defer()

            profile = await self.db.get_zombie_player(interaction.guild.id, interaction.user.id)
            player_level = (await self.db.get_user_level(interaction.guild.id, interaction.user.id)).level
            pet = await self.db.get_active_pet(interaction.guild.id, interaction.user.id)
            channel = self._channel(interaction)

            if action == "pause":
                if run.in_combat:
                    await interaction.followup.send(
                        embed=warning_embed("Im Kampf", "Besiege zuerst den aktiven Zombie."),
                        ephemeral=True,
                    )
                    return
                if not run.between_waves:
                    await interaction.followup.send(
                        embed=info_embed(
                            "Wellenpause",
                            "Kaufbare Produkte findest du unter **`/shop`**.\n"
                            "Zwischen Wellen: erst Welle abschließen.",
                        ),
                        ephemeral=True,
                    )
                    return
                economy = await self.db.get_player_economy(interaction.guild.id, interaction.user.id)
                embed = build_between_waves_embed(run, economy)
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            if action == "next_wave":
                if run.in_combat:
                    await interaction.followup.send(
                        embed=warning_embed("Noch im Kampf", "Besiege zuerst den Zombie."),
                        ephemeral=True,
                    )
                    return
                result = advance_to_next_wave(run)
            else:
                result = perform_melee(
                    run,
                    player_level=player_level,
                    pet=pet,
                )

            run.last_action_text = "\n".join(result.lines)[:1024]
            run.updated_at = datetime.now(timezone.utc)

            if result.zombie_killed:
                profile.total_kills += 1
            if result.boss_killed:
                profile.boss_kills += 1

            await self.db.save_zombie_player(profile)

            if result.run_completed:
                rewards = await finalize_zombie_run(
                    self.db,
                    self.bot,
                    interaction.user,
                    run,
                    profile,
                    completed=True,
                    boss_killed=True,
                    channel=channel,
                )
                await self._update_run_message(
                    interaction,
                    run,
                    interaction.user,
                    final_embed=build_victory_embed(run, rewards),
                )
                return

            if result.run_failed:
                rewards = await finalize_zombie_run(
                    self.db,
                    self.bot,
                    interaction.user,
                    run,
                    profile,
                    completed=False,
                    channel=channel,
                )
                await self._update_run_message(
                    interaction,
                    run,
                    interaction.user,
                    final_embed=build_defeat_embed(run, rewards),
                )
                return

            await self.db.save_zombie_run(run)
            await self._update_run_message(interaction, run, interaction.user)

    async def _open_pet_impulse_window(
        self,
        interaction: discord.Interaction,
        run_id: int,
    ) -> None:
        """Öffnet separates Impuls-Fenster für den Pet-Bonusangriff."""
        assert interaction.guild is not None
        if not isinstance(interaction.user, discord.Member):
            return
        if not await self._ensure_zombie_mode(interaction):
            return

        async with game_lock(run_id):
            run = await self.db.get_zombie_run(run_id)
            if run is None or run.status != ZombieRunStatus.ACTIVE.value:
                await interaction.response.send_message(
                    embed=error_embed("Kein aktiver Run", "Starte mit `/zombies start`."),
                    ephemeral=True,
                )
                return
            if run.user_id != interaction.user.id:
                await interaction.response.send_message(
                    embed=error_embed("Nicht dein Run", "Das ist nicht dein Run."),
                    ephemeral=True,
                )
                return

            checked = await self._check_expired_run(interaction.user, run)
            if checked is None:
                await interaction.response.send_message(embed=build_expired_embed(), ephemeral=True)
                return
            run = checked

            pet = await self.db.get_active_pet(interaction.guild.id, interaction.user.id)
            if pet is None:
                await interaction.response.send_message(
                    embed=error_embed("Kein Pet", "Du brauchst ein aktives Pet für Bonus-Angriffe."),
                    ephemeral=True,
                )
                return
            if run.pet_action_cooldown > 0:
                await interaction.response.send_message(
                    embed=warning_embed(
                        "Cooldown",
                        f"Pet-Angriff in **{run.pet_action_cooldown}** Angriff(en) wieder verfügbar.",
                    ),
                    ephemeral=True,
                )
                return
            if not run.in_combat:
                await interaction.response.send_message(
                    embed=warning_embed("Kein Kampf", "Es ist kein Zombie aktiv."),
                    ephemeral=True,
                )
                return

            embed = build_pet_impulse_embed(run, pet)
            view = ZombiePetImpulseView(self, run_id, interaction.user.id)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _handle_pet_impulse(
        self,
        interaction: discord.Interaction,
        run_id: int,
        impulse_id: str,
    ) -> None:
        """Führt gewählten Pet-Impuls als Bonusangriff aus."""
        assert interaction.guild is not None
        if not isinstance(interaction.user, discord.Member):
            return
        if not await self._ensure_zombie_mode(interaction):
            return

        async with game_lock(run_id):
            run = await self.db.get_zombie_run(run_id)
            if run is None or run.status != ZombieRunStatus.ACTIVE.value:
                await interaction.response.send_message(
                    embed=error_embed("Kein aktiver Run", "Starte mit `/zombies start`."),
                    ephemeral=True,
                )
                return
            if run.user_id != interaction.user.id:
                await interaction.response.send_message(
                    embed=error_embed("Nicht dein Run", "Das ist nicht dein Run."),
                    ephemeral=True,
                )
                return

            checked = await self._check_expired_run(interaction.user, run)
            if checked is None:
                await interaction.response.send_message(embed=build_expired_embed(), ephemeral=True)
                return
            run = checked

            pet = await self.db.get_active_pet(interaction.guild.id, interaction.user.id)
            if pet is None:
                await interaction.response.send_message(
                    embed=error_embed("Kein Pet", "Kein aktives Pet vorhanden."),
                    ephemeral=True,
                )
                return

            await interaction.response.defer(ephemeral=True)

            profile = await self.db.get_zombie_player(interaction.guild.id, interaction.user.id)
            channel = self._channel(interaction)
            result = perform_pet_action(run, pet, impulse_id)

            run.last_action_text = "\n".join(result.lines)[:1024]
            run.updated_at = datetime.now(timezone.utc)

            if result.zombie_killed:
                profile.total_kills += 1
            if result.boss_killed:
                profile.boss_kills += 1

            await self.db.save_zombie_player(profile)

            if result.run_completed:
                rewards = await finalize_zombie_run(
                    self.db,
                    self.bot,
                    interaction.user,
                    run,
                    profile,
                    completed=True,
                    boss_killed=True,
                    channel=channel,
                )
                await self._refresh_stored_run_message(
                    run,
                    interaction.user,
                    final_embed=build_victory_embed(run, rewards),
                )
            elif result.run_failed:
                rewards = await finalize_zombie_run(
                    self.db,
                    self.bot,
                    interaction.user,
                    run,
                    profile,
                    completed=False,
                    channel=channel,
                )
                await self._refresh_stored_run_message(
                    run,
                    interaction.user,
                    final_embed=build_defeat_embed(run, rewards),
                )
            else:
                await self.db.save_zombie_run(run)
                await self._refresh_stored_run_message(run, interaction.user)

            try:
                await interaction.delete_original_response()
            except discord.HTTPException:
                pass

    async def _send_profile(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        if not isinstance(interaction.user, discord.Member):
            return
        profile = await self.db.get_zombie_player(interaction.guild.id, interaction.user.id)
        economy = await self.db.get_player_economy(interaction.guild.id, interaction.user.id)
        pet = await self.db.get_active_pet(interaction.guild.id, interaction.user.id)
        level_record = await self.db.get_user_level(interaction.guild.id, interaction.user.id)
        embed = build_profile_embed(
            profile,
            economy,
            pet,
            interaction.user,
            player_level=level_record.level,
            player_xp=level_record.xp,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _send_status(self, interaction: discord.Interaction) -> None:
        await self.status(interaction)

    @app_commands.command(name="start", description="Startet einen neuen Zombie-Survival-Run")
    @app_commands.guild_only()
    async def start(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Nur Server-Mitglieder können spielen."),
                ephemeral=True,
            )
            return
        if not await self._ensure_zombie_mode(interaction):
            return

        active = await self.db.get_active_zombie_run(interaction.guild.id, interaction.user.id)
        if active is not None:
            checked = await self._check_expired_run(interaction.user, active)
            if checked is None:
                await interaction.response.send_message(embed=build_expired_embed(), ephemeral=True)
                return
            embed, file, view = await self._build_run_message(interaction.user, checked)
            kwargs = {"embed": embed, "view": view, "ephemeral": True}
            if file:
                kwargs["file"] = file
            await interaction.response.send_message(**kwargs)
            msg = await interaction.original_response()
            checked.message_id = msg.id
            checked.channel_id = self._channel(interaction).id if self._channel(interaction) else None
            await self.db.save_zombie_run(checked)
            self.bot.add_view(view, message_id=msg.id)
            return

        cooldown = await self._get_cooldown(interaction.guild.id, interaction.user.id)
        if cooldown is not None:
            await interaction.response.send_message(
                embed=warning_embed(
                    "Cooldown",
                    f"Nächster Run in **{cooldown // 60}:{cooldown % 60:02d}**.",
                ),
                ephemeral=True,
            )
            return

        player_level = (await self.db.get_user_level(interaction.guild.id, interaction.user.id)).level
        hp_max = player_max_hp(player_level)
        now = datetime.now(timezone.utc)
        channel = self._channel(interaction)

        run = ZombieRunRecord(
            id=0,
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            channel_id=channel.id if channel else None,
            status=ZombieRunStatus.ACTIVE.value,
            wave=1,
            max_waves=Config.ZOMBIE_MAX_WAVES,
            player_hp=hp_max,
            player_max_hp=hp_max,
            created_at=now,
            updated_at=now,
        )
        run = await self.db.save_zombie_run(run)
        spawn_lines = spawn_wave(run)
        run.last_action_text = "\n".join(spawn_lines)
        run = await self.db.save_zombie_run(run)

        embed, file, view = await self._build_run_message(interaction.user, run)
        kwargs: dict = {"embed": embed, "view": view, "ephemeral": True}
        if file:
            kwargs["file"] = file
        await interaction.response.send_message(**kwargs)
        msg = await interaction.original_response()
        run.message_id = msg.id
        await self.db.save_zombie_run(run)
        self.bot.add_view(view, message_id=msg.id)

    @app_commands.command(name="status", description="Zeigt den aktiven Run oder Kurzprofil")
    @app_commands.guild_only()
    async def status(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        if not isinstance(interaction.user, discord.Member):
            return
        if not await self._ensure_zombie_mode(interaction):
            return

        run = await self.db.get_active_zombie_run(interaction.guild.id, interaction.user.id)
        if run:
            if run.status == ZombieRunStatus.EXPIRED.value:
                await interaction.response.send_message(embed=build_expired_embed(), ephemeral=True)
                return
            checked = await self._check_expired_run(interaction.user, run)
            if checked is None:
                await interaction.response.send_message(embed=build_expired_embed(), ephemeral=True)
                return
            embed, file, view = await self._build_run_message(interaction.user, checked)
            kwargs = {"embed": embed, "view": view, "ephemeral": True}
            if file:
                kwargs["file"] = file
            await interaction.response.send_message(**kwargs)
            msg = await interaction.original_response()
            checked.message_id = msg.id
            checked.channel_id = self._channel(interaction).id if self._channel(interaction) else None
            await self.db.save_zombie_run(checked)
            self.bot.add_view(view, message_id=msg.id)
            return

        profile = await self.db.get_zombie_player(interaction.guild.id, interaction.user.id)
        economy = await self.db.get_player_economy(interaction.guild.id, interaction.user.id)
        player_level = (await self.db.get_user_level(interaction.guild.id, interaction.user.id)).level
        cooldown = await self._get_cooldown(interaction.guild.id, interaction.user.id)
        embed = build_idle_status_embed(
            interaction.user,
            economy,
            profile,
            player_level=player_level,
            cooldown=cooldown,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="profil", description="Zeigt dein Zombie-Survival-Profil")
    @app_commands.guild_only()
    async def profil(self, interaction: discord.Interaction) -> None:
        if interaction.guild is not None and not await self._ensure_zombie_mode(interaction):
            return
        await self._send_profile(interaction)

    @app_commands.command(name="interface", description="Steuerzentrale mit Schnellbuttons")
    @app_commands.guild_only()
    async def interface(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        if not await self._ensure_zombie_mode(interaction):
            return
        economy = await self.db.get_player_economy(interaction.guild.id, interaction.user.id)
        embed = build_interface_embed(economy)
        await interaction.response.send_message(
            embed=embed,
            view=ZombieInterfaceView(self, interaction.user.id),
            ephemeral=True,
        )

    @app_commands.command(name="leaderboard", description="Zombie-Rangliste")
    @app_commands.guild_only()
    @app_commands.describe(sortierung="Sortierung der Rangliste")
    @app_commands.choices(
        sortierung=[
            app_commands.Choice(name="Zombie-Kills", value="kills"),
            app_commands.Choice(name="Boss-Kills", value="boss_kills"),
            app_commands.Choice(name="Höchste Welle", value="highest_wave"),
            app_commands.Choice(name="Gold", value="gold"),
        ]
    )
    async def leaderboard(
        self,
        interaction: discord.Interaction,
        sortierung: app_commands.Choice[str],
    ) -> None:
        assert interaction.guild is not None
        if not await self._ensure_zombie_mode(interaction):
            return
        key = sortierung.value

        if key == "gold":
            rows = await self.db.get_zombie_gold_leaderboard(
                interaction.guild.id,
                limit=Config.ZOMBIE_LEADERBOARD_LIMIT,
            )
            if not rows:
                await interaction.response.send_message(
                    embed=info_embed("Rangliste", "Noch keine Einträge."),
                    ephemeral=True,
                )
                return
            lines: list[str] = []
            for rank, record in enumerate(rows, start=1):
                member = interaction.guild.get_member(record.user_id)
                name = member.display_name if member else f"User {record.user_id}"
                medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"**{rank}.**")
                lines.append(f"{medal} {name} — **{record.gold:,}** 🪙")
            await interaction.response.send_message(
                embed=info_embed("Gold-Rangliste", "\n".join(lines)),
                ephemeral=True,
            )
            return

        rows = await self.db.get_zombie_leaderboard(
            interaction.guild.id,
            key,
            limit=Config.ZOMBIE_LEADERBOARD_LIMIT,
        )
        if not rows:
            await interaction.response.send_message(
                embed=info_embed("Rangliste", "Noch keine Zombie-Spieler."),
                ephemeral=True,
            )
            return

        labels = {
            "kills": ("Zombie-Kills", lambda r: f"**{r.total_kills:,}** 💀"),
            "boss_kills": ("Boss-Kills", lambda r: f"**{r.boss_kills:,}** 👁️"),
            "highest_wave": ("Höchste Welle", lambda r: f"Welle **{r.highest_wave}/{Config.ZOMBIE_MAX_WAVES}**"),
        }
        title, formatter = labels.get(key, labels["kills"])
        lines = []
        for rank, record in enumerate(rows, start=1):
            member = interaction.guild.get_member(record.user_id)
            name = member.display_name if member else f"User {record.user_id}"
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"**{rank}.**")
            lines.append(f"{medal} {name} — {formatter(record)}")

        await interaction.response.send_message(
            embed=info_embed(f"Rangliste — {title}", "\n".join(lines)),
            ephemeral=True,
        )

    @app_commands.command(name="help", description="Kurze Erklärung von Zombie Survival")
    @app_commands.guild_only()
    async def help_cmd(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_zombie_mode(interaction):
            return
        await interaction.response.send_message(embed=build_help_embed(), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    db: Database = bot.db  # type: ignore[attr-defined]
    await bot.add_cog(ZombiesCog(bot, db))
