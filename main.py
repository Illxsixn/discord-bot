"""
Haupt-Einstiegspunkt des Discord-Bots.

Startet den Bot, initialisiert die Datenbank, lädt alle Cogs
und synchronisiert Slash Commands mit Discord.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from config import Config
from database.database import Database
from utils.embeds import install_brand_send_hooks

# Logging konfigurieren
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Path(__file__).parent / "bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("discord_bot")

# Liste aller zu ladenden Cogs (Reihenfolge: Logs vor Moderation für Referenzen)
COGS: list[str] = [
    "cogs.help",
    "cogs.changelog",
    "cogs.logs",
    "cogs.welcome",
    "cogs.leave",
    "cogs.automod",
    "cogs.moderation",
    "cogs.levels",
    "cogs.pets",
    "cogs.guess",
    "cogs.challenges",
    "cogs.reaction_roles",
    "cogs.polls",
    "cogs.giveaways",
    "cogs.tickets",
    "cogs.settings",
    "cogs.tournament",
]


class DiscordBot(commands.Bot):
    """
    Erweiterte Bot-Klasse mit Datenbank und Slash-Command-Support.

    Attributes:
        db: SQLite-Datenbankinstanz für persistente Einstellungen.
    """

    def __init__(self) -> None:
        """Initialisiert Intents und Bot-Basis."""
        intents = discord.Intents.default()
        # Pflicht-Intents für Member-Events, Moderation und Nachrichten
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        intents.moderation = True
        intents.bans = True

        super().__init__(
            command_prefix=commands.when_mentioned,  # Prefix ungenutzt – nur Slash Commands
            intents=intents,
            help_command=None,
        )
        self.db = Database()
        self._cleared_guild_ids: set[int] = set()

    async def setup_hook(self) -> None:
        """
        Wird beim Start aufgerufen: DB verbinden, Cogs laden, Commands syncen.
        """
        install_brand_send_hooks()

        # Datenbank verbinden und Schema erstellen
        await self.db.connect()
        await self.db.initialize()

        # Alle Cogs laden
        for extension in COGS:
            try:
                await self.load_extension(extension)
                logger.info("Cog geladen: %s", extension)
            except Exception as exc:
                logger.exception("Cog konnte nicht geladen werden (%s): %s", extension, exc)
                raise

        # Slash Commands global synchronisieren
        synced = await self.tree.sync()
        names = ", ".join(sorted(cmd.name for cmd in synced))
        logger.info("%d Slash Command(s) synchronisiert: %s", len(synced), names)

    async def _clear_guild_command_duplicates(self) -> None:
        """Entfernt Guild-Kopien globaler Befehle (verhindert doppelte Anzeige in Discord)."""
        for guild in self.guilds:
            if guild.id in self._cleared_guild_ids:
                continue
            try:
                self.tree.clear_commands(guild=guild)
                await self.tree.sync(guild=guild)
                self._cleared_guild_ids.add(guild.id)
                logger.info(
                    "Guild-Befehle bereinigt für '%s' — nur globale Slash Commands aktiv.",
                    guild.name,
                )
            except discord.HTTPException as exc:
                logger.warning("Guild-Bereinigung fehlgeschlagen für '%s': %s", guild.name, exc)

    async def on_ready(self) -> None:
        """Event wenn Bot erfolgreich verbunden ist."""
        assert self.user is not None
        logger.info("Bot online als %s (ID: %s)", self.user.name, self.user.id)
        logger.info("Verbunden mit %d Server(n).", len(self.guilds))

        await self._clear_guild_command_duplicates()

        # Präsenz setzen
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="/help | Slash Commands",
            )
        )

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """
        Globaler Fehlerhandler für Slash Commands.

        Args:
            interaction: Discord-Interaktion.
            error: Aufgetretener Fehler.
        """
        from utils.embeds import error_embed

        if isinstance(error, app_commands.CommandOnCooldown):
            embed = error_embed(
                "Cooldown",
                f"Bitte warte **{error.retry_after:.1f}** Sekunden.",
            )
        elif isinstance(error, app_commands.CheckFailure):
            return  # Bereits in Checks behandelt
        elif isinstance(error, app_commands.TransformerError):
            logger.warning("Slash Command Transform-Fehler: %s", error)
            embed = error_embed(
                "Ungültige Eingabe",
                "Ein Parameter konnte nicht verarbeitet werden. Bitte wähle einen Wert aus der Liste.",
            )
        elif isinstance(error, app_commands.CommandInvokeError):
            logger.exception("Slash Command Ausführungsfehler: %s", error.original)
            embed = error_embed("Befehl fehlgeschlagen", str(error.original))
        else:
            logger.exception("Slash Command Fehler: %s", error)
            embed = error_embed("Unerwarteter Fehler", str(error))

        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass

    async def close(self) -> None:
        """Schließt DB und Bot sauber."""
        await self.db.close()
        await super().close()


async def main() -> None:
    """Startet den Bot mit Validierung der Konfiguration."""
    try:
        Config.validate()
    except ValueError as exc:
        logger.error(str(exc))
        sys.exit(1)

    bot = DiscordBot()
    async with bot:
        await bot.start(Config.DISCORD_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot durch Benutzer beendet.")
    except Exception as exc:
        logger.exception("Kritischer Fehler: %s", exc)
        sys.exit(1)
