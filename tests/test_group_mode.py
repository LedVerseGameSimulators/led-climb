"""Coverage for Group-mode playlist building from games/source_group/."""

from __future__ import annotations

import os
from pathlib import Path

from api import game_manager

ROOT = Path(__file__).resolve().parents[1]
GROUP_ROOT = ROOT / "games" / "source_group"

EXPECTED = [f"B{i:02d}" for i in range(1, 11)]


def test_group_sequence_auto_is_corporate_b_series():
    seq = game_manager._build_group_level_sequence("auto")
    assert seq, "expected corporate source_group playlist"
    assert all("source_group" in p.replace("\\", "/") for p in seq)
    stems = [os.path.basename(p).rsplit(".", 1)[0] for p in seq]
    assert stems == EXPECTED


def test_group_sequence_can_start_mid_playlist():
    seq = game_manager._build_group_level_sequence("B03")
    stems = [os.path.basename(p).rsplit(".", 1)[0] for p in seq]
    assert stems[0] == "B03"
    assert "B01" not in stems
    assert "B02" not in stems
    assert stems[-1] == "B10"


def test_create_game_group_mode_is_single_player():
    mgr = game_manager.get_manager()
    gid = mgr.create_game("GUEST", "auto", "normal", mode="group")
    game = mgr.get_game(gid)
    assert game is not None
    assert game.mode == "group"
    assert game.multiplayer is False
    mgr.clear_all()
