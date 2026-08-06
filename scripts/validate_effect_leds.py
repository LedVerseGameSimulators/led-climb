#!/usr/bin/env python3
"""Authoring QA for Climb effect .led archives."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "games"))

from api.config import EFFECTS_DIR, EFFECT_FILES  # noqa: E402
from api.game_manager import _load_level_file  # noqa: E402


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    dg, go = _load_level_file(path)
    if not dg or go is None:
        return [f"{path.name}: failed to load"]
    if (go.row, go.col) != (6, 33):
        errors.append(f"{path.name}: expected 6x33, got {go.row}x{go.col}")
    if getattr(go, "play_order", True):
        errors.append(f"{path.name}: play_order must be False")
    for key, group in dg.items():
        sm = getattr(group, "start_member", ()) or ()
        for r, c in sm:
            if not (0 <= r < 6 and 0 <= c < 33):
                errors.append(f"{path.name}/{key}: cell ({r},{c}) out of bounds")
    return errors


def main() -> int:
    all_errors: list[str] = []
    for name in EFFECT_FILES:
        all_errors.extend(validate(EFFECTS_DIR / name))
    if all_errors:
        for err in all_errors:
            print(err)
        return 1
    print(f"OK: {len(EFFECT_FILES)} effect archives validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
