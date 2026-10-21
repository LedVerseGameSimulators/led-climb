"""Step 0: play facts on hex_scores + save-score + poll cursor (A1)."""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def scores_db(tmp_path, monkeypatch):
    db_file = tmp_path / "setting" / "ledplaydb.sqlite"
    monkeypatch.setattr("api.database._SCORES_DB", str(db_file))
    monkeypatch.setattr("api.database._db", None)
    from api.database import Database

    return Database()


def test_old_db_gets_rfid_columns(tmp_path, monkeypatch):
    db_file = tmp_path / "setting" / "ledplaydb.sqlite"
    db_file.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_file)
    con.execute("DROP TABLE IF EXISTS hex_scores")
    con.execute(
        "CREATE TABLE hex_scores (id INTEGER PRIMARY KEY, card_id TEXT, ts TEXT, game TEXT)"
    )
    con.commit()
    con.close()

    monkeypatch.setattr("api.database._SCORES_DB", str(db_file))
    monkeypatch.setattr("api.database._db", None)
    from api.database import Database

    Database()
    con = sqlite3.connect(db_file)
    cols = {row[1] for row in con.execute("PRAGMA table_info(hex_scores)")}
    con.close()
    for name in (
        "play_mode",
        "session_id",
        "group_id",
        "roster_size_at_play",
        "roster_player_ids",
        "session_id2",
        "group_id2",
        "roster_size_at_play2",
        "roster_player_ids2",
    ):
        assert name in cols


def test_record_without_rfid_fields(scores_db):
    ok = scores_db.record_game_score(
        {"card_id": "A1", "level": "1", "score": 10, "life": 3, "time_used": 60.0}
    )
    assert ok
    rows = scores_db.get_scores_since("2000-01-01T00:00:00")
    assert len(rows) == 1
    assert rows[0]["play_mode"] is None
    assert rows[0]["session_id"] is None


def test_record_with_rfid_fields(scores_db):
    scores_db.record_game_score(
        {
            "card_id": "C1",
            "card_id2": "C2",
            "level": "2",
            "score": 40,
            "score2": 35,
            "play_mode": "team_battle",
            "session_id": 1,
            "group_id": 9,
            "roster_size_at_play": 4,
            "roster_player_ids": [10, 11, 12, 13],
            "session_id2": 2,
            "group_id2": 10,
            "roster_size_at_play2": 3,
            "roster_player_ids2": [20, 21, 22],
        }
    )
    row = scores_db.get_scores_since("2000-01-01T00:00:00")[0]
    assert row["play_mode"] == "team_battle"
    assert row["roster_size_at_play"] == 4
    assert row["roster_player_ids"] == "[10, 11, 12, 13]"


def test_get_scores_since_inclusive_cursor(scores_db):
    ts = "2026-10-20T12:00:00"
    with scores_db._scores_lock:
        con = scores_db._scores_conn()
        con.execute(
            "INSERT INTO hex_scores (card_id, level, score, ts, game) VALUES (?,?,?,?,?)",
            ("X", "1", 1, ts, "climb"),
        )
        con.commit()
        con.close()
    rows = scores_db.get_scores_since(ts)
    assert len(rows) == 1
    assert rows[0]["ts"] == ts


def test_save_score_accepts_new_fields(scores_db, monkeypatch):
    monkeypatch.setattr("api.main.db", scores_db)
    from api.main import app

    client = TestClient(app)
    resp = client.post(
        "/save-score",
        json={
            "card_id": "Z9",
            "level": "3",
            "score": 99,
            "play_mode": "quick_play",
            "session_id": 5,
            "group_id": 7,
            "roster_size_at_play": 2,
            "roster_player_ids": [1, 2],
        },
    )
    assert resp.json()["success"] is True
    row = scores_db.get_scores_since("2000-01-01T00:00:00")[-1]
    assert row["play_mode"] == "quick_play"
    assert row["group_id"] == 7


def test_logout_does_not_write_hex_scores(scores_db, monkeypatch):
    monkeypatch.setattr("api.main.db", scores_db)

    class _FakeManager:
        def stop_game(self, game_id):
            return {"success": True, "state": {"score": 500}}

    monkeypatch.setattr("api.main.game_manager", _FakeManager())
    from api.main import app

    client = TestClient(app)
    save = client.post(
        "/save-score",
        json={"card_id": "L1", "level": "1", "score": 10, "play_mode": "quick_play"},
    )
    assert save.json()["success"] is True
    assert len(scores_db.get_scores_since("2000-01-01T00:00:00")) == 1

    logout = client.post(
        "/logout",
        json={"card_id": "L1", "game_id": "fake-game-id"},
    )
    assert logout.json()["success"] is True
    assert len(scores_db.get_scores_since("2000-01-01T00:00:00")) == 1
