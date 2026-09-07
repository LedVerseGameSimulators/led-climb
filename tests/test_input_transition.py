"""Regression tests for input reset/re-arm across level transitions."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from api import game_manager

ROOT = Path(__file__).resolve().parents[1]
A001 = ROOT / "games" / "source" / "-" / "A001.led"


def _transition_game():
    game = object.__new__(game_manager.GameInstance)
    game.running = True
    game.current_level_id = "B01"
    game.current_state = {
        "game_over": False,
        "result": None,
        "life": 20,
        "display_lives": 5,
        "accepting_input": True,
    }
    game.led_table = game_manager.HeadlessLedTable(100, 6, 33)
    game.zone = (0, 6, 0, 33)
    game.input_lock = threading.RLock()
    game.sim_pressed = set()
    game.hw_state_table = [[False] * 33 for _ in range(6)]
    game.accepting_input = True
    game._suppress_until_release = set()
    game.goal_cells = {(2, 5)}
    game.goal2_cells = set()
    game.red_cells = {(3, 10)}
    game.deduct_cells = set()
    game.scored_active = set()
    game.scored_active2 = set()
    game.multiplayer = False
    game.max_life = 20
    game.life = 20
    game.score = 0
    game.score2 = 0
    game.last_life_loss_time = 0.0
    game._life_count_time = 0.5
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


def test_transition_gate_blocks_stale_input_until_new_level_is_ready():
    game = _transition_game()
    scored = []
    real_score = game_manager.GameInstance.try_score_cell.__get__(
        game, game_manager.GameInstance
    )

    def track_score(row, col, total_pass=None):
        scored.append((row, col))
        return real_score(row, col, total_pass=total_pass)

    game.try_score_cell = track_score

    game.begin_level_transition()

    assert game.apply_input(2, 5, "press") is False
    assert scored == []
    assert game.goal_cells == set()
    assert game.red_cells == set()

    game.finish_level_transition()
    game.goal_cells = {(2, 5)}

    assert game.apply_input(2, 5, "press") is True
    assert scored == [(2, 5)]
    assert game.score == 1


def test_transition_clears_effective_and_sim_pressed_state():
    game = _transition_game()
    game.led_table.state_table[2][3] = True
    game.sim_pressed.add((4, 5))

    game.begin_level_transition()

    assert not any(any(row) for row in game.led_table.state_table)
    assert game.sim_pressed == set()
    assert (2, 3) in game._suppress_until_release
    assert (4, 5) in game._suppress_until_release


def test_stale_sim_press_does_not_score_across_transition():
    game = _transition_game()
    game.sim_pressed.add((2, 5))
    game.led_table.press_cell(2, 5)
    game.goal_cells = {(2, 5)}
    game.score = 0

    game.begin_level_transition()
    game.finish_level_transition()
    game.goal_cells = {(2, 5)}
    game.led_table.press_cell(2, 5)
    game.sim_pressed.add((2, 5))

    game.try_score_cell(2, 5)
    assert game.score == 0

    game.apply_input(2, 5, "release")
    game.apply_input(2, 5, "press")
    game.try_score_cell(2, 5)
    assert game.score == 1


def test_stale_hw_press_does_not_hurt_across_transition():
    game = _transition_game()
    game.hw_state_table[3][10] = True
    game.red_cells = {(3, 10)}
    life_before = game.life

    game.begin_level_transition()
    game.finish_level_transition()
    game.red_cells = {(3, 10)}
    game.hw_state_table[3][10] = True
    game.merge_input_states()

    game.try_score_cell(3, 10)
    assert game.life == life_before

    game.hw_state_table[3][10] = False
    game.merge_input_states()
    game.hw_state_table[3][10] = True
    game.merge_input_states()
    game.try_score_cell(3, 10)
    assert game.life == life_before - 1


def test_within_level_held_red_still_rate_limits():
    game = _transition_game()
    game.red_cells = {(3, 10)}
    game.led_table.press_cell(3, 10)
    game._life_count_time = 0.01

    game.try_score_cell(3, 10)
    life_after_first = game.life
    game.try_score_cell(3, 10)
    assert game.life == life_after_first

    time.sleep(0.02)
    game.try_score_cell(3, 10)
    assert game.life == life_after_first - 1


def test_attempt_seam_gates_input_through_load_and_setup(monkeypatch):
    game = _transition_game()
    original_loader = game_manager._load_level_file
    phases = []

    def tracking_loader(level_path):
        phases.append(("load", game.accepting_input))
        return original_loader(level_path)

    def setup_consumer(groups, level):
        phases.append(("setup", game.accepting_input))

    def play_consumer(groups):
        phases.append(("play", game.accepting_input))

    monkeypatch.setattr(game_manager, "_load_level_file", tracking_loader)

    game_manager._run_level_attempt(
        A001,
        led_table=game.led_table,
        settings={
            "grid_rows": 6,
            "grid_cols": 33,
            "wall_light": False,
            "screen_light": False,
            "floor_layout_coors_no_use": [],
        },
        level_id="A001",
        setup_consumer=setup_consumer,
        play_consumer=play_consumer,
        transition_consumer=game.begin_level_transition,
        ready_consumer=game.finish_level_transition,
    )

    assert phases == [("load", False), ("setup", False), ("play", True)]
    assert game.accepting_input is False


def test_refill_life_for_restart_blocks_input_until_gameplay():
    game = _transition_game()
    game.accepting_input = True

    game.refill_life_for_restart()

    assert game.life == 20
    assert game.accepting_input is False
    assert game.apply_input(2, 5, "press") is False


def test_clear_all_resets_input_state():
    mgr = game_manager.get_manager()
    gid = mgr.create_game("GUEST", "auto", "normal", mode="group")
    game = mgr.get_game(gid)
    assert game is not None
    game.accepting_input = True
    game.sim_pressed.add((1, 1))

    mgr.clear_all()

    assert gid not in mgr.games
    assert game.accepting_input is False
    assert game.sim_pressed == set()
