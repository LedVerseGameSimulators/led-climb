"""Phase A multiplayer: lives-only hazards + goal color HUD publish."""

from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

from api import game_manager

ROOT = Path(__file__).resolve().parents[1]
DK01 = ROOT / "games" / "source" / "---" / "DK01.ledb"

_P1_BLUE = [0, 0, 254]
_P2_ORANGE = [254, 128, 0]


def _score_game(*, multiplayer: bool):
    game = object.__new__(game_manager.GameInstance)
    game.running = True
    game.accepting_input = True
    game._suppress_until_release = set()
    game.led_table = game_manager.HeadlessLedTable(100, 6, 33)
    game.zone = (0, 6, 0, 33)
    game.input_lock = threading.RLock()
    game.sim_pressed = set()
    game.hw_state_table = [[False] * 33 for _ in range(6)]
    game.goal_cells = set()
    game.goal2_cells = set()
    game.red_cells = set()
    game.deduct_cells = set()
    game.scored_active = set()
    game.scored_active2 = set()
    game.p2_next_cells = set()
    game.pending_respawn = []
    game.flashes = {}
    game.multiplayer = multiplayer
    game.max_life = 20
    game.life = 20
    game.score = 10
    game.score2 = 7
    game.last_life_loss_time = 0.0
    game._life_count_time = 0.0  # disable rate limit for deterministic asserts
    game._session_over = False
    game.unused_cells = set()
    game.play = None
    game.dict_group = None
    game.audio = SimpleNamespace(backend_active=False)
    game.state_lock = threading.Lock()
    game.event_lock = threading.Lock()
    game._input_events = []
    game._input_event_seq = 0
    return game


def test_create_dk01_session_is_multiplayer():
    mgr = game_manager.get_manager()
    try:
        gid = mgr.create_game("GUEST", "DK01", "normal")
        game = mgr.get_game(gid)
        assert game is not None
        assert game.multiplayer is True
        assert DK01.exists()
    finally:
        mgr.clear_all()


def test_goal_colors_published_only_when_multiplayer():
    game = _score_game(multiplayer=True)
    game.current_state = {}
    # Mirror frame-callback publish rule from GameManager._run_game.
    goal_color = _P1_BLUE if game.multiplayer else None
    goal2_color = _P2_ORANGE if game.multiplayer else None
    game.update_state(
        multiplayer=game.multiplayer,
        goal_color=goal_color,
        goal2_color=goal2_color,
    )
    state = game.get_state()
    assert state["multiplayer"] is True
    assert state["goal_color"] == _P1_BLUE
    assert state["goal2_color"] == _P2_ORANGE

    game1p = _score_game(multiplayer=False)
    game1p.current_state = {}
    game1p.update_state(
        multiplayer=False,
        goal_color=None,
        goal2_color=None,
    )
    state1p = game1p.get_state()
    assert state1p["goal_color"] is None
    assert state1p["goal2_color"] is None


def test_mp_red_life_only_scores_flat():
    game = _score_game(multiplayer=True)
    game.red_cells = {(2, 5)}
    score_before = (game.score, game.score2)
    life_before = game.life

    game_manager.GameInstance.try_score_cell(game, 2, 5)

    assert game.life == life_before - 1
    assert (game.score, game.score2) == score_before


def test_mp_deduct_life_only_scores_flat_and_consumes():
    game = _score_game(multiplayer=True)
    cell = (3, 8)
    game.deduct_cells = {cell}
    group = SimpleNamespace(
        start_member={cell},
        start_time_sec=0,
        end_time_sec=999,
    )
    game.dict_group = {"g": group}
    score_before = (game.score, game.score2)
    life_before = game.life

    game_manager.GameInstance.try_score_cell(game, *cell, total_pass=1.0)

    assert game.life == life_before - 1
    assert (game.score, game.score2) == score_before
    assert cell in game.scored_active
    assert cell not in group.start_member  # consume kept
    assert cell in game.flashes


def test_1p_red_score_and_life():
    game = _score_game(multiplayer=False)
    game.red_cells = {(2, 5)}
    score_before = game.score
    life_before = game.life

    game_manager.GameInstance.try_score_cell(game, 2, 5)

    assert game.life == life_before - 1
    assert game.score == score_before - 1
    assert game.score2 == 7  # untouched in 1P


def test_1p_deduct_score_only_no_life_and_consumes():
    game = _score_game(multiplayer=False)
    cell = (3, 8)
    game.deduct_cells = {cell}
    group = SimpleNamespace(
        start_member={cell},
        start_time_sec=0,
        end_time_sec=999,
    )
    game.dict_group = {"g": group}
    score_before = game.score
    life_before = game.life

    game_manager.GameInstance.try_score_cell(game, *cell, total_pass=1.0)

    assert game.life == life_before
    assert game.score == score_before - 1
    assert cell in game.scored_active
    assert cell not in group.start_member


def test_dk01_has_p1_p2_and_red_floor_colors():
    """Content smoke: Team Battle level carries blue/orange goals + red hazards."""
    groups, _level = game_manager._load_level_file(DK01)
    mains = {
        game_manager._group_main_color(getattr(g, "color", (0, 0, 0)))
        for g in groups.values()
    }
    assert (0, 0, 254) in mains
    assert (254, 128, 0) in mains
    assert (254, 0, 0) in mains


def test_frame_callback_publish_constants_match_hud():
    """Guard the hard-coded HUD colors used in the live frame callback."""
    src = Path(game_manager.__file__).read_text(encoding="utf-8")
    assert "_goal_color = [0, 0, 254] if game.multiplayer else None" in src
    assert "_goal2_color = [254, 128, 0] if game.multiplayer else None" in src
