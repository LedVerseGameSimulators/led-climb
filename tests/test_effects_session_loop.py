"""API marathon proofs for Climb session effects (T1–T8)."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable, Optional

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_EFFECTS = ROOT / "tests" / "fixtures" / "effects"
FIXTURE_LEVELS = ROOT / "tests" / "fixtures" / "levels"

os.environ.setdefault("USE_SERIAL_HD", "0")
os.environ.setdefault("CLIMB_EFFECTS_DIR", str(FIXTURE_EFFECTS))


def _ensure_fixtures() -> None:
    if not (FIXTURE_EFFECTS / "countdown.led").exists():
        subprocess.check_call(
            [sys.executable, str(ROOT / "scripts" / "generate_effect_leds.py"), "--fast"],
            cwd=str(ROOT),
        )


@pytest.fixture(scope="session", autouse=True)
def bootstrap_assets():
    _ensure_fixtures()
    audio_dir = ROOT / "games" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    for name in ("transition_stinger.mp3", "background_noise.mp3"):
        path = audio_dir / name
        if not path.exists():
            path.write_bytes(b"\x00" * 64)


@pytest.fixture
def client():
    from api.game_manager import get_manager
    from api.main import app

    get_manager().clear_all()
    with TestClient(app) as test_client:
        yield test_client
    get_manager().clear_all()


@pytest.fixture
def fast_session(monkeypatch):
    """Short session timer for session-end tests."""
    from api import game_manager

    _orig = game_manager.load_real_settings

    def _settings():
        s = dict(_orig())
        s["game_time_sec"] = 8.0
        return s

    monkeypatch.setattr(game_manager, "load_real_settings", _settings)


@pytest.fixture
def tiny_two_level_sequence(monkeypatch):
    seq = [str(FIXTURE_LEVELS / "TINY.led"), str(FIXTURE_LEVELS / "TINY2.led")]

    def _build(_start):
        return seq

    monkeypatch.setattr("api.game_manager._build_level_sequence", _build)


def _start(client: TestClient, level: str = "A001") -> str:
    resp = client.post(
        "/start-game",
        json={"card_id": "test-card", "level": level, "difficulty": "normal"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"], data.get("error")
    return data["game_id"]


def _state(client: TestClient, game_id: str) -> dict:
    resp = client.get(f"/game-state/{game_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"]
    return body["state"]


def _wait_phase(
    client: TestClient,
    game_id: str,
    phase: str,
    *,
    timeout: float = 20.0,
) -> dict:
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        last = _state(client, game_id)
        if last.get("phase") == phase:
            return last
        if last.get("game_over"):
            break
        time.sleep(0.05)
    pytest.fail(f"Timed out waiting for phase={phase!r}, last={last.get('phase')!r}")


def _wait_any_phase(
    client: TestClient,
    game_id: str,
    phases: Iterable[str],
    *,
    timeout: float = 20.0,
) -> dict:
    wanted = set(phases)
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        last = _state(client, game_id)
        if last.get("phase") in wanted:
            return last
        if last.get("game_over"):
            break
        time.sleep(0.05)
    pytest.fail(f"Timed out waiting for phases {wanted}, last={last.get('phase')!r}")


def _contains_subsequence(seen: list[str], expected: list[str]) -> bool:
    idx = 0
    for phase in seen:
        if phase == expected[idx]:
            idx += 1
            if idx == len(expected):
                return True
    return False


def _poll_phases(
    client: TestClient,
    game_id: str,
    expected: list[str],
    *,
    timeout: float = 30.0,
) -> list[str]:
    seen: list[str] = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = _state(client, game_id)
        phase = st.get("phase")
        if phase and (not seen or seen[-1] != phase):
            seen.append(phase)
        if _contains_subsequence(seen, expected):
            return seen
        if st.get("game_over") and _contains_subsequence(seen, expected):
            return seen
        time.sleep(0.03)
    pytest.fail(f"expected subsequence {expected}, saw {seen}")


def _game(game_id: str):
    from api.game_manager import get_manager

    game = get_manager().get_game(game_id)
    assert game is not None
    return game


def _force_level_end(game, *, cleared: bool = False, restart: bool = False, session_over: bool = False) -> None:
    if cleared:
        game._level_cleared = True
    if restart:
        game._restart_level = True
    if session_over:
        game._session_over = True
    if game.play is not None:
        game.play.running_state = False


def test_t1_session_start_reaches_gameplay(client):
    game_id = _start(client)
    _wait_any_phase(client, game_id, ("countdown",))
    st = _wait_phase(client, game_id, "playing")
    assert st["accepting_input"] is True


def test_t7_input_gated_during_countdown(client):
    game_id = _start(client)
    st = _wait_any_phase(client, game_id, ("countdown",))
    assert st.get("accepting_input") is False
    score_before = st.get("score", 0)
    life_before = st.get("life")
    resp = client.post(
        "/game-input",
        json={"game_id": game_id, "row": 3, "col": 16, "type": "press"},
    )
    assert resp.status_code == 200
    st2 = _state(client, game_id)
    assert st2.get("score", 0) == score_before
    assert st2.get("life") == life_before


def test_t8_gameplay_accepts_input(client):
    game_id = _start(client)
    _wait_phase(client, game_id, "playing")
    game = _game(game_id)
    deadline = time.time() + 15.0
    target = None
    while time.time() < deadline and target is None:
        if game.goal_cells:
            target = next(iter(game.goal_cells))
        else:
            time.sleep(0.05)
    assert target is not None, "no scoreable cell appeared during gameplay"
    r, c = target
    score_before = game.score
    resp = client.post(
        "/game-input",
        json={"game_id": game_id, "row": r, "col": c, "type": "press"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"]
    deadline = time.time() + 2.0
    while time.time() < deadline and game.score == score_before:
        time.sleep(0.05)
    assert game.score > score_before


def _wait_current_level(client, game_id, level_id, *, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = _state(client, game_id)
        if st.get("current_level") == level_id:
            return st
        time.sleep(0.05)
    pytest.fail(f"Timed out waiting for current_level={level_id!r}")


def test_t2_countdown_after_mid_session_clear(client, tiny_two_level_sequence):
    game_id = _start(client, level="TINY")
    _wait_phase(client, game_id, "playing")
    _wait_current_level(client, game_id, "TINY")
    _force_level_end(_game(game_id), cleared=True)
    _poll_phases(client, game_id, ["level_clear", "countdown", "playing"])
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if _state(client, game_id).get("current_level") == "TINY2":
            break
        time.sleep(0.05)
    assert _state(client, game_id).get("current_level") == "TINY2"


def test_t3_level_fail_restart_same_level(client, fast_session):
    game_id = _start(client, level="A001")
    _wait_phase(client, game_id, "playing")
    game = _game(game_id)
    level_before = game.current_level_id
    score_before = game.score
    game.life = 0
    game._restart_level = True
    _force_level_end(game, restart=True)
    _poll_phases(client, game_id, ["level_fail", "countdown", "playing"])
    game = _game(game_id)
    assert game.current_level_id == level_before
    assert game.score == score_before
    assert game.life == game.max_life


def test_t4_session_end_on_timer_no_countdown(client, fast_session, monkeypatch):
    seq = [str(FIXTURE_LEVELS / "TINY.led")]
    monkeypatch.setattr("api.game_manager._build_level_sequence", lambda _s: seq)
    game_id = _start(client, level="TINY")
    _wait_phase(client, game_id, "playing")
    game = _game(game_id)
    game.session_start = time.time() - game.game_time_sec - 1
    _force_level_end(game, session_over=True)
    seen = _poll_phases(client, game_id, ["black"])
    assert "countdown" not in seen


def test_t5_session_end_life_le_10s_no_fail_panel(client, fast_session, monkeypatch):
    seq = [str(FIXTURE_LEVELS / "TINY.led")]
    monkeypatch.setattr("api.game_manager._build_level_sequence", lambda _s: seq)
    game_id = _start(client, level="TINY")
    _wait_phase(client, game_id, "playing")
    game = _game(game_id)
    game.session_start = time.time() - (game.game_time_sec - 5)
    game.life = 0
    _force_level_end(game, session_over=True)
    seen = _poll_phases(client, game_id, ["black"])
    assert "level_fail" not in seen
    assert "countdown" not in seen
    assert any(p in seen for p in ("session_end", "level_clear"))


def test_t6_last_level_cleared_session_end(client, monkeypatch, fast_session):
    seq = [str(FIXTURE_LEVELS / "TINY.led")]
    monkeypatch.setattr("api.game_manager._build_level_sequence", lambda _s: seq)
    game_id = _start(client, level="TINY")
    _wait_phase(client, game_id, "playing")
    _force_level_end(_game(game_id), cleared=True)
    seen = _poll_phases(client, game_id, ["black"])
    assert "countdown" not in seen
