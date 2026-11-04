"""Process bookkeeping + STOP — equivalent of STOP_GAME.bat."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable, List

from api.runtime_paths import install_root

from . import kiosk
from .product import API_PORT, SLUG, STOP_PORTS

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def logs_dir() -> Path:
    d = install_root() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def pidfile() -> Path:
    return logs_dir() / "supervisor.pid.json"


def write_pids(pids: Iterable[int]) -> None:
    pidfile().write_text(json.dumps({"pids": sorted(set(pids))}), encoding="utf-8")


def _read_pids() -> List[int]:
    try:
        return [int(p) for p in json.loads(pidfile().read_text(encoding="utf-8")).get("pids", [])]
    except (OSError, ValueError):
        return []


def kill_tree(pid: int) -> None:
    if pid == os.getpid():
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            creationflags=CREATE_NO_WINDOW,
            capture_output=True,
        )
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def free_ports(ports: Iterable[int] = STOP_PORTS) -> None:
    if sys.platform == "win32":
        plist = ",".join(str(p) for p in ports)
        ps = (
            f"foreach ($p in {plist}) {{ Get-NetTCPConnection -LocalPort $p -State Listen "
            "-ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess "
            "-Force -ErrorAction SilentlyContinue } }"
        )
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps],
            creationflags=CREATE_NO_WINDOW,
            capture_output=True,
        )
        return
    for p in ports:
        out = subprocess.run(
            ["lsof", "-ti", f"tcp:{p}", "-sTCP:LISTEN"], capture_output=True, text=True
        ).stdout.split()
        for pid in out:
            kill_tree(int(pid))


def _blank_floor() -> None:
    """STOP_GAME.bat parity: end the active game via the API so the LEDs get a black frame."""
    import urllib.request

    base = f"http://localhost:{API_PORT}"
    try:
        with urllib.request.urlopen(f"{base}/active-game", timeout=2) as r:
            a = json.loads(r.read())
        if a.get("success"):
            body = json.dumps({"card_id": a.get("card_id"), "game_id": a.get("game_id")}).encode()
            req = urllib.request.Request(
                f"{base}/logout", data=body, headers={"Content-Type": "application/json"}, method="POST"
            )
            urllib.request.urlopen(req, timeout=4).read()
            time.sleep(1)
    except Exception:
        pass


def stop_all() -> None:
    """Kill supervisor + children, the kiosk browser, and anything holding our ports."""
    _blank_floor()
    for pid in _read_pids():
        kill_tree(pid)
    kiosk.kill_kiosk(SLUG)
    free_ports()
    try:
        pidfile().unlink()
    except OSError:
        pass
