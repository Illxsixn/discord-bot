"""
Tic-Tac-Toe mit Herausforderungen und Discord-Buttons.
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
    PLAYER_X,
    new_ttt_board,
    ttt_board_from_json,
    ttt_board_to_json,
    ttt_is_draw,
    ttt_make_move,
    ttt_player_value,
    ttt_render,
    ttt_symbol,
    ttt_winner,
)
from utils.board_game_lifecycle import build_active_game_error_embed
from utils.embeds import error_embed, info_embed, success_embed
from utils.game_locks import game_lock
from utils.game_rewards import award_game_xp, record_board_result

logger = logging.getLogger(__name__)


def _player_label(guild: discord.Guild, user_id: int) -> str:
    member = guild.get_member(user_id)
    return member.display_name if member else f"<@{user_id}>"


def _build_ttt_embed(game, guild: discord.Guild, *, status: str) -> discord.Embed:
    board = ttt_board_from_json(game.board_json)
    current = guild.get_member(game.current_player_id)
    current_name = current.mention if current else f"<@{game.current_player_id}>"
    p1 = guild.get_member(game.player1_id)
    p2 = guild.get_member(game.player2_id)
    return info_embed(
        "Tic-Tac-Toe",
        status,
        fields=[
            ("Spieler ❌", p1.mention if p1 else f"<@{game.player1_id}>", True),
            ("Spieler ⭕", p2.mention if p2 else f"<@{game.player2_id}>", True),
            ("Am Zug", current_name, True),
            ("Spielfeld", ttt_render(board), False),
        ],
    )


class TTTMoveButton(discord.ui.Button["TicTacToeBoardView"]):
    """Einzelnes Feld auf dem 3x3-Brett."""

    def __init__(self, game_id: int, index: int, label: str, *, disabled: bool = False) -> None:
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label=label,
            row=index // 3,
            disabled=disabled,
            custom_id=f"ttt:board:{game_id}:cell:{index}",
        )
        self.index = index

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.view.handle_move(interaction, self.index)


class TicTacToeBoardView(discord.ui.View):
    """Interaktives Tic-Tac-Toe-Spielfeld."""

    def __init__(self, cog: TicTacToeCog, game_id: int) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.game_id = game_id
        self._sync_buttons(new_ttt_board())

    def _sync_buttons(self, board: list[int]) -> None:
        self.clear_items()
        for index in range(9):
            cell = board[index]
            if cell == 0:
                self.add_item(TTTMoveButton(self.game_id, index, str(index + 1)))
            else:
                self.add_item(
                    TTTMoveButton(
                        self.game_id,
                        index,
                        ttt_symbol(cell).replace("⬜", "·"),
                        disabled=True,
                    )
                )

    async def handle_move(self, interaction: discord.Interaction, index: int) -> None:
        if interaction.guild is None or interaction.user is None:
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

            board = ttt_board_from_json(game.board_json)
            player_value = ttt_player_value(interaction.user.id == game.player1_id)
            if not ttt_make_move(board, index, player_value):
                await interaction.response.send_message(
                    embed=error_embed("Ungültig", "Dieses Feld ist bereits belegt."),
                    ephemeral=True,
                )
                return

            winner_value = ttt_winner(board)
            if winner_value is not None:
                winner_id = game.player1_id if winner_value == PLAYER_X else game.player2_id
                await self.cog.db.update_board_game(
                    self.game_id,
                    board_json=ttt_board_to_json(board),
                    status=BoardGameStatus.FINISHED,
                    winner_id=winner_id,
                )
                await record_board_result(
                    self.cog.db,
                    game.guild_id,
                    game.player1_id,
                    game.player2_id,
                    winner_id,
                    game_type=BoardGameType.TICTACTOE,
                )
                winner = interaction.guild.get_member(winner_id)
                if winner is not None:
                    channel = interaction.channel if isinstance(
                        interaction.channel, (discord.TextChannel, discord.Thread)
                    ) else None
                    await award_game_xp(self.cog.bot, winner, channel=channel)
                embed = success_embed(
                    "Gewonnen!",
                    f"🏆 {winner.mention if winner else f'<@{winner_id}>'} hat Tic-Tac-Toe gewonnen!",
                    fields=[("Spielfeld", ttt_render(board), False)],
                )
                self._sync_buttons(board)
                for item in self.children:
                    item.disabled = True
                self.stop()
                await interaction.response.edit_message(embed=embed, view=self)
                return

            if ttt_is_draw(board):
                await self.cog.db.update_board_game(
                    self.game_id,
                    board_json=ttt_board_to_json(board),
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
                    game_type=BoardGameType.TICTACTOE,
                )
                embed = info_embed(
                    "Unentschieden",
                    "🤝 Kein Gewinner — das Brett ist voll.",
                    fields=[("Spielfeld", ttt_render(board), False)],
                )
                self._sync_buttons(board)
                for item in self.children:
                    item.disabled = True
                self.stop()
                await interaction.response.edit_message(embed=embed, view=self)
                return

            next_player = game.player2_id if game.current_player_id == game.player1_id else game.player1_id
            await self.cog.db.update_board_game(
                self.game_id,
                board_json=ttt_board_to_json(board),
                current_player_id=next_player,
            )
            game = await self.cog.db.get_board_game(self.game_id)
            assert game is not None
            embed = _build_ttt_embed(game, interaction.guild, status="Wähle ein Feld.")
            self._sync_buttons(board)
            await interaction.response.edit_message(embed=embed, view=self)

class TTTChallengeView(discord.ui.View):
    """Annahme einer Tic-Tac-Toe-Herausforderung."""

    def __init__(self, cog: TicTacToeCog, game_id: int, opponent_id: int) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.game_id = game_id
        self.opponent_id = opponent_id

        accept = discord.ui.Button(
            label="Annehmen",
            style=discord.ButtonStyle.success,
            emoji="✅",
            custom_id=f"ttt:challenge:{game_id}:accept",
        )
        accept.callback = self.accept
        self.add_item(accept)

        decline = discord.ui.Button(
            label="Ablehnen",
            style=discord.ButtonStyle.danger,
            emoji="❌",
            custom_id=f"ttt:challenge:{game_id}:decline",
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

        embed = _build_ttt_embed(game, interaction.guild, status="Das Spiel beginnt!")
        view = TicTacToeBoardView(self.cog, self.game_id)
        board = ttt_board_from_json(game.board_json)
        view._sync_buttons(board)
        self.cog.bot.add_view(view, message_id=interaction.message.id if interaction.message else None)
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(embed=embed, view=view)

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


class TicTacToeCog(commands.Cog):
    """Tic-Tac-Toe Herausforderungen."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db

    async def cog_load(self) -> None:
        """Registriert offene Spiele nach Bot-Neustart."""
        count = 0
        for game in await self.db.get_open_board_games():
            if game.game_type != BoardGameType.TICTACTOE:
                continue
            try:
                if game.status == BoardGameStatus.PENDING:
                    view: discord.ui.View = TTTChallengeView(self, game.id, game.player2_id)
                elif game.status == BoardGameStatus.ACTIVE:
                    board_view = TicTacToeBoardView(self, game.id)
                    board_view._sync_buttons(ttt_board_from_json(game.board_json))
                    view = board_view
                else:
                    continue
                self.bot.add_view(view, message_id=game.message_id)
                count += 1
            except Exception:
                logger.exception("Tic-Tac-Toe-View konnte nicht registriert werden (Spiel %s)", game.id)
        if count:
            logger.info("Tic-Tac-Toe: %d persistente View(s) wiederhergestellt.", count)

    @app_commands.command(name="tictactoe", description="Fordert ein Mitglied zu Tic-Tac-Toe heraus.")
    @app_commands.guild_only()
    @app_commands.describe(spieler="Gegner auf dem Server")
    async def tictactoe(self, interaction: discord.Interaction, spieler: discord.Member) -> None:
        """Startet Tic-Tac-Toe-Herausforderung."""
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

        board = new_ttt_board()
        game = await self.db.create_board_game(
            interaction.guild.id,
            interaction.channel.id,
            BoardGameType.TICTACTOE,
            challenger.id,
            spieler.id,
            ttt_board_to_json(board),
            status=BoardGameStatus.PENDING,
        )

        embed = info_embed(
            "Tic-Tac-Toe — Herausforderung",
            f"{challenger.mention} fordert {spieler.mention} heraus!\n"
            f"{spieler.display_name}, klicke **Annehmen**, um zu starten.",
            fields=[
                ("❌", challenger.mention, True),
                ("⭕", spieler.mention, True),
            ],
        )
        view = TTTChallengeView(self, game.id, spieler.id)
        self.bot.add_view(view, message_id=message.id)
        message = await channel.send(embed=embed, view=view)
        await self.db.update_board_game(game.id, message_id=message.id)
        await interaction.followup.send(
            embed=success_embed(
                "Herausforderung gesendet",
                f"{spieler.mention} kann die Anfrage im Kanal annehmen oder ablehnen.",
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    """Lädt Tic-Tac-Toe."""
    db: Database = bot.db  # type: ignore[attr-defined]
    await bot.add_cog(TicTacToeCog(bot, db))
