"""T9: AudioManager must not block the caller."""

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("USE_SERIAL_HD", "0")


def test_audio_manager_enqueue_returns_immediately():
    from api.audio_manager import AudioManager

    audio = AudioManager()
    start = time.perf_counter()
    for _ in range(20):
        audio.play_stinger()
        audio.play_bgm()
        audio.stop_bgm()
    elapsed = time.perf_counter() - start
    assert elapsed < 0.5
