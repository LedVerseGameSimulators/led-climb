"""Phase B multiplayer: either-player wave advance + vacuous-empty latch."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from api import game_manager

ROOT = Path(__file__).resolve().parents[1]
DK01 = ROOT / "games" / "source" / "---" / "DK01.ledb"
DK02 = ROOT / "games" / "source" / "---" / "DK02.ledb"

_P1 = game_manager._MP_P1_COLOR
_P2 = game_manager._MP_P2_COLOR
_FLOOR = game_manager._FLOOR_LIGHT


def _rings(rgb):
    return [rgb, rgb, rgb]


def _group(name, rgb, cells, *, start=0.0, end=100.0):
    return SimpleNamespace(
        name=name,
        type=_FLOOR,
        color=_rings(rgb),
        start_member=set(cells),
        start_time_sec=start,
        end_time_sec=end,
    )


def _mp_game(*, multiplayer=True):
    game = object.__new__(game_manager.GameInstance)
    game.multiplayer = multiplayer
    game.unused_cells = set()
    game._mp_wave_had_p1 = False
    game._mp_wave_had_p2 = False
    return game


def test_vacuous_empty_p2_does_not_discard_p1():
    """P1-only wave: empty P2 must not count as P2 cleared."""
    groups = {
        "p1": _group("p1", _P1, {(1, 1)}, start=0.0, end=50.0),
    }
    game = _mp_game()
    advanced = game_manager._mp_try_either_player_advance(
        game,
        groups,
        total_pass=5.0,
        goal_cells={(1, 1)},
        goal2_cells=set(),
    )
    assert advanced is False
    assert groups["p1"].start_member == {(1, 1)}


def test_p1_clears_discards_p2_current_wave():
    groups = {
        "p1": _group("p1", _P1, set(), start=0.0, end=50.0),
        "p2": _group("p2", _P2, {(2, 2), (2, 3)}, start=0.0, end=50.0),
    }
    game = _mp_game()
    game._mp_wave_had_p1 = True
    game._mp_wave_had_p2 = True

    advanced = game_manager._mp_try_either_player_advance(
        game,
        groups,
        total_pass=5.0,
        goal_cells=set(),
        goal2_cells={(2, 2), (2, 3)},
    )

    assert advanced is True
    assert groups["p2"].start_member == set()
    assert game._mp_wave_had_p1 is False
    assert game._mp_wave_had_p2 is False


def test_p2_clears_discards_p1_current_wave():
    groups = {
        "p1": _group("p1", _P1, {(1, 1)}, start=0.0, end=50.0),
        "p2": _group("p2", _P2, set(), start=0.0, end=50.0),
    }
    game = _mp_game()
    game._mp_wave_had_p1 = True
    game._mp_wave_had_p2 = True

    advanced = game_manager._mp_try_either_player_advance(
        game,
        groups,
        total_pass=5.0,
        goal_cells={(1, 1)},
        goal2_cells=set(),
    )

    assert advanced is True
    assert groups["p1"].start_member == set()


def test_discard_respects_time_window():
    """Only active-window members are discarded; future waves stay."""
    groups = {
        "p2_now": _group("p2_now", _P2, {(3, 3)}, start=0.0, end=50.0),
        "p2_later": _group("p2_later", _P2, {(4, 4)}, start=60.0, end=120.0),
    }
    game = _mp_game()
    game._mp_wave_had_p1 = True

    advanced = game_manager._mp_try_either_player_advance(
        game,
        groups,
        total_pass=5.0,
        goal_cells=set(),
        goal2_cells={(3, 3)},
    )

    assert advanced is True
    assert groups["p2_now"].start_member == set()
    assert groups["p2_later"].start_member == {(4, 4)}


def test_latch_sets_had_p2_from_active_members():
    groups = {
        "p1": _group("p1", _P1, set(), start=0.0, end=50.0),
        "p2": _group("p2", _P2, {(2, 2)}, start=0.0, end=50.0),
    }
    game = _mp_game()

    game_manager._mp_try_either_player_advance(
        game,
        groups,
        total_pass=5.0,
        goal_cells=set(),
        goal2_cells={(2, 2)},
    )

    assert game._mp_wave_had_p2 is True


def test_mp_advance_blocked_during_grace_period():
    groups = {
        "p1": _group("p1", _P1, set(), start=0.0, end=50.0),
        "p2": _group("p2", _P2, {(2, 2)}, start=0.0, end=50.0),
    }
    game = _mp_game()
    game._mp_wave_had_p1 = True

    advanced = game_manager._mp_try_either_player_advance(
        game,
        groups,
        total_pass=1.0,
        goal_cells=set(),
        goal2_cells={(2, 2)},
    )

    assert advanced is False
    assert groups["p2"].start_member == {(2, 2)}


def test_1p_does_not_use_either_player_advance():
    groups = {
        "goal": _group("goal", _P1, set(), start=0.0, end=50.0),
        "p2": _group("p2", _P2, {(2, 2)}, start=0.0, end=50.0),
    }
    game = _mp_game(multiplayer=False)
    game._mp_wave_had_p1 = True

    advanced = game_manager._mp_try_either_player_advance(
        game,
        groups,
        total_pass=5.0,
        goal_cells=set(),
        goal2_cells={(2, 2)},
    )

    assert advanced is False
    assert groups["p2"].start_member == {(2, 2)}


def test_discard_helper_matches_consume_time_filter():
    groups = {
        "p2": _group("p2", _P2, {(5, 5)}, start=10.0, end=40.0),
    }
    # Before window — nothing to discard
    assert (
        game_manager._discard_mp_current_wave_members(groups, 5.0, _P2) == 0
    )
    assert groups["p2"].start_member == {(5, 5)}
    # Inside window — discard
    assert (
        game_manager._discard_mp_current_wave_members(groups, 20.0, _P2) == 1
    )
    assert groups["p2"].start_member == set()


def test_dk_ledb_levels_exist_for_manual_qa():
    assert DK01.exists()
    assert DK02.exists()


def test_dk01_loads_as_multiplayer():
    groups, _level = game_manager._load_level_file(DK01)
    assert groups
    mains = {
        game_manager._group_main_color(getattr(g, "color", (0, 0, 0)))
        for g in groups.values()
    }
    assert _P1 in mains
    assert _P2 in mains
