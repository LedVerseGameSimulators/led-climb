"""Run authored 6×33 effect mini-levels inside the marathon loop."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable, Optional

from loguru import logger

from .audio_manager import AudioManager
from .config import EFFECTS_DIR, EFFECT_FILES

ACCURACY = 0.001


def _gm():
    from . import game_manager as gm

    return gm


def resolve_effect_path(name: str) -> Path:
    filename = name if name.endswith(".led") else f"{name}.led"
    if filename not in EFFECT_FILES and not filename.endswith(".led"):
        raise FileNotFoundError(f"Unknown effect: {name}")
    path = EFFECTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Effect archive missing: {path}")
    return path


def countdown_step(total_pass: float, thresholds: tuple[float, float, float]) -> int:
    if total_pass < thresholds[0]:
        return 3
    if total_pass < thresholds[1]:
        return 2
    if total_pass < thresholds[2]:
        return 1
    return 0


def effect_duration(dict_group: dict) -> float:
    return max((float(getattr(g, "end_time_sec", 0) or 0) for g in dict_group.values()), default=0.0)


def load_effect_thresholds(path: Path) -> tuple[float, float, float]:
    """Derive 3/2/1 step boundaries from countdown group start times."""
    dg, _ = _gm()._load_level_file(path)
    if not dg:
        return (0.8, 1.6, 2.4)
    starts = sorted(
        {
            float(getattr(g, "start_time_sec", 0) or 0)
            for g in dg.values()
            if float(getattr(g, "start_time_sec", 0) or 0) > 0
        }
    )
    if len(starts) >= 3:
        return (starts[0], starts[1], starts[2])
    step = float(os.getenv("CLIMB_COUNTDOWN_STEP_SEC", "0.8"))
    return (step, 2 * step, 3 * step)


class EffectRunner:
    def __init__(
        self,
        game,
        play,
        led_table,
        settings: dict,
        audio: AudioManager,
        *,
        blank_floor: Callable,
    ) -> None:
        self.game = game
        self.play = play
        self.led_table = led_table
        self.settings = dict(settings)
        self.audio = audio
        self.blank_floor = blank_floor
        self._countdown_thresholds: Optional[tuple[float, float, float]] = None

    def _effect_settings(self) -> dict:
        s = dict(self.settings)
        s["floor_layout_coors_no_use"] = ()
        return s

    def _publish_frame(self, rows: int, cols: int) -> list:
        led_display = [[0, 0, 0] for _ in range(rows * cols)]
        grid = self.led_table.led_table
        for r in range(rows):
            for c in range(cols):
                if r < len(grid) and c < len(grid[r]):
                    mc = grid[r][c]
                    idx = r * cols + c
                    led_display[idx] = [int(mc[0]), int(mc[1]), int(mc[2])]
        self.game.update_state(led_display=led_display, grid_rows=rows, grid_cols=cols)
        _gm()._hw_draw_led_display(self.game, self.led_table, led_display)
        return led_display

    def run(
        self,
        effect_name: str,
        *,
        phase: Optional[str] = None,
        play_stinger: bool = False,
    ) -> bool:
        """Play one effect archive. Returns False if session aborted."""
        self.audio.stop_bgm()
        self.game.update_state(bgm_active=False)
        if not self.game.running:
            return False

        path = resolve_effect_path(effect_name)
        display_phase = phase or {
            "countdown": "countdown",
            "level_clear": "level_clear",
            "level_fail": "level_fail",
        }.get(effect_name, effect_name)

        if play_stinger or effect_name in ("level_clear", "level_fail"):
            self.audio.play_stinger()

        if effect_name == "countdown" and self._countdown_thresholds is None:
            self._countdown_thresholds = load_effect_thresholds(path)

        self.game.update_state(
            phase=display_phase,
            accepting_input=False,
            bgm_active=False,
            effect_name=effect_name,
            phase_step=3 if effect_name == "countdown" else None,
        )

        rows = self.led_table.led_row
        cols = self.led_table.led_col
        thresholds = self._countdown_thresholds or (0.8, 1.6, 2.4)

        def _effect_callback(_play_self, _dgroup, _time_pass, total_pass):
            if not self.game.running:
                return False
            session_elapsed = time.time() - self.game.session_start
            if session_elapsed > self.game.game_time_sec:
                self.game._session_over = True
                return False

            if effect_name == "countdown":
                step = countdown_step(total_pass, thresholds)
                prev = getattr(self, "_last_countdown_step", None)
                if step != prev and step in (3, 2, 1):
                    self.audio.play_countdown_tick()
                self._last_countdown_step = step
                self.game.update_state(phase_step=step)

            self._publish_frame(rows, cols)
            duration = effect_duration(_dgroup)
            if total_pass >= duration - ACCURACY:
                return False
            time.sleep(0.01)
            return True

        def _play_effect(dg):
            self.play.running_state = True
            self.play.total_pass = 0
            self.play.callback = _effect_callback
            self.play.running(dg)

        try:
            _gm()._run_level_attempt(
                str(path),
                led_table=self.led_table,
                settings=self._effect_settings(),
                level_id=effect_name,
                setup_consumer=lambda _g, _go: None,
                play_consumer=_play_effect,
            )
        except _gm().LevelAttemptPreparationError as exc:
            # Missing/unreadable effect must NOT abort the marathon — venue
            # play continues without the transition visual.
            logger.warning(f"Effect {effect_name} skipped: {exc}")
            self.game.update_state(
                phase="playing" if effect_name == "countdown" else display_phase,
                effect_name=None,
                phase_step=None,
            )
            return True

        if not self.game.running or self.game._session_over:
            self.blank_floor(self.led_table)
            return False
        return True

    def enter_gameplay(self) -> None:
        self.game.finish_level_transition()
        self.audio.play_bgm()
        self.game.update_state(bgm_active=self.audio.bgm_active)

    def run_session_end(self) -> None:
        if getattr(self.game, "_session_end_played", False):
            return
        self.game._session_end_played = True
        self.game.update_state(phase="session_end", accepting_input=False, bgm_active=False)
        self.run("level_clear", phase="session_end", play_stinger=True)
        self.audio.teardown()
        self.game.update_state(phase="black", accepting_input=False, bgm_active=False, effect_name=None)
        self.blank_floor(self.led_table)
