"""
Spiellogik für Tic-Tac-Toe und Connect Four.
"""

from __future__ import annotations

import json
from typing import Any

TTT_WIN_LINES: tuple[tuple[int, int, int], ...] = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
)

PLAYER_X = 1
PLAYER_O = 2


def new_ttt_board() -> list[int]:
    """Leeres 3x3-Feld (9 Zellen)."""
    return [0] * 9


def ttt_board_from_json(raw: str) -> list[int]:
    """Deserialisiert Tic-Tac-Toe-Brett."""
    data = json.loads(raw)
    return [int(x) for x in data]


def ttt_board_to_json(board: list[int]) -> str:
    """Serialisiert Tic-Tac-Toe-Brett."""
    return json.dumps(board)


def ttt_symbol(cell: int) -> str:
    """Zelle als Anzeige-Emoji."""
    if cell == PLAYER_X:
        return "❌"
    if cell == PLAYER_O:
        return "⭕"
    return "⬜"


def ttt_render(board: list[int]) -> str:
    """3x3-Gitter als Text."""
    rows = []
    for row in range(3):
        cells = [ttt_symbol(board[row * 3 + col]) for col in range(3)]
        rows.append(" ".join(cells))
    return "\n".join(rows)


def ttt_make_move(board: list[int], index: int, player: int) -> bool:
    """Setzt einen Zug; False wenn Feld belegt."""
    if index < 0 or index > 8 or board[index] != 0:
        return False
    board[index] = player
    return True


def ttt_winner(board: list[int]) -> int | None:
    """Gibt 1, 2 oder None zurück."""
    for a, b, c in TTT_WIN_LINES:
        if board[a] != 0 and board[a] == board[b] == board[c]:
            return board[a]
    return None


def ttt_is_draw(board: list[int]) -> bool:
    """True wenn das Brett voll und kein Gewinner."""
    return ttt_winner(board) is None and all(cell != 0 for cell in board)


def ttt_player_value(user_is_player1: bool) -> int:
    """Spielerwert für X (P1) oder O (P2)."""
    return PLAYER_X if user_is_player1 else PLAYER_O


def new_c4_board() -> list[list[int]]:
    """Leeres 7x6 Connect-Four-Brett (Spalten mit Reihen von unten)."""
    return [[0 for _ in range(6)] for _ in range(7)]


def c4_board_from_json(raw: str) -> list[list[int]]:
    """Deserialisiert Connect-Four-Brett."""
    data: list[list[int]] = json.loads(raw)
    return data


def c4_board_to_json(board: list[list[int]]) -> str:
    """Serialisiert Connect-Four-Brett."""
    return json.dumps(board)


def c4_drop(board: list[list[int]], column: int, player: int) -> int | None:
    """
    Wirft Spielstein in Spalte.

    Returns:
        Reihen-Index des platzierten Steins oder None wenn Spalte voll.
    """
    if column < 0 or column >= 7:
        return None
    for row in range(5, -1, -1):
        if board[column][row] == 0:
            board[column][row] = player
            return row
    return None


def c4_symbol(cell: int) -> str:
    """Zelle als Anzeige-Emoji."""
    if cell == PLAYER_X:
        return "🔴"
    if cell == PLAYER_O:
        return "🟡"
    return "⚫"


def c4_render(board: list[list[int]]) -> str:
    """Brett von oben nach unten als Text."""
    lines = []
    for row in range(5, -1, -1):
        cells = [c4_symbol(board[col][row]) for col in range(7)]
        lines.append(" ".join(cells))
    lines.append("1️⃣ 2️⃣ 3️⃣ 4️⃣ 5️⃣ 6️⃣ 7️⃣")
    return "\n".join(lines)


def c4_count_direction(
    board: list[list[int]],
    col: int,
    row: int,
    dc: int,
    dr: int,
    player: int,
) -> int:
    """Zählt zusammenhängende Steine in eine Richtung."""
    count = 0
    c, r = col + dc, row + dr
    while 0 <= c < 7 and 0 <= r < 6 and board[c][r] == player:
        count += 1
        c += dc
        r += dr
    return count


def c4_check_win(board: list[list[int]], col: int, row: int, player: int) -> bool:
    """Prüft Sieg nach letztem Zug."""
    directions = ((1, 0), (0, 1), (1, 1), (1, -1))
    for dc, dr in directions:
        total = (
            1
            + c4_count_direction(board, col, row, dc, dr, player)
            + c4_count_direction(board, col, row, -dc, -dr, player)
        )
        if total >= 4:
            return True
    return False


def c4_is_draw(board: list[list[int]]) -> bool:
    """True wenn oberste Reihe aller Spalten belegt."""
    return all(board[col][5] != 0 for col in range(7))


def c4_player_value(user_is_player1: bool) -> int:
    """Spielerwert für P1/P2."""
    return PLAYER_X if user_is_player1 else PLAYER_O
