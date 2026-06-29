"""
Hilfsfunktionen für Brettspiel-Lebenszyklus: Fehlermeldungen, Abbruch, Cleanup.
"""

from __future__ import annotations

import logging

import discord

from database.database import Database
from database.models import BoardGameRecord, BoardGameStatus, BoardGameType
from utils.embeds import error_embed, info_embed

logger = logging.getLogger(__name__)

GAME_TYPE_LABELS: dict[BoardGameType, str] = {
    BoardGameType.TICTACTOE: "Tic-Tac-Toe",
    BoardGameType.CONNECT4: "Connect Four",
}

STATUS_LABELS: dict[BoardGameStatus, str] = {
    BoardGameStatus.PENDING: "Herausforderung offen",
    BoardGameStatus.ACTIVE: "Läuft",
}


def game_type_label(game_type: BoardGameType) -> str:
    """Lesbarer Spielname."""
    return GAME_TYPE_LABELS.get(game_type, game_type.value)


def status_label(status: BoardGameStatus) -> str:
    """Lesbarer Status."""
    return STATUS_LABELS.get(status, status.value)


def build_active_game_error_embed(
    guild: discord.Guild,
    game: BoardGameRecord,
    blocked_user_id: int,
) -> discord.Embed:
    """Embed, wenn ein Spieler durch ein offenes Spiel blockiert ist."""
    blocked = guild.get_member(blocked_user_id)
    blocked_name = blocked.mention if blocked else f"<@{blocked_user_id}>"
    opponent_id = game.player2_id if blocked_user_id == game.player1_id else game.player1_id
    opponent = guild.get_member(opponent_id)
    opponent_name = opponent.mention if opponent else f"<@{opponent_id}>"
    created = discord.utils.format_dt(game.created_at, "R")

    return error_embed(
        "Aktives Spiel",
        f"{blocked_name} ist bereits in einem **{game_type_label(game.game_type)}**-Spiel.\n\n"
        f"**Status:** {status_label(game.status)}\n"
        f"**Gegner:** {opponent_name}\n"
        f"**Spiel-ID:** `#{game.id}`\n"
        f"**Gestartet:** {created}\n\n"
        "Nutze `/game cancel`, um das Spiel zu beenden.",
    )


async def finalize_cancelled_game_message(
    bot: discord.Client,
    game: BoardGameRecord,
    *,
    cancelled_by: discord.Member | None = None,
) -> None:
    """Aktualisiert die Spielnachricht nach Abbruch und deaktiviert Buttons."""
    if game.message_id is None:
        return

    guild = bot.get_guild(game.guild_id)
    if guild is None:
        return

    channel = guild.get_channel(game.channel_id)
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        return

    try:
        message = await channel.fetch_message(game.message_id)
    except (discord.NotFound, discord.Forbidden):
        return
    except discord.HTTPException:
        logger.warning("Spielnachricht #%s konnte nicht geladen werden.", game.message_id)
        return

    who = cancelled_by.mention if cancelled_by else "Ein Administrator"
    embed = info_embed(
        f"{game_type_label(game.game_type)} — Abgebrochen",
        f"{who} hat das Spiel abgebrochen.",
    )
    empty_view = discord.ui.View(timeout=None)

    try:
        await message.edit(embed=embed, view=empty_view)
    except discord.HTTPException:
        logger.warning("Spielnachricht #%s konnte nicht aktualisiert werden.", game.message_id)


async def cleanup_stale_board_games(bot: discord.Client, db: Database) -> int:
    """
    Bricht offene Spiele ab, deren Nachricht fehlt oder nie gesendet wurde.

    Returns:
        Anzahl abgebrochener Spiele.
    """
    cancelled = 0
    for game in await db.get_open_board_games():
        should_cancel = False

        if game.message_id is None:
            should_cancel = True
        else:
            guild = bot.get_guild(game.guild_id)
            if guild is None:
                continue

            channel = guild.get_channel(game.channel_id)
            if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                should_cancel = True
            else:
                try:
                    await channel.fetch_message(game.message_id)
                except discord.NotFound:
                    should_cancel = True
                except discord.Forbidden:
                    should_cancel = True
                except discord.HTTPException:
                    logger.warning(
                        "Cleanup übersprungen für Spiel #%s (Nachricht nicht erreichbar).",
                        game.id,
                    )

        if should_cancel:
            await db.update_board_game(game.id, status=BoardGameStatus.CANCELLED)
            cancelled += 1
            logger.info(
                "Verwaistes Brettspiel #%s (%s) automatisch abgebrochen.",
                game.id,
                game_type_label(game.game_type),
            )

    return cancelled
