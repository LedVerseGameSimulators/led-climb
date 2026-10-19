"""Non-blocking audio for Climb session phases."""

from __future__ import annotations

import os
import queue
import threading
from pathlib import Path
from typing import Optional

from loguru import logger

from .config import (
    AUDIO_DIR,
    BGM_TRACK,
    TRANSITION_STINGER,
    SCORE_POSITIVE,
    SCORE_NEGATIVE,
    COUNTDOWN_TICK,
)

USE_SERIAL_HD = os.environ.get("USE_SERIAL_HD", "0") == "1"
# Venue audio on by default; tests/CI set CLIMB_AUDIO_DISABLED=1.
_AUDIO_DISABLED = os.environ.get("CLIMB_AUDIO_DISABLED", "0") == "1"


def _audio_file_usable(path: str) -> bool:
    if not path or not Path(path).is_file():
        return False
    try:
        with open(path, "rb") as fh:
            if fh.read(8).startswith(b"version "):
                logger.warning(
                    f"Audio file is a Git LFS pointer — run git lfs pull: {path}"
                )
                return False
    except OSError:
        return False
    return True


def _release_music(mixer) -> None:
    try:
        mixer.music.stop()
    except Exception:
        pass
    try:
        mixer.music.unload()
    except Exception:
        pass


class AudioManager:
    """Enqueue playback on a daemon thread; game thread never waits on mixer."""

    def __init__(self) -> None:
        self._queue: queue.Queue[tuple[str, Optional[str], Optional[int]]] = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._mixer = None
        self._enabled = False
        self._bgm_playing = False
        self._bgm_epoch = 0
        self._start_worker()

    def _start_worker(self) -> None:
        if not _AUDIO_DISABLED:
            try:
                import pygame  # type: ignore

                if not pygame.mixer.get_init():
                    pygame.mixer.init(frequency=22050, size=-16, channels=8, buffer=512)
                self._mixer = pygame.mixer
                self._enabled = True
            except Exception as exc:
                logger.warning(f"AudioManager init failed: {exc}")
        self._thread = threading.Thread(target=self._worker, daemon=True, name="climb-audio")
        self._thread.start()

    def _worker(self) -> None:
        while True:
            cmd, path, epoch = self._queue.get()
            try:
                if cmd == "stop_bgm":
                    self._stop_bgm_locked()
                elif cmd == "play_bgm" and path:
                    self._play_bgm_locked(path, epoch)
                elif cmd == "play_stinger" and path:
                    self._play_stinger_locked(path)
                elif cmd == "play_sfx" and path:
                    self._play_sfx_locked(path)
            except Exception as exc:
                logger.debug(f"AudioManager skip {cmd}: {exc}")
            finally:
                self._queue.task_done()

    def _stop_bgm_locked(self) -> None:
        self._bgm_playing = False
        if self._mixer is None:
            return
        _release_music(self._mixer)

    def _play_bgm_locked(self, path: str, epoch: Optional[int]) -> None:
        if epoch is not None and epoch != self._bgm_epoch:
            return
        if self._mixer is None or not Path(path).exists():
            self._bgm_playing = False
            return
        try:
            self._mixer.music.load(path)
            self._mixer.music.play(-1)
            self._bgm_playing = True
        except Exception as exc:
            self._bgm_playing = False
            logger.debug(f"BGM load failed: {exc}")

    def _play_stinger_locked(self, path: str) -> None:
        self._stop_bgm_locked()
        if self._mixer is None or not _audio_file_usable(path):
            logger.warning(f"Transition stinger missing or unusable: {path}")
            return
        try:
            ch = self._mixer.find_channel(True)
            if ch:
                ch.set_volume(1.0)
                ch.play(self._mixer.Sound(path))
                logger.info("Transition stinger played (sfx)")
                return
        except Exception as exc:
            logger.warning(f"Transition stinger (sfx) failed: {exc}")
        try:
            self._mixer.music.load(path)
            self._mixer.music.play(loops=0)
            logger.info("Transition stinger played (music)")
        except Exception as exc:
            logger.warning(f"Transition stinger (music) failed: {exc}")

    def _play_sfx_locked(self, path: str) -> None:
        if self._mixer is None or not Path(path).exists():
            return
        try:
            ch = self._mixer.find_channel(True)
            if ch:
                ch.play(self._mixer.Sound(path))
        except Exception:
            pass

    def _enqueue(self, cmd: str, path: Optional[str] = None, epoch: Optional[int] = None) -> None:
        self._queue.put((cmd, path, epoch))

    def stop_bgm(self) -> None:
        self._bgm_epoch += 1
        self._bgm_playing = False
        self._enqueue("stop_bgm")

    def play_bgm(self, path: Optional[Path] = None) -> None:
        epoch = self._bgm_epoch
        self._enqueue("play_bgm", str(path or BGM_TRACK), epoch)

    def teardown(self) -> None:
        """Idempotent BGM stop; safe on every game exit path."""
        self.stop_bgm()

    def play_stinger(self, path: Optional[Path] = None, phase: Optional[str] = None) -> None:
        if path is None and phase in ("level_clear", "level_fail"):
            cand = TRANSITION_STINGER.parent / f"{phase}.mp3"
            if cand.is_file():
                path = cand
        self._enqueue("play_stinger", str(path or TRANSITION_STINGER))

    def play_sfx(self, path: Path) -> None:
        self._enqueue("play_sfx", str(path))

    def play_score_positive(self) -> None:
        self.play_sfx(SCORE_POSITIVE)

    def play_score_negative(self) -> None:
        self.play_sfx(SCORE_NEGATIVE)

    def play_countdown_tick(self) -> None:
        self.play_sfx(COUNTDOWN_TICK)

    @property
    def bgm_active(self) -> bool:
        return self._bgm_playing and self._enabled

    @property
    def backend_active(self) -> bool:
        return self._enabled
