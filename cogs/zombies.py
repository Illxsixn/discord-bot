"""
Zombie Survival Cog: Wellen, Kampf, Shop und Profil.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import discord
from discord import InteractionType, app_commands
from discord.ext import commands

from config import Config
from database.database import Database
from database.models import (
    ZombieCooldownType,
    ZombieRunRecord,
    ZombieRunStatus,
)
from utils.embeds import error_embed, info_embed, spaced_list, warning_embed
from utils.game_locks import game_lock
from utils.zombie_assets import apply_zombie_visual
from utils.zombie_combat import (
    perform_melee,
    perform_pet_action,
    resume_if_between_waves,
    spawn_wave,
)
from utils.zombie_content import get_zombie, player_max_hp
from utils.zombie_embeds import (
    build_defeat_embed,
    build_expired_embed,
    build_help_embed,
    build_idle_status_embed,
    build_interface_embed,
    build_pet_action_picker_embed,
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


class ZombieRunView(discord.ui.View):
    """Persistente Run-Buttons — dieselbe View-Instanz wird wiederverwendet."""

    def __init__(
        self,
        cog: "ZombiesCog",
        run_id: int,
        owner_id: int,
        *,
        has_pet: bool = True,
        pet_on_cooldown: bool = False,
    ) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.run_id = run_id
        self.owner_id = owner_id
        self._busy = False
        self._last_action = 0.0
        self._has_pet = has_pet
        self._pet_on_cooldown = pet_on_cooldown
        self._build_buttons()

    def _build_buttons(self) -> None:
        self.clear_items()

        melee = discord.ui.Button(
            label="Nahkampf",
            style=discord.ButtonStyle.danger,
            emoji="🗡️",
            custom_id=f"zombies:melee:{self.run_id}",
        )
        melee.callback = self._melee_callback
        self.add_item(melee)

        pet_btn = discord.ui.Button(
            label="Pet-Aktion",
            style=discord.ButtonStyle.primary,
            emoji="🐾",
            custom_id=f"zombies:pet:{self.run_id}",
            disabled=not self._has_pet or self._pet_on_cooldown,
        )
        pet_btn.callback = self._pet_callback
        self.add_item(pet_btn)

    def sync_from_run(
        self,
        run: ZombieRunRecord,
        *,
        has_pet: bool,
    ) -> None:
        """Aktualisiert Button-Zustand ohne neue View-Instanz."""
        self._has_pet = has_pet
        self._pet_on_cooldown = run.pet_action_cooldown > 0
        self._build_buttons()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy

    def action_cooldown_remaining(self) -> float:
        elapsed = time.monotonic() - self._last_action
        return max(0.0, Config.ZOMBIE_ACTION_COOLDOWN - elapsed)

    def mark_action(self) -> None:
        self._last_action = time.monotonic()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                embed=error_embed("Nicht dein Run", "Das ist nicht dein Run."),
                ephemeral=True,
            )
            return False
        return True

    async def _dispatch_action(self, interaction: discord.Interaction, action: str) -> None:
        if self._busy:
            await interaction.response.send_message(
                embed=warning_embed("Moment", "Die letzte Aktion läuft noch …"),
                ephemeral=True,
            )
            return

        if self.action_cooldown_remaining() > 0:
            await interaction.response.defer(ephemeral=True)
            return

        await self.cog._handle_run_action(
            interaction,
            self.run_id,
            action,
            view=self,
        )

    async def _melee_callback(self, interaction: discord.Interaction) -> None:
        await self._dispatch_action(interaction, "melee")

    async def _pet_callback(self, interaction: discord.Interaction) -> None:
        if self._busy:
            await interaction.response.send_message(
                embed=warning_embed("Moment", "Die letzte Aktion läuft noch …"),
                ephemeral=True,
            )
            return
        await self.cog._open_pet_action_picker(interaction, self.run_id)


class ZombiePetActionView(discord.ui.View):
    """Pet-Aktion direkt auf der Run-Nachricht wählen (Fokus, Glück, Power)."""

    def __init__(
        self,
        cog: "ZombiesCog",
        run_id: int,
        owner_id: int,
    ) -> None:
        super().__init__(timeout=60.0)
        self.cog = cog
        self.run_id = run_id
        self.owner_id = owner_id

        for action_id, emoji, label in (
            ("focus", "🎯", "Fokus"),
            ("luck", "🍀", "Glück"),
            ("energy", "⚡", "Power"),
        ):
            button = discord.ui.Button(
                label=label,
                emoji=emoji,
                style=discord.ButtonStyle.primary,
            )
            button.callback = self._make_callback(action_id)
            self.add_item(button)

        back = discord.ui.Button(
            label="Zurück",
            style=discord.ButtonStyle.secondary,
            emoji="↩️",
            row=1,
        )
        back.callback = self._back_callback
        self.add_item(back)

    def _make_callback(self, action_id: str):
        async def callback(interaction: discord.Interaction) -> None:
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message(
                    embed=error_embed("Nicht dein Run", "Das ist nicht dein Run."),
                    ephemeral=True,
                )
                return
            await self.cog._handle_run_action(
                interaction,
                self.run_id,
                "pet",
                pet_action=action_id,
            )

        return callback

    async def _back_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                embed=error_embed("Nicht dein Run", "Das ist nicht dein Run."),
                ephemeral=True,
            )
            return
        await self.cog._restore_run_message(interaction, self.run_id)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                embed=error_embed("Nicht dein Run", "Das ist nicht dein Run."),
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True  # type: ignore[union-attr]


class ZombiesCog(commands.GroupCog, group_name="zombies", group_description="Zombie Survival — Wellen, Gold & Pets"):
    """Zombie Survival RPG — kein Abbrechen, persistenter Run-Zustand."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db
        self._run_views: dict[int, ZombieRunView] = {}

    async def cog_load(self) -> None:
        stale = await self.db.get_stale_active_zombie_runs(Config.ZOMBIE_RUN_INACTIVITY)
        if stale:
            logger.info("%d Zombie-Run(s) wegen Inaktivität abgelaufen.", len(stale))
        for run in stale:
            await self._finalize_stale_run(run)
        for run in await self.db.get_all_active_zombie_runs():
            if run.message_id:
                view = await self._build_persistent_run_view(run)
                self._persist_run_view(view, run.message_id)

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

    async def _normalize_run(self, run: ZombieRunRecord) -> ZombieRunRecord:
        """Überspringt alte Wellenpausen aus früheren Versionen."""
        lines = resume_if_between_waves(run)
        if not lines:
            return run
        run.last_action_text = "\n".join(lines)[:1024]
        run.updated_at = datetime.now(timezone.utc)
        return await self.db.save_zombie_run(run)

    def _persist_run_view(self, view: ZombieRunView, message_id: int | None) -> None:
        """
        Registriert persistente Buttons für Nachricht und Bot-Neustart.

        Ephemeral-Antworten setzen in discord.py timeout=900 — dann ist die View
        nicht mehr persistent und add_view würde fehlschlagen.
        """
        if message_id and view.is_persistent() and not view.is_finished():
            self.bot.add_view(view, message_id=message_id)

    async def _send_run_panel(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        run: ZombieRunRecord,
        *,
        embed: discord.Embed,
        view: ZombieRunView,
        file: discord.File | None = None,
    ) -> None:
        """Sendet das Run-Panel als öffentliche Nachricht (persistent Views)."""
        kwargs: dict = {"embed": embed, "view": view}
        if file:
            kwargs["file"] = file
        await interaction.response.send_message(**kwargs)
        msg = await interaction.original_response()
        image_url = self._embed_image_url(msg)
        if image_url:
            run.current_zombie_image_url = image_url
        run.message_id = msg.id
        channel = self._channel(interaction)
        if channel:
            run.channel_id = channel.id
        await self.db.save_zombie_run(run)
        self._persist_run_view(view, msg.id)

    def _drop_run_view(self, run_id: int) -> None:
        self._run_views.pop(run_id, None)

    async def _get_run_view(
        self,
        run: ZombieRunRecord,
        *,
        has_pet: bool,
    ) -> ZombieRunView:
        """Gibt dieselbe View-Instanz pro Run zurück (Buttons bleiben nach Edits aktiv)."""
        view = self._run_views.get(run.id)
        if view is None:
            view = ZombieRunView(
                self,
                run.id,
                run.user_id,
                has_pet=has_pet,
                pet_on_cooldown=run.pet_action_cooldown > 0,
            )
            self._run_views[run.id] = view
        view.sync_from_run(run, has_pet=has_pet)
        return view

    async def _build_persistent_run_view(self, run: ZombieRunRecord) -> ZombieRunView:
        """View für persistente Nachrichten nach Bot-Neustart."""
        pet = await self.db.get_active_pet(run.guild_id, run.user_id)
        return await self._get_run_view(run, has_pet=pet is not None)

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

    @staticmethod
    def _embed_image_url(message: discord.Message) -> str | None:
        """Liefert die Discord-CDN-URL des Embed-Bilds (nach attachment://-Upload)."""
        if not message.embeds:
            return None
        image = message.embeds[0].image
        if image and image.url and not image.url.startswith("attachment://"):
            return image.url
        return None

    async def _build_run_message(
        self,
        member: discord.Member,
        run: ZombieRunRecord,
        *,
        refresh_visual: bool = False,
        use_attachment: bool = False,
    ) -> tuple[discord.Embed, discord.File | None, ZombieRunView]:
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
                file = apply_zombie_visual(
                    embed,
                    run,
                    run.current_zombie_key,
                    is_boss=zombie.is_boss,
                    use_attachment=use_attachment,
                    refresh_visual=refresh_visual,
                )

        view = await self._get_run_view(run, has_pet=pet is not None)
        return embed, file, view

    async def _restore_active_run_panel(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> bool:
        """Stellt das Run-Panel für einen aktiven Run wieder her."""
        assert interaction.guild is not None
        run = await self.db.get_active_zombie_run(interaction.guild.id, member.id)
        if run is None:
            return False
        if run.status == ZombieRunStatus.EXPIRED.value:
            await interaction.response.send_message(embed=build_expired_embed(), ephemeral=True)
            return True
        checked = await self._check_expired_run(member, run)
        if checked is None:
            await interaction.response.send_message(embed=build_expired_embed(), ephemeral=True)
            return True
        embed, file, view = await self._build_run_message(
            member, checked, refresh_visual=True, use_attachment=True
        )
        await self._send_run_panel(
            interaction,
            member,
            checked,
            embed=embed,
            view=view,
            file=file,
        )
        return True

    async def _respond_run_update(
        self,
        interaction: discord.Interaction,
        run: ZombieRunRecord,
        member: discord.Member,
        *,
        final_embed: discord.Embed | None = None,
        refresh_visual: bool = False,
        view: ZombieRunView | None = None,
    ) -> None:
        """Aktualisiert die Run-Nachricht über die Interaction (ephemeral-sicher)."""
        if final_embed is not None:
            self._drop_run_view(run.id)
            payload: dict = {"embed": final_embed, "view": None, "attachments": []}
        else:
            embed, _file, run_view = await self._build_run_message(
                member,
                run,
                refresh_visual=refresh_visual,
                use_attachment=False,
            )
            view = view or run_view
            payload = {"embed": embed, "view": view, "attachments": []}

        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(**payload)
            elif interaction.type is InteractionType.component:
                await interaction.response.edit_message(**payload)
            else:
                channel = self._channel(interaction)
                if channel is None:
                    await interaction.response.send_message(
                        embed=error_embed("Kein Kanal", "Run-Panel kann hier nicht gesendet werden."),
                        ephemeral=True,
                    )
                    return
                sent = await channel.send(**payload)
                run.message_id = sent.id
                run.channel_id = channel.id
                await self.db.save_zombie_run(run)
                self._persist_run_view(view, sent.id)
                await interaction.response.send_message(
                    embed=info_embed("Run aktualisiert", f"Dein Run-Panel: {sent.jump_url}"),
                    ephemeral=True,
                )
                return
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
            logger.warning("Run-Nachricht Update fehlgeschlagen: %s", exc)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    embed=error_embed("Update fehlgeschlagen", "Nutze `/zombies status`."),
                    ephemeral=True,
                )
            return

        if final_embed is None and view is not None:
            if interaction.message and run.message_id != interaction.message.id:
                run.message_id = interaction.message.id
                await self.db.save_zombie_run(run)
            self._persist_run_view(view, run.message_id)

    async def _restore_run_message(
        self,
        interaction: discord.Interaction,
        run_id: int,
    ) -> None:
        """Stellt die Run-Ansicht nach dem Pet-Menü wieder her."""
        assert interaction.guild is not None
        if not isinstance(interaction.user, discord.Member):
            return

        run = await self.db.get_zombie_run(run_id)
        if run is None or run.user_id != interaction.user.id:
            await interaction.response.send_message(
                embed=error_embed("Kein aktiver Run", "Starte mit `/zombies start`."),
                ephemeral=True,
            )
            return

        await self._respond_run_update(interaction, run, interaction.user)

    async def _open_pet_action_picker(
        self,
        interaction: discord.Interaction,
        run_id: int,
    ) -> None:
        assert interaction.guild is not None
        if not isinstance(interaction.user, discord.Member):
            return

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

        if not run.in_combat:
            await interaction.response.send_message(
                embed=warning_embed("Kein Kampf", "Es ist gerade kein Zombie aktiv."),
                ephemeral=True,
            )
            return
        if run.pet_action_cooldown > 0:
            attacks = run.pet_action_cooldown
            label = "Angriff" if attacks == 1 else "Angriffe"
            await interaction.response.send_message(
                embed=warning_embed(
                    "Cooldown",
                    f"Pet-Aktion in **{attacks}** {label} (Nahkampf) wieder verfügbar.",
                ),
                ephemeral=True,
            )
            return

        pet = await self.db.get_active_pet(interaction.guild.id, interaction.user.id)
        if pet is None:
            await interaction.response.send_message(
                embed=warning_embed("Kein Pet", "Du brauchst ein aktives Pet für Spezialaktionen."),
                ephemeral=True,
            )
            return

        embed = build_pet_action_picker_embed(pet)
        view = ZombiePetActionView(self, run_id, interaction.user.id)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _handle_run_action(
        self,
        interaction: discord.Interaction,
        run_id: int,
        action: str,
        *,
        view: ZombieRunView | None = None,
        pet_action: str | None = None,
    ) -> None:
        assert interaction.guild is not None
        if not isinstance(interaction.user, discord.Member):
            return

        member = interaction.user

        run = await self.db.get_zombie_run(run_id)
        if run is None or run.status != ZombieRunStatus.ACTIVE.value:
            await interaction.response.send_message(
                embed=error_embed("Kein aktiver Run", "Starte mit `/zombies start`."),
                ephemeral=True,
            )
            return
        if run.user_id != member.id:
            await interaction.response.send_message(
                embed=error_embed("Nicht dein Run", "Das ist nicht dein Run."),
                ephemeral=True,
            )
            return

        checked = await self._check_expired_run(member, run)
        if checked is None:
            await interaction.response.send_message(embed=build_expired_embed(), ephemeral=True)
            return
        run = await self._normalize_run(checked)

        if view is not None:
            view.set_busy(True)

        followup_embed: discord.Embed | None = None
        final_embed: discord.Embed | None = None
        saved_run: ZombieRunRecord | None = None
        refresh_visual = False

        try:
            async with game_lock("zombie", run_id):
                run = await self.db.get_zombie_run(run_id)
                if run is None or run.status != ZombieRunStatus.ACTIVE.value or run.user_id != member.id:
                    followup_embed = error_embed("Kein aktiver Run", "Starte mit `/zombies start`.")
                else:
                    checked = await self._check_expired_run(member, run)
                    if checked is None:
                        followup_embed = build_expired_embed()
                    else:
                        run = await self._normalize_run(checked)
                        profile = await self.db.get_zombie_player(interaction.guild.id, member.id)
                        player_level = (
                            await self.db.get_user_level(interaction.guild.id, member.id)
                        ).level
                        pet = await self.db.get_active_pet(interaction.guild.id, member.id)

                        if action == "pet":
                            if not pet_action:
                                followup_embed = warning_embed(
                                    "Keine Aktion",
                                    "Wähle Fokus, Glück oder Power.",
                                )
                                result = None
                            else:
                                result = perform_pet_action(run, pet, action=pet_action)
                        else:
                            result = perform_melee(run, player_level=player_level, pet=pet)

                        if followup_embed is None and result is not None:
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
                                    member,
                                    run,
                                    profile,
                                    completed=True,
                                    boss_killed=True,
                                )
                                final_embed = build_victory_embed(run, rewards)
                            elif result.run_failed:
                                rewards = await finalize_zombie_run(
                                    self.db,
                                    self.bot,
                                    member,
                                    run,
                                    profile,
                                    completed=False,
                                )
                                final_embed = build_defeat_embed(run, rewards)
                            else:
                                await self.db.save_zombie_run(run)
                                saved_run = run
                                refresh_visual = bool(
                                    result.zombie_killed or result.wave_cleared
                                )
                                if view is not None:
                                    pet = await self.db.get_active_pet(
                                        interaction.guild.id,
                                        member.id,
                                    )
                                    view.sync_from_run(run, has_pet=pet is not None)
                                    view.mark_action()
        finally:
            if view is not None:
                view.set_busy(False)

        if followup_embed is not None:
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=followup_embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=followup_embed, ephemeral=True)
            return

        if final_embed is not None:
            await self._respond_run_update(
                interaction,
                run,
                member,
                final_embed=final_embed,
            )
        elif saved_run is not None:
            await self._respond_run_update(
                interaction,
                saved_run,
                member,
                view=view,
                refresh_visual=refresh_visual,
            )

    async def _send_profile(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        if not isinstance(interaction.user, discord.Member):
            return
        profile = await self.db.get_zombie_player(interaction.guild.id, interaction.user.id)
        economy = await self.db.get_player_economy(interaction.guild.id, interaction.user.id)
        pet = await self.db.get_active_pet(interaction.guild.id, interaction.user.id)
        embed = build_profile_embed(profile, economy, pet, interaction.user)
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

        active = await self.db.get_active_zombie_run(interaction.guild.id, interaction.user.id)
        if active is not None:
            await self._restore_active_run_panel(interaction, interaction.user)
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

        embed, file, view = await self._build_run_message(
            interaction.user, run, refresh_visual=True, use_attachment=True
        )
        await self._send_run_panel(
            interaction,
            interaction.user,
            run,
            embed=embed,
            view=view,
            file=file,
        )

    @app_commands.command(name="status", description="Zeigt den aktiven Run oder Kurzprofil")
    @app_commands.guild_only()
    async def status(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        if not isinstance(interaction.user, discord.Member):
            return

        if await self._restore_active_run_panel(interaction, interaction.user):
            return

        profile = await self.db.get_zombie_player(interaction.guild.id, interaction.user.id)
        economy = await self.db.get_player_economy(interaction.guild.id, interaction.user.id)
        cooldown = await self._get_cooldown(interaction.guild.id, interaction.user.id)
        embed = build_idle_status_embed(interaction.user, economy, profile, cooldown=cooldown)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="resume", description="Stellt den aktiven Run nach Bot-Neustart wieder her")
    @app_commands.guild_only()
    async def resume(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Nur Server-Mitglieder können spielen."),
                ephemeral=True,
            )
            return

        if await self._restore_active_run_panel(interaction, interaction.user):
            return

        await interaction.response.send_message(
            embed=error_embed(
                "Kein aktiver Run",
                "Du hast keinen laufenden Run. Starte mit **`/zombies start`**.",
            ),
            ephemeral=True,
        )

    @app_commands.command(name="profil", description="Zeigt dein Zombie-Survival-Profil")
    @app_commands.guild_only()
    async def profil(self, interaction: discord.Interaction) -> None:
        await self._send_profile(interaction)

    @app_commands.command(name="interface", description="Steuerzentrale mit Schnellbuttons")
    @app_commands.guild_only()
    async def interface(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
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
            app_commands.Choice(name="Zombie-Level", value="level"),
            app_commands.Choice(name="Gold", value="gold"),
        ]
    )
    async def leaderboard(
        self,
        interaction: discord.Interaction,
        sortierung: app_commands.Choice[str],
    ) -> None:
        assert interaction.guild is not None
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
                embed=info_embed("Gold-Rangliste", spaced_list(lines)),
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
            "level": ("Zombie-Level", lambda r: f"Level **{r.level}** · **{r.xp:,}** XP"),
        }
        title, formatter = labels.get(key, labels["kills"])
        lines = []
        for rank, record in enumerate(rows, start=1):
            member = interaction.guild.get_member(record.user_id)
            name = member.display_name if member else f"User {record.user_id}"
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"**{rank}.**")
            lines.append(f"{medal} {name} — {formatter(record)}")

        await interaction.response.send_message(
            embed=info_embed(f"Rangliste — {title}", spaced_list(lines)),
            ephemeral=True,
        )

    @app_commands.command(name="help", description="Kurze Erklärung von Zombie Survival")
    @app_commands.guild_only()
    async def help_cmd(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(embed=build_help_embed(), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    db: Database = bot.db  # type: ignore[attr-defined]
    await bot.add_cog(ZombiesCog(bot, db))
