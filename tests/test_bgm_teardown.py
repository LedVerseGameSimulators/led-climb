"""BGM teardown on every game exit path."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from unittest import mock

import pytest

from api import game_manager
from api.audio_manager import AudioManager


def _game_with_audio():
    game = object.__new__(game_manager.GameInstance)
    game.running = True
    game.current_state = {"bgm_active": False, "game_over": False}
    game.state_lock = threading.Lock()
    game.audio = AudioManager()
    game.led_table = None
    game.input_lock = threading.RLock()
    game.sim_pressed = set()
    game.accepting_input = False
    game._suppress_until_release = set()
    return game


def test_stop_bgm_enqueued_even_when_disabled():
    audio = AudioManager()
    audio._enabled = False
    audio._bgm_playing = True

    audio.stop_bgm()

    assert audio._bgm_playing is False
    assert audio.bgm_active is False


def test_teardown_is_idempotent():
    audio = AudioManager()
    audio._bgm_playing = True

    audio.teardown()
    audio.teardown()

    assert audio._bgm_playing is False
    assert audio.bgm_active is False


def test_stale_play_bgm_after_stop_is_ignored():
    audio = AudioManager()
    play_epoch = audio._bgm_epoch
    audio.stop_bgm()

    audio._play_bgm_locked(str(audio._enqueue.__self__ if False else "missing"), play_epoch)

    assert audio._bgm_playing is False


def test_play_after_stop_uses_fresh_epoch(monkeypatch):
    audio = AudioManager()
    played = []

    def fake_play(path, epoch):
        played.append((path, epoch))

    monkeypatch.setattr(audio, "_play_bgm_locked", fake_play)
    audio.play_bgm()
    first_epoch = audio._bgm_epoch
    audio.stop_bgm()
    audio.play_bgm()
    second_epoch = audio._bgm_epoch

    while not audio._queue.empty():
        time.sleep(0.01)

    time.sleep(0.05)
    assert first_epoch < second_epoch


def test_teardown_game_audio_publishes_inactive():
    game = _game_with_audio()
    game.audio._bgm_playing = True
    game.update_state(bgm_active=True)

    game_manager._teardown_game_audio(game)

    assert game.get_state()["bgm_active"] is False
    assert game.audio._bgm_playing is False


def test_clear_all_tears_down_audio():
    mgr = game_manager.get_manager()
    gid = mgr.create_game("GUEST", "auto", "normal", mode="group")
    game = mgr.get_game(gid)
    assert game is not None
    game.audio._bgm_playing = True

    mgr.clear_all()

    assert game.audio._bgm_playing is False


def test_stop_game_tears_down_audio():
    mgr = game_manager.get_manager()
    gid = mgr.create_game("GUEST", "auto", "normal", mode="group")
    game = mgr.get_game(gid)
    assert game is not None
    game.audio._bgm_playing = True
    game.update_state(bgm_active=True)

    mgr.stop_game(gid)

    assert game.audio._bgm_playing is False
    assert game.get_state()["bgm_active"] is False


def test_effect_runner_stops_bgm_when_session_already_stopped():
    from api.effect_runner import EffectRunner

    game = _game_with_audio()
    game.running = False
    game.audio._bgm_playing = True
    runner = EffectRunner(
        game,
        SimpleNamespace(),
        SimpleNamespace(led_row=6, led_col=33, led_table=[[[0, 0, 0]] * 33] * 6),
        {},
        game.audio,
        blank_floor=lambda _lt: None,
    )

    assert runner.run("countdown") is False
    assert game.audio._bgm_playing is False
