"""
Connect Four (4 gewinnt) mit Discord-Buttons.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from config import Config
from database.database import Database
from database.models import BoardGameStatus, BoardGameType
from utils.board_games import (
    c4_board_from_json,
    c4_board_to_json,
    c4_check_win,
    c4_drop,
    c4_is_draw,
    c4_player_value,
    c4_render,
    new_c4_board,
)
from utils.board_game_lifecycle import build_active_game_error_embed
from utils.embeds import error_embed, info_embed, success_embed
from utils.game_locks import game_lock
from utils.game_rewards import award_game_xp, record_board_result

logger = logging.getLogger(__name__)


def _build_c4_embed(game, guild: discord.Guild, *, status: str) -> discord.Embed:
    board = c4_board_from_json(game.board_json)
    current = guild.get_member(game.current_player_id)
    current_name = current.mention if current else f"<@{game.current_player_id}>"
    p1 = guild.get_member(game.player1_id)
    p2 = guild.get_member(game.player2_id)
    return info_embed(
        "Connect Four",
        status,
        fields=[
            ("Spieler 🔴", p1.mention if p1 else f"<@{game.player1_id}>", True),
            ("Spieler 🟡", p2.mention if p2 else f"<@{game.player2_id}>", True),
            ("Am Zug", current_name, True),
            ("Spielfeld", c4_render(board), False),
        ],
    )


class C4ColumnButton(discord.ui.Button["ConnectFourBoardView"]):
    """Spalten-Button für Connect Four."""

    def __init__(self, game_id: int, column: int) -> None:
        super().__init__(
            style=discord.ButtonStyle.primary,
            label=str(column + 1),
            row=0 if column < 5 else 1,
            custom_id=f"c4:board:{game_id}:col:{column}",
        )
        self.column = column

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.view.handle_move(interaction, self.column)


class ConnectFourBoardView(discord.ui.View):
    """Interaktives Connect-Four-Spielfeld."""

    def __init__(self, cog: ConnectFourCog, game_id: int) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.game_id = game_id
        for col in range(7):
            self.add_item(C4ColumnButton(game_id, col))

    def _disable_all(self) -> None:
        for item in self.children:
            item.disabled = True

    async def handle_move(self, interaction: discord.Interaction, column: int) -> None:
        if interaction.guild is None:
            return

        async with game_lock(self.game_id):
            game = await self.cog.db.get_board_game(self.game_id)
            if game is None or game.status != BoardGameStatus.ACTIVE:
                await interaction.response.send_message(
                    embed=error_embed("Spiel beendet", "Dieses Spiel ist nicht mehr aktiv."),
                    ephemeral=True,
                )
                return

            if interaction.user.id not in (game.player1_id, game.player2_id):
                await interaction.response.send_message(
                    embed=error_embed("Nicht dein Zug", "Du nimmst an diesem Spiel nicht teil."),
                    ephemeral=True,
                )
                return

            if interaction.user.id != game.current_player_id:
                await interaction.response.send_message(
                    embed=error_embed("Nicht dein Zug", "Warte auf den Gegner."),
                    ephemeral=True,
                )
                return

            board = c4_board_from_json(game.board_json)
            player_value = c4_player_value(interaction.user.id == game.player1_id)
            row = c4_drop(board, column, player_value)
            if row is None:
                await interaction.response.send_message(
                    embed=error_embed("Spalte voll", "Diese Spalte ist bereits voll."),
                    ephemeral=True,
                )
                return

            if c4_check_win(board, column, row, player_value):
                winner_id = interaction.user.id
                await self.cog.db.update_board_game(
                    self.game_id,
                    board_json=c4_board_to_json(board),
                    status=BoardGameStatus.FINISHED,
                    winner_id=winner_id,
                )
                await record_board_result(
                    self.cog.db,
                    game.guild_id,
                    game.player1_id,
                    game.player2_id,
                    winner_id,
                    game_type=BoardGameType.CONNECT4,
                )
                winner = interaction.guild.get_member(winner_id)
                if winner is not None:
                    channel = interaction.channel if isinstance(
                        interaction.channel, (discord.TextChannel, discord.Thread)
                    ) else None
                    await award_game_xp(self.cog.bot, winner, channel=channel)
                embed = success_embed(
                    "Connect Four — Gewonnen!",
                    f"🏆 {winner.mention if winner else f'<@{winner_id}>'} hat gewonnen!",
                    fields=[("Spielfeld", c4_render(board), False)],
                )
                self._disable_all()
                self.stop()
                await interaction.response.edit_message(embed=embed, view=self)
                return

            if c4_is_draw(board):
                await self.cog.db.update_board_game(
                    self.game_id,
                    board_json=c4_board_to_json(board),
                    status=BoardGameStatus.FINISHED,
                    winner_id=None,
                    clear_winner=True,
                )
                await record_board_result(
                    self.cog.db,
                    game.guild_id,
                    game.player1_id,
                    game.player2_id,
                    None,
                    game_type=BoardGameType.CONNECT4,
                )
                embed = info_embed(
                    "Unentschieden",
                    "🤝 Das Brett ist voll — kein Gewinner.",
                    fields=[("Spielfeld", c4_render(board), False)],
                )
                self._disable_all()
                self.stop()
                await interaction.response.edit_message(embed=embed, view=self)
                return

            next_player = game.player2_id if game.current_player_id == game.player1_id else game.player1_id
            await self.cog.db.update_board_game(
                self.game_id,
                board_json=c4_board_to_json(board),
                current_player_id=next_player,
            )
            game = await self.cog.db.get_board_game(self.game_id)
            assert game is not None
            embed = _build_c4_embed(game, interaction.guild, status="Wähle eine Spalte (1–7).")
            await interaction.response.edit_message(embed=embed, view=self)


class C4ChallengeView(discord.ui.View):
    """Annahme einer Connect-Four-Herausforderung."""

    def __init__(self, cog: ConnectFourCog, game_id: int, opponent_id: int) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.game_id = game_id
        self.opponent_id = opponent_id

        accept = discord.ui.Button(
            label="Annehmen",
            style=discord.ButtonStyle.success,
            emoji="✅",
            custom_id=f"c4:challenge:{game_id}:accept",
        )
        accept.callback = self.accept
        self.add_item(accept)

        decline = discord.ui.Button(
            label="Ablehnen",
            style=discord.ButtonStyle.danger,
            emoji="❌",
            custom_id=f"c4:challenge:{game_id}:decline",
        )
        decline.callback = self.decline
        self.add_item(decline)

    async def accept(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.opponent_id:
            await interaction.response.send_message(
                embed=error_embed("Nicht für dich", "Nur der Herausgeforderte kann annehmen."),
                ephemeral=True,
            )
            return

        async with game_lock(self.game_id):
            game = await self.cog.db.get_board_game(self.game_id)
            if game is None or game.status != BoardGameStatus.PENDING:
                await interaction.response.send_message(
                    embed=error_embed("Abgelaufen", "Diese Herausforderung ist nicht mehr gültig."),
                    ephemeral=True,
                )
                return

            await self.cog.db.update_board_game(
                self.game_id,
                status=BoardGameStatus.ACTIVE,
                current_player_id=game.player1_id,
            )
            game = await self.cog.db.get_board_game(self.game_id)
            assert game is not None and interaction.guild is not None

        try:
            embed = _build_c4_embed(game, interaction.guild, status="Das Spiel beginnt — Spalte wählen!")
            view = ConnectFourBoardView(self.cog, self.game_id)
            message_id = interaction.message.id if interaction.message else None
            self.cog.bot.add_view(view, message_id=message_id)
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(embed=embed, view=view)
        except Exception:
            logger.exception("Connect-Four-Start fehlgeschlagen (Spiel %s)", self.game_id)
            await self.cog.db.update_board_game(self.game_id, status=BoardGameStatus.CANCELLED)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    embed=error_embed(
                        "Start fehlgeschlagen",
                        "Das Spiel konnte nicht gestartet werden. Bitte erneut herausfordern.",
                    ),
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    embed=error_embed(
                        "Start fehlgeschlagen",
                        "Das Spiel konnte nicht gestartet werden. Bitte erneut herausfordern.",
                    ),
                    ephemeral=True,
                )

    async def decline(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.opponent_id:
            await interaction.response.send_message(
                embed=error_embed("Nicht für dich", "Nur der Herausgeforderte kann ablehnen."),
                ephemeral=True,
            )
            return

        async with game_lock(self.game_id):
            await self.cog.db.update_board_game(self.game_id, status=BoardGameStatus.CANCELLED)

        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            embed=info_embed("Abgelehnt", f"{interaction.user.mention} hat die Herausforderung abgelehnt."),
            view=self,
        )


class ConnectFourCog(commands.Cog):
    """Connect Four Herausforderungen."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db

    async def cog_load(self) -> None:
        """Registriert offene Spiele nach Bot-Neustart."""
        count = 0
        for game in await self.db.get_open_board_games():
            if game.game_type != BoardGameType.CONNECT4:
                continue
            try:
                if game.status == BoardGameStatus.PENDING:
                    view: discord.ui.View = C4ChallengeView(self, game.id, game.player2_id)
                elif game.status == BoardGameStatus.ACTIVE:
                    view = ConnectFourBoardView(self, game.id)
                else:
                    continue
                self.bot.add_view(view, message_id=game.message_id)
                count += 1
            except Exception:
                logger.exception("Connect-Four-View konnte nicht registriert werden (Spiel %s)", game.id)
        if count:
            logger.info("Connect Four: %d persistente View(s) wiederhergestellt.", count)

    @app_commands.command(name="connect4", description="Fordert ein Mitglied zu Connect Four heraus.")
    @app_commands.guild_only()
    @app_commands.describe(spieler="Gegner auf dem Server")
    async def connect4(self, interaction: discord.Interaction, spieler: discord.Member) -> None:
        """Startet Connect-Four-Herausforderung."""
        await interaction.response.defer(ephemeral=True)
        if interaction.guild is None or interaction.channel is None:
            return

        channel = interaction.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await interaction.followup.send(
                embed=error_embed("Fehler", "Herausforderungen sind nur in Textkanälen möglich."),
                ephemeral=True,
            )
            return

        if spieler.bot or spieler.id == interaction.user.id:
            await interaction.followup.send(
                embed=error_embed("Ungültiger Gegner", "Wähle ein anderes Mitglied."),
                ephemeral=True,
            )
            return

        challenger = interaction.user if isinstance(interaction.user, discord.Member) else None
        if challenger is None:
            return

        for user_id in (challenger.id, spieler.id):
            active = await self.db.user_in_active_board_game(interaction.guild.id, user_id)
            if active is not None:
                await interaction.followup.send(
                    embed=build_active_game_error_embed(interaction.guild, active, user_id),
                    ephemeral=True,
                )
                return

        board = new_c4_board()
        game = await self.db.create_board_game(
            interaction.guild.id,
            interaction.channel.id,
            BoardGameType.CONNECT4,
            challenger.id,
            spieler.id,
            c4_board_to_json(board),
            status=BoardGameStatus.PENDING,
        )

        embed = info_embed(
            "Connect Four — Herausforderung",
            f"{challenger.mention} fordert {spieler.mention} heraus!\n"
            f"{spieler.display_name}, klicke **Annehmen**, um zu starten.",
            fields=[
                ("🔴", challenger.mention, True),
                ("🟡", spieler.mention, True),
            ],
        )
        view = C4ChallengeView(self, game.id, spieler.id)
        message = await channel.send(embed=embed, view=view)
        self.bot.add_view(view, message_id=message.id)
        await self.db.update_board_game(game.id, message_id=message.id)
        await interaction.followup.send(
            embed=success_embed(
                "Herausforderung gesendet",
                f"{spieler.mention} kann die Anfrage im Kanal annehmen oder ablehnen.",
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    """Lädt Connect Four."""
    db: Database = bot.db  # type: ignore[attr-defined]
    await bot.add_cog(ConnectFourCog(bot, db))
