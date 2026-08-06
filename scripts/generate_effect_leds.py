#!/usr/bin/env python3
"""Bootstrap native 6×33 effect .led archives for Power Climb."""

from __future__ import annotations

import argparse
import os
import shelve
import sys
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GAMES_ROOT = REPO_ROOT / "games"
sys.path.insert(0, str(GAMES_ROOT / "game_play"))
sys.path.insert(0, str(GAMES_ROOT))

from model.game import Game  # noqa: E402
from model.group import Group  # noqa: E402
from model.setting import Color, Setting  # noqa: E402

BLUE = Color.BLUE
GREEN = Color.GREEN
RED = Color.RED


def _rect(r0: int, r1: int, c0: int, c1: int) -> list[tuple[int, int]]:
    return [(r, c) for r in range(r0, r1) for c in range(c0, c1)]


def _group(name, cells, color, start, end, *, speed=0.0):
    return Group(
        name,
        list(cells),
        0,
        float(start),
        0,
        float(end),
        color,
        speed,
        Setting.DISAPPEAR,
        Setting.DISAPPEAR,
        Setting.FLOOR_LIGHT,
        [],
        Setting.SIDE_NONE,
        1,
        [(0, Setting.ROW), (0, Setting.COL)],
    )


def _game_obj(row: int = 6, col: int = 33) -> Game:
    g = Game(
        "effect",
        row,
        col,
        Setting.STANDARD,
        0,
        row,
        0,
        col,
        Setting.NO,
        Setting.NO,
        Setting.NO,
        0,
    )
    g.play_order = False
    return g


def _write_archive(out_path: Path, folder: str, game_obj: Game, groups: dict) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        sub = Path(tmp) / folder
        sub.mkdir()
        gf = str(sub / "game_file")
        db = shelve.open(gf)
        db["para_key_game"] = game_obj
        db["dict_group"] = groups
        db.close()
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(tmp):
                for fname in files:
                    fp = Path(root) / fname
                    zf.write(fp, fp.relative_to(tmp).as_posix())


def build_countdown(*, step_sec: float = 0.8, go_sec: float = 1.2) -> dict:
    t0, t1, t2, t3 = 0.0, step_sec, 2 * step_sec, 3 * step_sec
    end = t3 + go_sec
    center_digit = [(2, 15), (2, 16), (3, 15), (3, 16), (4, 15), (4, 16)]
    return {
        "step3_left": _group("step3_left", _rect(0, 6, 0, 13), BLUE, t0, t1),
        "step3_center_fill": _group("step3_center_fill", _rect(0, 6, 13, 20), BLUE, t0, t1),
        "step3_digit": _group("step3_digit", center_digit, GREEN, t0, t1),
        "step2_center_fill": _group("step2_center_fill", _rect(0, 6, 13, 20), BLUE, t1, t2),
        "step2_digit": _group("step2_digit", center_digit, GREEN, t1, t2),
        "step1_center_fill": _group("step1_center_fill", _rect(0, 6, 13, 20), BLUE, t2, t3),
        "step1_digit": _group("step1_digit", center_digit, GREEN, t2, t3),
        "step1_right": _group("step1_right", _rect(0, 6, 20, 33), BLUE, t2, t3),
        "go_left": _group("go_left", _rect(0, 6, 0, 13), BLUE, t3, end),
        "go_center_fill": _group("go_center_fill", _rect(0, 6, 13, 20), BLUE, t3, end),
        "go_digit": _group("go_digit", center_digit, GREEN, t3, end),
        "go_right": _group("go_right", _rect(0, 6, 20, 33), BLUE, t3, end),
    }


def build_solid(color, hold_sec: float) -> dict:
    cells = _rect(0, 6, 0, 33)
    return {"hold": _group("hold", cells, color, 0.0, hold_sec)}


def generate_all(out_dir: Path, *, fast: bool = False) -> None:
    step = 0.08 if fast else 0.8
    go = 0.12 if fast else 1.2
    hold = 0.25 if fast else 2.5
    folder = "effect_fast" if fast else "effect"
    _write_archive(out_dir / "countdown.led", folder, _game_obj(), build_countdown(step_sec=step, go_sec=go))
    _write_archive(out_dir / "level_clear.led", folder, _game_obj(), build_solid(BLUE, hold))
    _write_archive(out_dir / "level_fail.led", folder, _game_obj(), build_solid(RED, hold))


def build_tiny_level(name: str = "TINY", hold_sec: float = 30.0) -> None:
    """Minimal gameplay level for effects integration tests."""
    cells = [(3, 16), (3, 17), (4, 16), (4, 17)]
    groups = {
        "goal": _group("goal", cells, BLUE, 0.0, hold_sec, speed=0.0),
    }
    out = REPO_ROOT / "tests" / "fixtures" / "levels" / f"{name}.led"
    _write_archive(out, name, _game_obj(6, 24), groups)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fast", action="store_true", help="Short timelines for pytest")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    if args.out:
        out_dir = args.out
    elif args.fast:
        out_dir = REPO_ROOT / "tests" / "fixtures" / "effects"
    else:
        out_dir = GAMES_ROOT / "source" / "effects"
    generate_all(out_dir, fast=args.fast)
    if args.fast:
        build_tiny_level("TINY", hold_sec=30.0)
        build_tiny_level("TINY2", hold_sec=30.0)
    print(f"Wrote effects to {out_dir}")


if __name__ == "__main__":
    main()
