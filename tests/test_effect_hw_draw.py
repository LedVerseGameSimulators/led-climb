"""Physical floor must mirror transition effects (countdown/clear/fail)."""

from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from api import game_manager
from api.audio_manager import AudioManager
from api.effect_runner import EffectRunner

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_EFFECTS = ROOT / "tests" / "fixtures" / "effects"

os.environ.setdefault("CLIMB_EFFECTS_DIR", str(FIXTURE_EFFECTS))


def _mock_setting():
    class MockAttr:
        def get(self):
            return 0.9

    setting = SimpleNamespace()
    setting.leval_span = MockAttr()
    setting.blue_hide_max_time = SimpleNamespace(get=lambda: 5.0)
    setting.corner_line_start = SimpleNamespace(get=lambda: 0)
    return setting


def _game_stub():
    game = object.__new__(game_manager.GameInstance)
    game.running = True
    game._session_over = False
    game.session_start = time.time()
    game.game_time_sec = 300.0
    game.state_lock = threading.Lock()
    game.current_state = {}
    game._hw_last_draw = 0.0
    game._hw_draw_count = 0
    game.hw_state_table = [[False] * 33 for _ in range(6)]
    game.merge_input_states = mock.Mock()
    game.finish_level_transition = mock.Mock()
    game.update_state = game_manager.GameInstance.update_state.__get__(
        game, game_manager.GameInstance
    )
    return game


def _play_stub(led_table):
    from game_play.Play import Play

    return Play(led_table, _mock_setting(), lambda *_a, **_k: None, game_level=2)


@pytest.fixture
def hw_env(monkeypatch):
    """Enable serial HD with a mocked driver and observable lock."""
    driver = mock.Mock()
    lock = mock.Mock()
    lock.__enter__ = mock.Mock(return_value=None)
    lock.__exit__ = mock.Mock(return_value=False)

    monkeypatch.setattr(game_manager, "USE_SERIAL_HD", True)
    monkeypatch.setattr(game_manager, "_hw_led_control", driver)
    monkeypatch.setattr(game_manager, "_hw_layout_type", 2)
    monkeypatch.setattr(game_manager, "_hw_serial_lock", lock)
    monkeypatch.setattr(game_manager, "_HW_DRAW_INTERVAL", 0.0)

    return driver, lock


def _runner():
    led_table = game_manager.HeadlessLedTable(100, 6, 33)
    game = _game_stub()
    play = _play_stub(led_table)
    audio = AudioManager()
    audio._enabled = False
    return EffectRunner(
        game,
        play,
        led_table,
        {"grid_rows": 6, "grid_cols": 33},
        audio,
        blank_floor=mock.Mock(),
    )


def _has_non_black(frame) -> bool:
    for row in frame:
        for cell in row:
            if any(int(ch) > 0 for ch in cell[:3]):
                return True
    return False


def _draw_frames(driver) -> list:
    return [call.args[1] for call in driver.draw_screen_by_com.call_args_list]


@pytest.mark.parametrize("effect_name", ("countdown", "level_clear", "level_fail"))
def test_effect_publishes_non_black_hw_frames(hw_env, effect_name):
    driver, _lock = hw_env
    runner = _runner()
    assert runner.run(effect_name) is True

    assert driver.draw_screen_by_com.call_count > 0
    frames = _draw_frames(driver)
    assert any(_has_non_black(frame) for frame in frames)
    driver.update_screen_state_by_com.assert_not_called()
    runner.game.merge_input_states.assert_not_called()


def test_effect_hw_draw_respects_rate_limit(hw_env, monkeypatch):
    driver, _lock = hw_env
    monkeypatch.setattr(game_manager, "_HW_DRAW_INTERVAL", 1.0)
    runner = _runner()
    game = runner.game
    led_table = runner.led_table
    led_table.led_table[2][16] = [120, 40, 200]

    times = iter([100.0, 100.01, 101.1])
    monkeypatch.setattr(time, "time", lambda: next(times))

    flat = [[0, 0, 0] for _ in range(led_table.led_row * led_table.led_col)]
    flat[2 * led_table.led_col + 16] = [120, 40, 200]

    assert game_manager._hw_draw_led_display(game, led_table, flat) is True
    assert game_manager._hw_draw_led_display(game, led_table, flat) is False
    assert game_manager._hw_draw_led_display(game, led_table, flat) is True
    assert driver.draw_screen_by_com.call_count == 2


def test_effect_hw_draw_skipped_when_serial_disabled(monkeypatch):
    driver = mock.Mock()
    monkeypatch.setattr(game_manager, "USE_SERIAL_HD", False)
    monkeypatch.setattr(game_manager, "_hw_led_control", driver)

    game = _game_stub()
    led_table = game_manager.HeadlessLedTable(100, 6, 33)
    flat = [[254, 0, 0] for _ in range(led_table.led_row * led_table.led_col)]

    assert game_manager._hw_draw_led_display(game, led_table, flat) is False
    driver.draw_screen_by_com.assert_not_called()


def test_effect_hw_draw_skipped_without_driver(monkeypatch):
    driver = mock.Mock()
    monkeypatch.setattr(game_manager, "USE_SERIAL_HD", True)
    monkeypatch.setattr(game_manager, "_hw_led_control", None)

    game = _game_stub()
    led_table = game_manager.HeadlessLedTable(100, 6, 33)
    flat = [[254, 0, 0] for _ in range(led_table.led_row * led_table.led_col)]

    assert game_manager._hw_draw_led_display(game, led_table, flat) is False
    driver.draw_screen_by_com.assert_not_called()


def test_effect_hw_draw_logs_nonfatal_errors(hw_env, monkeypatch):
    driver, _lock = hw_env
    driver.draw_screen_by_com.side_effect = RuntimeError("com busy")

    game = _game_stub()
    led_table = game_manager.HeadlessLedTable(100, 6, 33)
    flat = [[10, 20, 30] for _ in range(led_table.led_row * led_table.led_col)]

    assert game_manager._hw_draw_led_display(game, led_table, flat) is False
