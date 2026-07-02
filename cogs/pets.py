"""
Anarchy Pets — Virtuelle Begleiter für Discord-Server.

Sammeln, pflegen und wachsen lassen ohne Stress:
Kein Hunger, kein Tod, kein Zwang.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from config import Config
from database.database import Database
from database.models import PetCooldownType, PetRarity, PetRecord
from utils.embeds import error_embed, info_embed, success_embed
from utils.permissions import bot_can_use_channel
from utils.pet_ai_images import (
    PetPortraitError,
    agnes_configured,
    ensure_pet_portrait,
    load_pet_portrait_buffer,
    portrait_status_label,
)
from utils.pet_embeds import (
    build_leaderboard_line,
    build_pet_collection_embed,
    build_pet_duplicate_embed,
    build_pet_display_embed,
    build_pet_dex_embed,
    build_pet_hatch_embed,
    build_pet_info_embed,
    build_pet_leaderboard_embed,
    build_pet_play_embed,
    pet_embed_color,
)
from utils.pet_play import (
    PET_IMPULSES,
    PET_PLAY_ROUNDS,
    impulse_by_id,
    pet_play_xp_for_score,
    random_impulse_id,
)
from utils.pets import (
    apply_pet_xp_boost,
    pet_xp_boost_label,
    default_pet_name,
    evolution_display,
    evolution_stage_from_level,
    get_species_by_name,
    get_species_rarity,
    is_evolution_milestone,
    level_from_xp,
    mood_display,
    random_catchphrase,
    random_favorite_activity,
    random_mood,
    random_personality,
    random_species,
    species_display_emoji,
    validate_pet_name,
    PetSpeciesDefinition,
)

logger = logging.getLogger(__name__)


class PetImpulseView(discord.ui.View):
    """3-Runden Impuls-Spiel: schnell den richtigen Pet-Impuls treffen."""

    def __init__(
        self,
        cog: "PetsCog",
        owner_id: int,
        pet: PetRecord,
        species: PetSpeciesDefinition | None,
    ) -> None:
        super().__init__(timeout=45.0)
        self.cog = cog
        self.owner_id = owner_id
        self.pet = pet
        self.species = species
        self.round_num = 1
        self.score = 0
        self.finished = False
        self.correct_id = random_impulse_id()
        self._rebuild_buttons()

    def _rebuild_buttons(self) -> None:
        self.clear_items()
        for impulse_id, emoji, label in PET_IMPULSES:
            button = discord.ui.Button(
                label=label,
                emoji=emoji,
                style=discord.ButtonStyle.secondary,
                row=0,
            )
            button.callback = self._make_callback(impulse_id)
            self.add_item(button)

    def _make_callback(self, chosen_id: str):
        async def callback(interaction: discord.Interaction) -> None:
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message(
                    embed=error_embed("Nicht dein Spiel", "Nur der Besitzer kann spielen."),
                    ephemeral=True,
                )
                return
            if self.finished:
                await interaction.response.send_message(
                    embed=error_embed("Schon vorbei", "Dieses Spiel ist bereits beendet."),
                    ephemeral=True,
                )
                return

            correct = chosen_id == self.correct_id
            if correct:
                self.score += 1

            correct_impulse = impulse_by_id(self.correct_id)
            chosen_impulse = impulse_by_id(chosen_id)
            correct_label = (
                f"{correct_impulse[1]} {correct_impulse[2]}" if correct_impulse else self.correct_id
            )
            chosen_label = (
                f"{chosen_impulse[1]} {chosen_impulse[2]}" if chosen_impulse else chosen_id
            )

            if self.round_num >= PET_PLAY_ROUNDS:
                self.finished = True
                for item in self.children:
                    item.disabled = True  # type: ignore[union-attr]

                base_xp, hit_bonus, total_xp = pet_play_xp_for_score(self.score)
                display_xp = apply_pet_xp_boost(
                    total_xp,
                    species_name=self.pet.species,
                    evolution_stage=self.pet.evolution_stage,
                )
                member = interaction.user
                if isinstance(member, discord.Member) and interaction.guild is not None:
                    channel = interaction.channel if isinstance(
                        interaction.channel, (discord.TextChannel, discord.Thread)
                    ) else None
                    fresh_pet = await self.cog.get_pet(self.pet.id)
                    if fresh_pet is not None:
                        await self.cog._apply_pet_xp(
                            fresh_pet,
                            total_xp,
                            member=member,
                            channel=channel,
                            count_interaction=True,
                        )
                    challenges = self.cog.bot.get_cog("ChallengesCog")
                    if challenges is not None:
                        await challenges.track_pet_play(member, channel=channel)  # type: ignore[attr-defined]

                feedback = (
                    f"✅ **{correct_label}**"
                    if correct
                    else f"❌ **{chosen_label}** · richtig: **{correct_label}**"
                )
                embed = build_pet_play_embed(
                    self.pet,
                    self.species,
                    round_num=self.round_num,
                    total_rounds=PET_PLAY_ROUNDS,
                    score=self.score,
                    feedback=feedback,
                    xp_gain=display_xp,
                    xp_breakdown=f"{base_xp} Basis + {hit_bonus} Treffer",
                )
                await interaction.response.edit_message(embed=embed, view=self)
                self.stop()
                return

            feedback = (
                f"✅ **{correct_label}** — weiter!"
                if correct
                else f"❌ **{chosen_label}** · richtig: **{correct_label}**"
            )
            self.round_num += 1
            self.correct_id = random_impulse_id()
            self._rebuild_buttons()
            embed = build_pet_play_embed(
                self.pet,
                self.species,
                round_num=self.round_num,
                total_rounds=PET_PLAY_ROUNDS,
                score=self.score,
                feedback=feedback,
            )
            await interaction.response.edit_message(embed=embed, view=self)

        return callback

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True  # type: ignore[union-attr]


class PetSelectView(discord.ui.View):
    """Dropdown zum Wechseln des aktiven Pets."""

    def __init__(self, db: Database, owner_id: int, pets: list[PetRecord]) -> None:
        super().__init__(timeout=120.0)
        self.db = db
        self.owner_id = owner_id
        options = []
        for pet in pets[:25]:
            species = get_species_by_name(pet.species)
            options.append(
                discord.SelectOption(
                    label=f"{pet.name} ({pet.species})",
                    value=str(pet.id),
                    description=f"Lv. {pet.level} · {evolution_display(pet.evolution_stage)}",
                    default=pet.is_active,
                )
            )
        select = discord.ui.Select(
            placeholder="Aktives Pet wählen …",
            options=options,
            min_values=1,
            max_values=1,
        )
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                embed=error_embed("Nicht dein Menü", "Nur der Besitzer kann das aktive Pet wechseln."),
                ephemeral=True,
            )
            return
        if interaction.guild is None:
            return

        values = interaction.data.get("values") if interaction.data else None
        if not values:
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Keine Auswahl getroffen."),
                ephemeral=True,
            )
            return

        pet_id = int(values[0])
        pet = await self.db.set_active_pet(interaction.guild.id, self.owner_id, pet_id)
        if pet is None:
            await interaction.response.send_message(
                embed=error_embed("Fehler", "Pet konnte nicht aktiviert werden."),
                ephemeral=True,
            )
            return

        species = get_species_by_name(pet.species)
        emoji = species_display_emoji(species, pet.evolution_stage)
        await interaction.response.send_message(
            embed=success_embed(
                "Aktives Pet gewechselt",
                f"{emoji} **{pet.name}** ist jetzt dein aktiver Begleiter.",
            ),
        )
        self.stop()


class PetsCog(commands.GroupCog, group_name="pet", group_description="Virtuelle Begleiter — sammeln, spielen, wachsen"):
    """Haustier-System mit Slash-Commands und XP-Integration."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.CheckFailure):
            return
        logger.exception("Pet-Befehl Fehler: %s", error)
        embed = error_embed("Pet-Befehl fehlgeschlagen", str(error))
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass

    async def get_pet(self, pet_id: int) -> PetRecord | None:
        """Lädt ein Pet aus der Datenbank."""
        return await self.db.get_pet(pet_id)

    async def _ensure_bot_permissions(
        self,
        interaction: discord.Interaction,
        *,
        add_reactions: bool = False,
    ) -> tuple[bool, str | None]:
        """Prüft Bot-Berechtigungen im Kanal."""
        channel = interaction.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return False, "Dieser Befehl ist nur in Textkanälen verfügbar."
        return bot_can_use_channel(
            channel,
            send=True,
            embed_links=True,
            read_history=True,
            add_reactions=add_reactions,
        )

    async def _cooldown_remaining(
        self,
        guild_id: int,
        owner_id: int,
        cooldown_type: PetCooldownType,
    ) -> timedelta | None:
        """Gibt verbleibende Cooldown-Zeit zurück oder None."""
        expires = await self.db.get_pet_cooldown(guild_id, owner_id, cooldown_type)
        if expires is None:
            return None
        now = datetime.now(timezone.utc)
        if expires <= now:
            return None
        return expires - now

    async def _set_cooldown(
        self,
        guild_id: int,
        owner_id: int,
        cooldown_type: PetCooldownType,
        seconds: int,
    ) -> None:
        """Setzt einen Cooldown ab jetzt."""
        expires = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        await self.db.set_pet_cooldown(guild_id, owner_id, cooldown_type, expires)

    async def _apply_pet_xp(
        self,
        pet: PetRecord,
        amount: int,
        *,
        member: discord.Member | None = None,
        channel: discord.TextChannel | discord.Thread | None = None,
        count_interaction: bool = False,
        announce_evolution: bool = True,
        apply_boost: bool = True,
    ) -> PetRecord:
        """Wendet Pet-XP an und aktualisiert Level/Evolution."""
        old_level = pet.level
        boosted_amount = (
            apply_pet_xp_boost(
                amount,
                species_name=pet.species,
                evolution_stage=pet.evolution_stage,
            )
            if apply_boost
            else amount
        )
        pet.xp += boosted_amount
        pet.level = level_from_xp(pet.xp)
        pet.evolution_stage = evolution_stage_from_level(pet.level)
        pet.last_interaction = datetime.now(timezone.utc)
        if count_interaction:
            pet.total_interactions += 1
        await self.db.save_pet(pet)

        if member is not None and announce_evolution:
            milestone = is_evolution_milestone(old_level, pet.level)
            if milestone is not None:
                await self._announce_evolution(member, pet, milestone, channel)

        return pet

    async def award_pet_xp(
        self,
        member: discord.Member,
        amount: int,
        *,
        channel: discord.TextChannel | discord.Thread | None = None,
        count_interaction: bool = False,
        announce_evolution: bool = True,
    ) -> bool:
        """Öffentliche API für Pet-XP aus anderen Systemen."""
        if amount <= 0 or member.bot:
            return False

        pet = await self.db.get_active_pet(member.guild.id, member.id)
        if pet is None:
            return False

        await self._apply_pet_xp(
            pet,
            amount,
            member=member,
            channel=channel,
            count_interaction=count_interaction,
            announce_evolution=announce_evolution,
        )
        return True

    async def award_pet_activity_xp(
        self,
        member: discord.Member,
        *,
        channel: discord.TextChannel | discord.Thread | None = None,
    ) -> bool:
        """Vergibt Pet-XP für Nachrichtenaktivität (mit Cooldown)."""
        if member.bot:
            return False

        remaining = await self._cooldown_remaining(
            member.guild.id, member.id, PetCooldownType.ACTIVITY
        )
        if remaining is not None:
            return False

        pet = await self.db.get_active_pet(member.guild.id, member.id)
        if pet is None:
            return False

        amount = random.randint(Config.PET_XP_ACTIVITY_MIN, Config.PET_XP_ACTIVITY_MAX)
        await self._apply_pet_xp(
            pet,
            amount,
            member=member,
            channel=channel,
            count_interaction=False,
            announce_evolution=False,
        )
        await self._set_cooldown(
            member.guild.id,
            member.id,
            PetCooldownType.ACTIVITY,
            Config.PET_XP_ACTIVITY_COOLDOWN,
        )
        challenges = self.bot.get_cog("ChallengesCog")
        if challenges is not None:
            await challenges.track_pet_activity(member, channel=channel)  # type: ignore[attr-defined]
        return True

    async def _announce_evolution(
        self,
        member: discord.Member,
        pet: PetRecord,
        milestone: int,
        channel: discord.TextChannel | discord.Thread | None,
    ) -> None:
        """Sendet eine Nachricht bei Evolutions-Meilensteinen."""
        if channel is None:
            return

        allowed, _ = bot_can_use_channel(channel, send=True, embed_links=True)
        if not allowed:
            return

        species = get_species_by_name(pet.species)
        emoji = species_display_emoji(species, pet.evolution_stage)
        stage = evolution_display(pet.evolution_stage)

        titles = {
            Config.PET_EVOLUTION_TEEN: "🌱 Dein Pet wächst!",
            Config.PET_EVOLUTION_ADULT: "✨ Dein Pet ist erwachsen!",
            Config.PET_EVOLUTION_LEGENDARY: "👑 Meisterhafte Evolution!",
        }
        descriptions = {
            Config.PET_EVOLUTION_TEEN: (
                f"{emoji} **{pet.name}** · Level **{milestone}** → **{stage}**\n"
                "Dein Begleiter wird neugieriger und zeigt mehr Persönlichkeit."
            ),
            Config.PET_EVOLUTION_ADULT: (
                f"{emoji} **{pet.name}** · Level **{milestone}** → **{stage}**\n"
                "Ein stolzer Begleiter an deiner Seite."
            ),
            Config.PET_EVOLUTION_LEGENDARY: (
                f"{emoji} **{pet.name}** · Level **{milestone}** → **{stage}**\n"
                "Dein Begleiter hat seine Meisterform erreicht!"
            ),
        }

        embed = success_embed(
            titles.get(milestone, "Pet-Evolution!"),
            descriptions.get(milestone, f"**{pet.name}** ist gewachsen!"),
        )
        embed.color = pet_embed_color(pet.evolution_stage)
        embed.set_footer(text=f"Besitzer: {member.display_name}")
        try:
            await channel.send(content=member.mention, embed=embed)
        except discord.Forbidden:
            logger.warning("Pet-Evolution-Nachricht konnte nicht gesendet werden (Guild %s).", member.guild.id)

    async def _track_pet_challenge(
        self,
        member: discord.Member,
        method: str,
        *,
        channel: discord.TextChannel | discord.Thread | None = None,
    ) -> None:
        challenges = self.bot.get_cog("ChallengesCog")
        if challenges is None:
            return
        tracker = getattr(challenges, method, None)
        if tracker is not None:
            await tracker(member, channel=channel)  # type: ignore[misc]

    @app_commands.command(name="ei", description="Öffnet ein Pet-Ei und adoptiert einen neuen Begleiter (1× täglich).")
    @app_commands.guild_only()
    async def ei(self, interaction: discord.Interaction) -> None:
        """Öffnet ein Pet-Ei."""
        await interaction.response.defer()
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return

        allowed, msg = await self._ensure_bot_permissions(interaction)
        if not allowed:
            await interaction.followup.send(
                embed=error_embed("Fehlende Berechtigungen", msg or "Der Bot kann hier nicht antworten."),
            )
            return

        remaining = await self._cooldown_remaining(
            interaction.guild.id, interaction.user.id, PetCooldownType.EGG
        )
        if remaining is not None:
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            await interaction.followup.send(
                embed=error_embed(
                    "Cooldown",
                    f"Du kannst erst in **{hours}h {minutes}m** wieder ein Ei öffnen.",
                ),
            )
            return

        species = random_species()
        personality = random_personality()
        mood = random_mood()
        favorite = random_favorite_activity()
        catchphrase = random_catchphrase(personality)
        now = datetime.now(timezone.utc)

        existing = await self.db.get_pets_by_owner(interaction.guild.id, interaction.user.id)
        owned_species = {pet.species for pet in existing}

        await self._set_cooldown(
            interaction.guild.id,
            interaction.user.id,
            PetCooldownType.EGG,
            Config.PET_EGG_COOLDOWN,
        )

        if species.name in owned_species:
            duplicate_pet = next((pet for pet in existing if pet.species == species.name), None)
            if duplicate_pet is not None:
                await self._apply_pet_xp(
                    duplicate_pet,
                    Config.PET_DUPLICATE_PET_XP,
                    member=interaction.user,
                    channel=interaction.channel
                    if isinstance(interaction.channel, (discord.TextChannel, discord.Thread))
                    else None,
                    apply_boost=False,
                )

            levels = self.bot.get_cog("LevelsCog")
            if levels is not None:
                await levels.award_xp(  # type: ignore[attr-defined]
                    interaction.user,
                    Config.PET_DUPLICATE_PLAYER_XP,
                    channel=interaction.channel
                    if isinstance(interaction.channel, (discord.TextChannel, discord.Thread))
                    else None,
                    apply_pet_boost=False,
                )

            embed = build_pet_duplicate_embed(
                interaction.user,
                species,
                pet_xp=Config.PET_DUPLICATE_PET_XP,
                player_xp=Config.PET_DUPLICATE_PLAYER_XP,
            )
            await interaction.followup.send(embed=embed)
            return

        has_active = any(p.is_active for p in existing)

        pet = PetRecord(
            id=0,
            owner_id=interaction.user.id,
            guild_id=interaction.guild.id,
            name=default_pet_name(species),
            species=species.name,
            mood=mood,
            favorite_activity=favorite,
            personality=personality,
            catchphrase=catchphrase,
            adoption_date=now,
            last_interaction=now,
            is_active=not has_active,
        )
        created = await self.db.create_pet(pet)

        embed = build_pet_hatch_embed(
            interaction.user,
            created,
            species,
            personality=personality,
            mood=mood,
            favorite=favorite,
            catchphrase=catchphrase,
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="dex", description="Zeigt das Pet-Sammlungsbuch (alle Arten, öffentlich).")
    @app_commands.guild_only()
    async def dex(self, interaction: discord.Interaction) -> None:
        """Zeigt den Pet-Dex."""
        await interaction.response.defer()
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return

        allowed, msg = await self._ensure_bot_permissions(interaction)
        if not allowed:
            await interaction.followup.send(
                embed=error_embed("Fehlende Berechtigungen", msg or "Der Bot kann hier nicht antworten."),
            )
            return

        owned = await self.db.get_pets_by_owner(interaction.guild.id, interaction.user.id)
        discovered = {pet.species for pet in owned}
        await interaction.followup.send(
            embed=build_pet_dex_embed(discovered, owner_name=interaction.user.display_name),
        )

    @app_commands.command(name="info", description="Zeigt Infos über dein aktives Pet.")
    @app_commands.guild_only()
    async def info(self, interaction: discord.Interaction) -> None:
        """Zeigt Pet-Informationen."""
        await interaction.response.defer()
        if interaction.guild is None:
            return

        allowed, msg = await self._ensure_bot_permissions(interaction)
        if not allowed:
            await interaction.followup.send(
                embed=error_embed("Fehlende Berechtigungen", msg or "Der Bot kann hier nicht antworten."),
            )
            return

        pet = await self.db.get_active_pet(interaction.guild.id, interaction.user.id)
        if pet is None:
            await interaction.followup.send(
                embed=info_embed(
                    "Kein aktives Pet",
                    f"{interaction.user.mention} hat noch kein aktives Pet.\nÖffne ein Ei mit **`/pet ei`**!",
                ),
            )
            return

        if not isinstance(interaction.user, discord.Member):
            return
        embed = build_pet_info_embed(pet, interaction.user)
        await interaction.followup.send(embed=embed)
        await self._track_pet_challenge(
            interaction.user,
            "track_pet_info",
            channel=interaction.channel if isinstance(interaction.channel, (discord.TextChannel, discord.Thread)) else None,
        )

    @app_commands.command(
        name="display",
        description="Zeigt ein KI-Portrait deines aktiven Pets (wird einmal generiert und gespeichert).",
    )
    @app_commands.guild_only()
    async def display(self, interaction: discord.Interaction) -> None:
        """Generiert oder lädt das KI-Portrait des aktiven Pets."""
        await interaction.response.defer()
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return

        allowed, msg = await self._ensure_bot_permissions(interaction)
        if not allowed:
            await interaction.followup.send(
                embed=error_embed("Fehlende Berechtigungen", msg or "Der Bot kann hier nicht antworten."),
            )
            return

        pet = await self.db.get_active_pet(interaction.guild.id, interaction.user.id)
        if pet is None:
            await interaction.followup.send(
                embed=info_embed(
                    "Kein aktives Pet",
                    f"{interaction.user.mention} hat noch kein aktives Pet.\nÖffne ein Ei mit **`/pet ei`**!",
                ),
            )
            return

        if not agnes_configured():
            await interaction.followup.send(
                embed=error_embed(
                    "KI-Portraits nicht verfügbar",
                    "Der Bot-Admin muss `AGNES_API_KEY` in der `.env` hinterlegen.\n"
                    "Key erhältlich auf [platform.agnes-ai.com](https://platform.agnes-ai.com).",
                ),
            )
            return

        species = get_species_by_name(pet.species)
        rarity = species.rarity if species else PetRarity.COMMON

        try:
            image_path = await ensure_pet_portrait(pet)
        except PetPortraitError as exc:
            await interaction.followup.send(
                embed=error_embed("Portrait fehlgeschlagen", str(exc)),
            )
            return

        filename = f"pet_{pet.id}.png"
        attachment = discord.File(load_pet_portrait_buffer(image_path, rarity), filename=filename)
        embed = build_pet_display_embed(
            pet,
            interaction.user,
            portrait_label=portrait_status_label(pet),
        )
        embed.set_image(url=f"attachment://{filename}")
        await interaction.followup.send(embed=embed, files=[attachment])

    @app_commands.command(
        name="play",
        description="Impuls-Rush mit deinem Pet — 3 schnelle Runden (Cooldown: 5 Min.).",
    )
    @app_commands.guild_only()
    async def play(self, interaction: discord.Interaction) -> None:
        """Startet das Impuls-Minispiel."""
        allowed, msg = await self._ensure_bot_permissions(interaction, add_reactions=True)
        if not allowed:
            await interaction.response.send_message(
                embed=error_embed("Fehlende Berechtigungen", msg or "Der Bot kann hier nicht antworten."),
                ephemeral=True,
            )
            return

        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return

        remaining = await self._cooldown_remaining(
            interaction.guild.id, interaction.user.id, PetCooldownType.PLAY
        )
        if remaining is not None:
            minutes = int(remaining.total_seconds() // 60)
            seconds = int(remaining.total_seconds() % 60)
            await interaction.response.send_message(
                embed=error_embed(
                    "Cooldown",
                    f"Dein Pet braucht noch **{minutes}m {seconds}s** Pause.",
                ),
                ephemeral=True,
            )
            return

        pet = await self.db.get_active_pet(interaction.guild.id, interaction.user.id)
        if pet is None:
            await interaction.response.send_message(
                embed=info_embed(
                    "Kein aktives Pet",
                    f"{interaction.user.mention} braucht ein aktives Pet.\nÖffne ein Ei mit **`/pet ei`** oder wähle eins mit **`/pets`**!",
                ),
                ephemeral=True,
            )
            return

        species = get_species_by_name(pet.species)

        embed = build_pet_play_embed(pet, species, total_rounds=PET_PLAY_ROUNDS)
        view = PetImpulseView(self, interaction.user.id, pet, species)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        await self._set_cooldown(
            interaction.guild.id,
            interaction.user.id,
            PetCooldownType.PLAY,
            Config.PET_PLAY_COOLDOWN,
        )

    @app_commands.command(name="rename", description="Benennt dein aktives Pet um (Cooldown: 7 Tage).")
    @app_commands.guild_only()
    @app_commands.describe(neuer_name="Neuer Name (max. 15 Zeichen)")
    async def rename(self, interaction: discord.Interaction, neuer_name: str) -> None:
        """Benennt das aktive Pet um."""
        await interaction.response.defer()
        if interaction.guild is None:
            return

        allowed, msg = await self._ensure_bot_permissions(interaction)
        if not allowed:
            await interaction.followup.send(
                embed=error_embed("Fehlende Berechtigungen", msg or "Der Bot kann hier nicht antworten."),
            )
            return

        settings = await self.db.get_guild_settings(interaction.guild.id)
        name_error = validate_pet_name(neuer_name, settings.bad_words if settings.bad_word_filter else None)
        if name_error:
            await interaction.followup.send(embed=error_embed("Ungültiger Name", name_error))
            return

        remaining = await self._cooldown_remaining(
            interaction.guild.id, interaction.user.id, PetCooldownType.RENAME
        )
        if remaining is not None:
            days = int(remaining.total_seconds() // 86400)
            hours = int((remaining.total_seconds() % 86400) // 3600)
            await interaction.followup.send(
                embed=error_embed(
                    "Cooldown",
                    f"Du kannst den Namen erst in **{days}d {hours}h** wieder ändern.",
                ),
            )
            return

        pet = await self.db.get_active_pet(interaction.guild.id, interaction.user.id)
        if pet is None:
            await interaction.followup.send(
                embed=info_embed("Kein aktives Pet", "Du hast kein aktives Pet zum Umbenennen."),
            )
            return

        old_name = pet.name
        pet.name = neuer_name.strip()
        await self.db.save_pet(pet)
        await self._set_cooldown(
            interaction.guild.id,
            interaction.user.id,
            PetCooldownType.RENAME,
            Config.PET_RENAME_COOLDOWN,
        )
        await interaction.followup.send(
            embed=success_embed(
                "Name geändert",
                f"**{old_name}** heißt jetzt **{pet.name}**!",
            ),
        )

    @app_commands.command(name="leaderboard", description="Zeigt die besten Pets des Servers.")
    @app_commands.guild_only()
    @app_commands.describe(sortierung="Sortierung der Rangliste")
    @app_commands.choices(
        sortierung=[
            app_commands.Choice(name="Level", value="level"),
            app_commands.Choice(name="XP", value="xp"),
            app_commands.Choice(name="Interaktionen", value="interactions"),
        ]
    )
    async def leaderboard(
        self,
        interaction: discord.Interaction,
        sortierung: str = "level",
    ) -> None:
        """Zeigt Pet-Rangliste."""
        await interaction.response.defer()
        if interaction.guild is None:
            return

        sort_by = sortierung if sortierung in ("level", "xp", "interactions") else "level"
        records = await self.db.get_pet_leaderboard(
            interaction.guild.id,
            sort_by=sort_by,
            limit=Config.PET_LEADERBOARD_LIMIT,
        )
        if not records:
            await interaction.followup.send(
                embed=info_embed("Pet-Rangliste", "Noch keine Pets auf diesem Server."),
            )
            return

        sort_labels = {"level": "Level", "xp": "XP", "interactions": "Interaktionen"}
        medals = ("🥇", "🥈", "🥉")
        lines = [
            build_leaderboard_line(
                rank=index,
                pet=pet,
                owner_name=interaction.guild.get_member(pet.owner_id).display_name
                if interaction.guild.get_member(pet.owner_id)
                else f"User `{pet.owner_id}`",
                medal_prefix=medals[index - 1] if index <= 3 else f"**{index}.**",
            )
            for index, pet in enumerate(records, start=1)
        ]

        embed = build_pet_leaderboard_embed(
            interaction.guild.name,
            sort_label=sort_labels.get(sort_by, sort_by),
            lines=lines,
        )
        await interaction.followup.send(embed=embed)


class PetsListCog(commands.Cog):
    """Separater Cog für /pets (Sammlungsübersicht)."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db

    @app_commands.command(name="pets", description="Zeigt alle deine Pets und wechselt das aktive Pet.")
    @app_commands.guild_only()
    async def pets(self, interaction: discord.Interaction) -> None:
        """Zeigt die Pet-Sammlung."""
        await interaction.response.defer()
        if interaction.guild is None:
            return

        channel = interaction.channel
        if isinstance(channel, (discord.TextChannel, discord.Thread)):
            allowed, msg = bot_can_use_channel(channel, send=True, embed_links=True, read_history=True)
            if not allowed:
                await interaction.followup.send(
                    embed=error_embed("Fehlende Berechtigungen", msg or "Der Bot kann hier nicht antworten."),
                )
                return

        pets = await self.db.get_pets_by_owner(interaction.guild.id, interaction.user.id)
        if not pets:
            await interaction.followup.send(
                embed=info_embed(
                    "Keine Pets",
                    f"{interaction.user.mention} hat noch keine Pets.\nÖffne dein erstes Ei mit **`/pet ei`**!",
                ),
            )
            return

        embed = build_pet_collection_embed(interaction.user.display_name, pets)
        view = PetSelectView(self.db, interaction.user.id, pets)
        await interaction.followup.send(embed=embed, view=view)


async def setup(bot: commands.Bot) -> None:
    """Lädt Pet-Cogs."""
    db: Database = bot.db  # type: ignore[attr-defined]
    await bot.add_cog(PetsCog(bot, db))
    await bot.add_cog(PetsListCog(bot, db))
