"""Tests for Tic-Tac-Toe game plugin."""

from boardgame_platform.game_api import PlayerInfo, ensure_builtin_games_loaded, get_game
from boardgame_platform.games.tictactoe import TicTacToe


ensure_builtin_games_loaded()


def _two_players() -> TicTacToe:
    players = [
        PlayerInfo(player_id="p1", nickname="Alice", seat=0),
        PlayerInfo(player_id="p2", nickname="Bob", seat=1),
    ]
    game = TicTacToe(players)
    game.setup()
    return game


def test_registered() -> None:
    cls = get_game("tictactoe")
    assert cls is TicTacToe


def test_x_wins() -> None:
    g = _two_players()
    # X: 0,1,2  O: 3,4
    assert g.apply("p1", {"cell": 0}).ok
    assert g.apply("p2", {"cell": 3}).ok
    assert g.apply("p1", {"cell": 1}).ok
    assert g.apply("p2", {"cell": 4}).ok
    assert g.apply("p1", {"cell": 2}).ok
    over = g.is_over()
    assert over.over
    assert over.winner_id == "p1"


def test_reject_wrong_turn_and_occupied() -> None:
    g = _two_players()
    assert not g.validate("p2", {"cell": 0}).ok
    assert g.apply("p1", {"cell": 0}).ok
    assert not g.validate("p1", {"cell": 1}).ok
    assert not g.validate("p2", {"cell": 0}).ok
    assert g.apply("p2", {"cell": 1}).ok


def test_draw() -> None:
    g = _two_players()
    # X O X
    # X O O
    # O X X
    moves = [
        ("p1", 0),
        ("p2", 1),
        ("p1", 2),
        ("p2", 4),
        ("p1", 3),
        ("p2", 5),
        ("p1", 7),
        ("p2", 6),
        ("p1", 8),
    ]
    for pid, cell in moves:
        assert g.apply(pid, {"cell": cell}).ok
    over = g.is_over()
    assert over.over
    assert over.winner_id is None
    assert "平局" in over.reason


def test_view_filtering_fields() -> None:
    g = _two_players()
    v = g.view(for_player="p1")
    assert v["your_symbol"] == "X"
    assert v["your_turn"] is True
    assert len(v["board"]) == 9


def test_format_board() -> None:
    text = TicTacToe.format_board([None] * 9)
    assert "0" in text and "8" in text
