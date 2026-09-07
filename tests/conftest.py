"""Headless pytest setup for Climb level archives and API imports."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GAMES_ROOT = REPO_ROOT / "games"

for path in (REPO_ROOT, GAMES_ROOT):
    path_string = str(path)
    if path_string not in sys.path:
        sys.path.insert(0, path_string)

os.environ["USE_SERIAL_HD"] = "0"
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ.setdefault("CLIMB_AUDIO_DISABLED", "1")
