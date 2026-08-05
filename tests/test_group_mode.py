"""Coverage for Group-mode playlist building from games/source_group/."""

from __future__ import annotations

import os
from pathlib import Path

from api import game_manager

ROOT = Path(__file__).resolve().parents[1]
GROUP_ROOT = ROOT / "games" / "source_group"


def test_group_sequence_auto_starts_at_first_seed_level():
    seq = game_manager._build_group_level_sequence("auto")
    assert seq, "expected seeded source_group playlist"
    assert all("source_group" in p.replace("\\", "/") for p in seq)
    stems = [os.path.basename(p).rsplit(".", 1)[0] for p in seq]
    assert stems[0] == "A001"
    assert "A002" in stems and "A003" in stems
    assert any(s.startswith("B") for s in stems)


def test_group_sequence_can_start_mid_playlist():
    seq = game_manager._build_group_level_sequence("A003")
    stems = [os.path.basename(p).rsplit(".", 1)[0] for p in seq]
    assert stems[0] == "A003"
    assert "A001" not in stems
    assert "A002" not in stems


def test_create_game_group_mode_is_single_player():
    mgr = game_manager.get_manager()
    gid = mgr.create_game("GUEST", "auto", "normal", mode="group")
    game = mgr.get_game(gid)
    assert game is not None
    assert game.mode == "group"
    assert game.multiplayer is False
    mgr.clear_all()
