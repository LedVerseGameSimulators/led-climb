"""
Game Manager - Climb
Manages running Play instances and game state for the Climb game.
Headless: no tkinter GUI. Input via API websocket, output via LED state.
"""
import uuid
import threading
import time
import asyncio
import os
import sys
import math
import json
import shelve as _shelve
from typing import Dict, Optional
from loguru import logger
from unittest.mock import MagicMock
from .config import (
    GAME_TIMEOUT_SECONDS,
    MAX_CONCURRENT_GAMES,
    GAMES_ROOT,
    GAME_GROUP_LEVEL_DIR,
)
from .level_scaler import prepare_level_for_platform
from .audio_manager import AudioManager
from .effect_runner import EffectRunner

USE_SERIAL_HD = os.environ.get("USE_SERIAL_HD", "0") == "1"
if USE_SERIAL_HD:
    _games_dir = str(GAMES_ROOT)
    if _games_dir not in sys.path:
        sys.path.insert(0, _games_dir)

# Mock hardware/network dependencies before importing game_play
# These are not needed for headless game logic:
# - tkinter: GUI (game_running.py imports tkinter.messagebox)
# - encryption: hardware dongle check (yanqian.py checks connected pedrive at module level)
# - led.led_control: hardware LED driver
# - net: network communication

# Mock ALL external dependencies (hardware, GUI, media, etc)
# Standard approach: mock before any imports to prevent ModuleNotFoundError
mocks = {
    # GUI/Display
    'tkinter': MagicMock(),
    'tkinter.messagebox': MagicMock(),
    'tkinter.font': MagicMock(),
    'gui': MagicMock(),
    'gui.app_gui': MagicMock(),
    'gui.gui_debugging': MagicMock(),
    'gui.gui_setting': MagicMock(),
    'gui.language': MagicMock(),
    'gui2': MagicMock(),
    'gui2.gui_led_table_editor': MagicMock(),
    'gui2.gui_led_canvas2': MagicMock(),
    'gui2.gui_table_editor': MagicMock(),
    'gui2.ui_player_setting': MagicMock(),
    'gui2.ui_table': MagicMock(),
    'gui2.gui_util': MagicMock(),
    'ui_design': MagicMock(),
    # Hardware
    **({} if USE_SERIAL_HD else {
        'serial': MagicMock(),
        'serial.tools': MagicMock(),
        'serial.tools.list_ports': MagicMock(),
        'led': MagicMock(),
        'led.led_control': MagicMock(),
        'led.communication': MagicMock(),
        'led.position_convert': MagicMock(),
        'led.led_serial_thread': MagicMock(),
        'led.led_control_c': MagicMock(),
    }),
    'net': MagicMock(),
    'socket': MagicMock(),
    # Audio/Video — do NOT mock pygame/audio_play (venue BGM/SFX need real mixer)
    'moviepy': MagicMock(),
    'moviepy.editor': MagicMock(),
    'cv2': MagicMock(),
    # Input
    'pynput': MagicMock(),
    'pynput.keyboard': MagicMock(),
    'pynput.mouse': MagicMock(),
    # Encryption
    'encryption': MagicMock(),
    'encryption.yanqian': MagicMock(),
    'rsa': MagicMock(),
    'Crypto': MagicMock(),
    'Crypto.Hash': MagicMock(),
    'Crypto.Cipher': MagicMock(),
    'Crypto.PublicKey': MagicMock(),
    'Crypto.Signature': MagicMock(),
    # Database
    'mysql': MagicMock(),
    'mysql.connector': MagicMock(),
    # Image processing
    'numpy': MagicMock(),
    'PIL': MagicMock(),
    'PIL.Image': MagicMock(),
    'PIL.ImageTk': MagicMock(),
}

for mod_name, mock in mocks.items():
    sys.modules[mod_name] = mock

_HW_DEFAULT_ROWS = 6
_HW_DEFAULT_COLS = 33
_hw_led_control = None
_hw_layout_type = 0
_HW_DRAW_INTERVAL = float(os.environ.get("HW_DRAW_INTERVAL", "0.045"))
_MASKED_GOAL_GRACE = float(os.environ.get("MASKED_GOAL_GRACE", "1.0"))
_hw_serial_lock = threading.Lock()


def _normalize_rgb(cell):
    """Ensure [R,G,B] ints. Play.clear_led_table can leave nested tuples."""
    if isinstance(cell, (list, tuple)):
        if len(cell) >= 3 and isinstance(cell[0], (int, float)):
            return [int(cell[0]), int(cell[1]), int(cell[2])]
        if len(cell) == 1:
            return _normalize_rgb(cell[0])
    return [0, 0, 0]


def _hw_init():
    global _hw_led_control, _hw_layout_type
    if _hw_led_control is not None:
        return _hw_led_control
    try:
        import shelve as _s
        from led import led_control as _lc
        db = _s.open(str(GAMES_ROOT / 'setting' / 'led_parameter'), flag='r')
        list_com_info = db.get('list_com_info', [])
        layout_type   = int(db.get('led_layout_type', 0))
        no_use        = db.get('floor_layout_coors_no_use', [])
        rows          = int(float(db.get('value_high', _HW_DEFAULT_ROWS)))
        cols          = int(float(db.get('value_width', _HW_DEFAULT_COLS)))
        db.close()
        _lc.init_layout(layout_type, rows, cols, no_use)
        errors = _lc.init_com(list_com_info)
        if errors:
            logger.warning(f"HW init COM errors (non-fatal): {errors}")
        logger.info(f"Hardware ready: {len(list_com_info)} port(s), {rows}×{cols}, layout={layout_type}")
        _hw_led_control = _lc
        _hw_layout_type = layout_type
    except Exception as e:
        logger.error(f"Hardware init failed: {e}")
    return _hw_led_control


def _hw_blank_floor(led_table=None):
    """Send one all-black frame to the physical floor. Call at every game
    end/stop path (session-end, stop_game, clear_all) so the hardware
    doesn't stay stuck lit with the last drawn pattern after a game ends.
    Uses the same draw call as normal gameplay frames, gated the same way.
    """
    if not (USE_SERIAL_HD and _hw_led_control is not None):
        return
    try:
        rows = getattr(led_table, "led_row", None) or _HW_DEFAULT_ROWS
        cols = getattr(led_table, "led_col", None) or _HW_DEFAULT_COLS
        blank = [[0, 0, 0] for _ in range(cols)]
        with _hw_serial_lock:
            _hw_led_control.draw_screen_by_com(_hw_layout_type, [blank[:] for _ in range(rows)])
    except Exception as e:
        logger.warning(f"HW blank failed: {e}")

# Will import after config is set
# from game_play.Play import Play

# Climb-specific: player colors (COLOR_ARR from model/setting.py).
# Any FLOOR_LIGHT tile matching one of these scores for that player.
# 1P: all non-hazard FLOOR_LIGHT tiles are scoreable.
# 2P DK: P1=blue (0,0,254), P2=orange (254,128,0).
_CLIMB_COLOR_ARR = [
    (254, 128, 0),   # orange  - P2 in DK 2P levels
    (0, 0, 254),     # blue    - P1 in DK 2P levels
    (254, 254, 0),   # yellow
    (0, 254, 254),   # cyan
    (254, 0, 254),   # magenta
    (254, 254, 254), # white
]
_CLIMB_HAZARD_COLORS = {(254, 0, 0), (240, 0, 0)}  # RED variants

# Settings from Climb's own led_parameter shelve.
_LED_PARAM  = str(GAMES_ROOT / "setting" / "led_parameter")
_DEBUG_PARAM = str(GAMES_ROOT / "setting" / "debug_parameter")

# Sensible fallbacks if the shelve can't be read.
_SETTINGS_DEFAULTS = {
    "game_time_sec": 300.0,    # game_time_sw (min) * 60
    "life_value": 20,          # life_value_sw  (starting HP)
    "leval_span": 0.9,         # leval_span_sw  (speed span)
    "tread_red_time": 0.01,    # debug: secs on red before life loss
    "life_value_count_time": 1.2,  # debug: min secs between life losses
    "grid_rows": 6,            # value_high  — Climb is 6 rows
    "grid_cols": 33,           # value_width — Climb is 33 cols (SQUARE grid)
    "unused_cells": set(),      # logical coordinates with no wired tile
    "scode_divide_person": True,   # game_scode_divide_person
    "scode_divide_time": True,     # game_scode_divide_time
    "player_num": 1,               # player_num_sw (overridden by 2P levels)
    # Prepare/upscale inputs (also mirrored into unused_cells for runtime filtering)
    "floor_layout_coors_no_use": (),
    "wall_light": False,
    "screen_light": False,
    "corner_line_start": 0,
}

_settings_cache = None


def load_real_settings() -> dict:
    """Read game settings from the decompiled project's shelve DBs once.
    Returns a parsed dict; falls back to defaults on any error."""
    global _settings_cache
    if _settings_cache is not None:
        return _settings_cache
    s = dict(_SETTINGS_DEFAULTS)
    # led_parameter: game length, HP, speed span
    try:
        db = _shelve.open(_LED_PARAM, flag="r")
        try:
            gt = db.get("game_time_sw")
            if gt is not None:
                s["game_time_sec"] = float(gt) * 60.0   # stored in minutes
            lv = db.get("life_value_sw")
            if lv is not None:
                s["life_value"] = int(float(lv))
            ls = db.get("leval_span_sw")
            if ls is not None:
                s["leval_span"] = float(ls)
            vh = db.get("value_high")
            if vh is not None:
                s["grid_rows"] = int(float(vh))
            vw = db.get("value_width")
            if vw is not None:
                s["grid_cols"] = int(float(vw))
            no_use = db.get("floor_layout_coors_no_use")
            if no_use is not None:
                no_use_coords = [
                    (int(round(cell[0])), int(round(cell[1])))
                    for cell in no_use
                    if isinstance(cell, (list, tuple)) and len(cell) >= 2
                ]
                # Runtime input/completion filter (onsite hardware path)
                s["unused_cells"] = set(no_use_coords)
                # Level prepare/upscale strip list (static groups)
                s["floor_layout_coors_no_use"] = list(no_use_coords)
            wall_light = db.get("wall_light")
            if wall_light is not None:
                s["wall_light"] = bool(wall_light)
            screen_light = db.get("screen_light")
            if screen_light is not None:
                s["screen_light"] = bool(screen_light)
            cls = db.get("corner_line_start")
            if cls is not None:
                s["corner_line_start"] = int(float(cls))
            dp = db.get("game_scode_divide_person")
            if dp is not None:
                s["scode_divide_person"] = bool(dp)
            dt = db.get("game_scode_divide_time")
            if dt is not None:
                s["scode_divide_time"] = bool(dt)
            pn = db.get("player_num_sw")
            if pn is not None:
                s["player_num"] = int(float(pn))
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Could not read led_parameter: {e}; using defaults")
    # debug_parameter: red-penalty timing
    try:
        db = _shelve.open(_DEBUG_PARAM, flag="r")
        try:
            trt = db.get("tread_red_time")
            if trt is not None:
                s["tread_red_time"] = float(trt)
            lct = db.get("life_value_count_time")
            if lct is not None:
                s["life_value_count_time"] = float(lct)
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Could not read debug_parameter: {e}; using defaults")
    _settings_cache = s
    logger.info(f"Loaded real settings: {s}")
    return s


def _prepare_level_attempt(
    groups,
    game,
    *,
    led_table,
    settings,
    level_id,
):
    """Prepare an isolated scaled level copy for one gameplay attempt."""
    source_rows = getattr(game, "row", None)
    source_cols = getattr(game, "col", None)
    try:
        prepared_groups, prepared_game = prepare_level_for_platform(
            groups,
            game,
            target_rows=led_table.led_row,
            target_cols=led_table.led_col,
            enable_wall_light=settings.get("wall_light") is True,
            enable_screen_light=settings.get("screen_light") is True,
            floor_layout_coors_no_use=settings.get("floor_layout_coors_no_use", ()),
        )
    except Exception as exc:
        raise ValueError(f"Level {level_id} scaling failed: {exc}") from exc

    zone = (
        prepared_game.zone_row_from,
        prepared_game.zone_row_to,
        prepared_game.zone_col_from,
        prepared_game.zone_col_to,
    )
    logger.info(
        f"Level {level_id} prepared: {source_rows}x{source_cols} -> "
        f"{led_table.led_row}x{led_table.led_col}, "
        f"retained={len(prepared_groups)}, "
        f"dropped={len(groups) - len(prepared_groups)}, zone={zone}"
    )
    return prepared_groups, prepared_game


class LevelAttemptPreparationError(ValueError):
    """A level attempt could not be loaded and prepared safely."""


def _run_level_attempt(
    path,
    *,
    led_table,
    settings,
    level_id,
    setup_consumer,
    play_consumer,
    reset_consumer=None,
    transition_consumer=None,
    ready_consumer=None,
):
    """Load and prepare one fresh attempt before invoking runtime consumers."""
    if transition_consumer is not None:
        transition_consumer()
    groups, game = _load_level_file(path)
    if not groups:
        raise LevelAttemptPreparationError(
            f"Level {level_id} failed to load for attempt"
        )
    if reset_consumer is not None:
        reset_consumer()
    try:
        groups, game = _prepare_level_attempt(
            groups,
            game,
            led_table=led_table,
            settings=settings,
            level_id=level_id,
        )
    except ValueError as exc:
        raise LevelAttemptPreparationError(str(exc)) from exc

    setup_consumer(groups, game)
    if ready_consumer is not None:
        ready_consumer()
    try:
        play_consumer(groups)
    finally:
        if transition_consumer is not None:
            transition_consumer()
    return groups, game


# Level-progression tiers (dirs under source/, easy->hard). Category is
# locked by the START level's file type: .led = 1-player, .ledb = 2-player.
# A 1P session marathons only the 1P tiers and never crosses into 2P.
_TIERS_1P = ["-", "--"]      # A-series -> B-series (.led)
_TIERS_2P = ["---"]          # DK 2P (.ledb)
# Group mode: same dash-folder names as 1P, rooted at games/source_group/
_TIERS_GROUP = list(_TIERS_1P)


def _level_sort_key(p):
    stem = os.path.basename(p).rsplit(".", 1)[0]
    return (0, int(stem)) if stem.isdigit() else (1, stem.lower())


def _build_level_sequence(start_level):
    """Ordered list of level FILE PATHS forming the marathon.

    Category is locked by the START level's file type. A start level found in
    a 1P (.led) tier yields a 1P-only chain (its tier onward through
    _TIERS_1P); a start level in a 2P (.ledb) tier yields a 2P-only chain.
    Never mixes."""
    import glob as _glob
    src = str(GAMES_ROOT)
    sl = str(start_level or "").strip()

    def _chain(dirs, ext):
        return [(d, sorted(_glob.glob(os.path.join(src, "source", d, f"*.{ext}")),
                           key=_level_sort_key)) for d in dirs]

    chain_1p = _chain(_TIERS_1P, "led")
    chain_2p = _chain(_TIERS_2P, "ledb")

    def _find(chain):
        for ti, (_d, files) in enumerate(chain):
            for fi, f in enumerate(files):
                stem = os.path.basename(f).rsplit(".", 1)[0]
                if stem == sl or stem.startswith(sl):
                    return ti, fi
        return None

    loc = _find(chain_1p)
    chain = chain_1p
    if loc is None:
        loc = _find(chain_2p)
        chain = chain_2p
    if loc is None:                       # unknown start -> begin at 1P tier 0
        chain, loc = chain_1p, (0, 0)
        if not chain or not chain[0][1]:
            return []

    ti, fi = loc
    seq = list(chain[ti][1][fi:])         # remaining levels in the start tier
    for j in range(ti + 1, len(chain)):   # then all later SAME-category tiers
        seq.extend(chain[j][1])
    return seq


def _build_group_level_sequence(start_level=None):
    """Marathon paths from games/source_group/ (Group mode only, .led).

    Same progression rules as 1P tiers, but a separate admin-curated tree.
    If start_level is missing/unknown, begin at the first file of the first
    non-empty group tier.
    """
    import glob as _glob
    root = str(GAME_GROUP_LEVEL_DIR)
    sl = str(start_level or "").strip()
    if sl.lower() in ("", "auto", "none"):
        sl = ""

    chain = [
        (d, sorted(_glob.glob(os.path.join(root, d, "*.led")), key=_level_sort_key))
        for d in _TIERS_GROUP
    ]
    # Drop empty tiers so admins can leave a middle folder empty
    chain = [(d, files) for d, files in chain if files]
    if not chain:
        return []

    loc = None
    if sl:
        for ti, (_d, files) in enumerate(chain):
            for fi, f in enumerate(files):
                stem = os.path.basename(f).rsplit(".", 1)[0]
                if stem == sl or stem.startswith(sl):
                    loc = (ti, fi)
                    break
            if loc is not None:
                break
    if loc is None:
        loc = (0, 0)

    ti, fi = loc
    seq = list(chain[ti][1][fi:])
    for j in range(ti + 1, len(chain)):
        seq.extend(chain[j][1])
    return seq


def _load_level_file(path):
    """Load one .led/.ledb: unzip, find the main gameplay shelve (the one with
    play_order=False; audio/anim dirs have play_order=True), return
    (dict_group, game_obj) as in-memory objects. (None, None) on failure."""
    import zipfile, tempfile, shelve
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            with zipfile.ZipFile(path, 'r') as z:
                z.extractall(tmpdir)
            best_go = best_dg = None
            for root, _, files in os.walk(tmpdir):
                if not any(f.startswith("game_file") for f in files):
                    continue
                gf = os.path.join(root, "game_file")
                if not (
                    os.path.exists(gf + ".dat") or os.path.exists(gf + ".db")
                ):
                    continue
                try:
                    db = shelve.open(gf)
                    go = db.get("para_key_game")
                    dg = db.get("dict_group")
                    db.close()
                    if go is None or dg is None:
                        continue
                    if not getattr(go, "play_order", True):
                        return dg, go          # main gameplay — done
                    elif best_go is None:
                        best_go, best_dg = go, dg
                except Exception:
                    continue
            return best_dg, best_go
    except Exception as e:
        logger.warning(f"Could not load level file {path}: {e}")
        return None, None


class HeadlessLedTable:
    """In-memory LED table — replaces tkinter LedTable for headless API operation.
    Same interface as gui2/gui_led_table_editor.LedTable but zero GUI deps.
    Ported from LED-Hex SimulatorLedTable.
    """

    def __init__(self, wall_light_arr_len: int, led_row: int, led_col: int):
        self.led_row = led_row
        self.led_col = led_col
        self.row = led_row
        self.col = led_col
        # Floor LED colors: led_table[row][col] = [R, G, B]
        self.led_table = [[[0, 0, 0] for _ in range(led_col)] for _ in range(led_row)]
        # Tile press state: True = being stepped on
        self._state_table = [[False] * led_col for _ in range(led_row)]
        self.table_state = self._state_table   # shared ref
        self.state_table = self._state_table   # alias (game_manager callback uses this)
        self.state_2array = [[5] * led_col for _ in range(led_row)]
        self.g_wall_has_been_tread_arr2 = [[False] * led_col for _ in range(led_row)]
        # Wall arrays
        self._wall_light_arr = [[0, 0, 0] for _ in range(wall_light_arr_len)]
        self._wall_light_state_array = [False] * wall_light_arr_len
        self._wall_screen_arr = [0] * wall_light_arr_len
        # Per-tile scoring state
        self.red_table = [[False] * led_col for _ in range(led_row)]
        self.green_table = [[False] * led_col for _ in range(led_row)]
        self.safe_table = [[False] * led_col for _ in range(led_row)]
        self.deduct_table = [[False] * led_col for _ in range(led_row)]
        self.plus_table = [[None] * led_col for _ in range(led_row)]
        self.other_color_table = [[False] * led_col for _ in range(led_row)]
        self.blue_table = [[False] * led_col for _ in range(led_row)]
        self.tread_short_stay = [[None] * led_col for _ in range(led_row)]
        self.goal_color = None
        self.goal_color2 = None
        self.safe_color = None
        self.canvas = None
        self.led_coors_click = [[0, 0], False]
        self.led_coors_click_wall = [[0, 0], False]

    # ── State table ────────────────────────────────────────────────────
    def get_state_table(self):
        return self._state_table

    def get_state_2array(self):
        return self.state_2array

    def get_g_wall_has_been_tread_arr2(self):
        return self.g_wall_has_been_tread_arr2

    # ── Wall accessors ─────────────────────────────────────────────────
    def get_wall_light_arr(self):
        return self._wall_light_arr

    def get_wall_light_state_array(self):
        return self._wall_light_state_array

    def get_wall_screen_arr(self):
        return self._wall_screen_arr

    # ── Color output ───────────────────────────────────────────────────
    def set_color_table_by_set_cell(self, start_member, color) -> None:
        c = list(color) if isinstance(color, (tuple, list)) else [0, 0, 0]
        for cell in (start_member or []):
            try:
                r_idx, c_idx = int(round(cell[0])), int(round(cell[1]))
                if 0 <= r_idx < self.led_row and 0 <= c_idx < self.led_col:
                    self.led_table[r_idx][c_idx] = c[:]
            except (IndexError, TypeError, ValueError):
                pass

    def set_table_color(self, table, color=None):
        c = list(color) if isinstance(color, (tuple, list)) else [0, 0, 0]
        for row in table:
            for i in range(len(row)):
                row[i] = c[:]

    def redraw_led_table_default(self, line=0, draw_canvas=True):
        pass  # no-op: game_manager reads led_table directly

    def draw_led_color(self):
        pass

    def clear_led_table(self):
        for r in range(self.led_row):
            for c in range(self.led_col):
                self.led_table[r][c] = [0, 0, 0]
        for i in range(len(self._wall_light_arr)):
            self._wall_light_arr[i] = [0, 0, 0]
        self._wall_screen_arr = [0] * len(self._wall_light_arr)

    def screen_mouse_click_state_get(self):
        pass

    # ── Input (press/release from simulator) ──────────────────────────
    def press_cell(self, row: int, col: int):
        if 0 <= row < self.led_row and 0 <= col < self.led_col:
            self._state_table[row][col] = True

    def release_cell(self, row: int, col: int):
        if 0 <= row < self.led_row and 0 <= col < self.led_col:
            self._state_table[row][col] = False

    # ── tkinter-compat stubs ───────────────────────────────────────────
    def pack(self, **kw): pass
    def grid(self, **kw): pass
    def update(self): pass
    def update_idletasks(self): pass
    def configure(self, **kw): pass
    def config(self, **kw): pass
    def destroy(self): pass
    def bind(self, *a, **kw): pass
    def unbind(self, *a, **kw): pass
    def after(self, ms, func=None, *args):
        import threading
        if func:
            t = threading.Timer(ms / 1000.0, func, args)
            t.daemon = True
            t.start()
    def after_cancel(self, *a): pass
    def winfo_width(self): return self.led_col * 44
    def winfo_height(self): return self.led_row * 38
    def get_canvas_table_size(self): return (self.led_row, self.led_col)


def _normalize_rings(cell):
    """Normalize a led_table cell to 3 ring colors [[r,g,b],[r,g,b],[r,g,b]]
    (outer, mid, inner). Cell is normally a 3-ring list, but tolerate a flat
    (r,g,b) (broadcast to all rings)."""
    try:
        if isinstance(cell, (list, tuple)) and len(cell) > 0:
            if isinstance(cell[0], (list, tuple)):
                rings = [[int(c[0]), int(c[1]), int(c[2])] for c in cell[:3]]
                while len(rings) < 3:
                    rings.append(rings[-1])
                return rings
            # flat (r,g,b) -> all rings same
            rgb = [int(cell[0]), int(cell[1]), int(cell[2])]
            return [rgb, rgb, rgb]
    except Exception:
        pass
    return [[0, 0, 0], [0, 0, 0], [0, 0, 0]]


def _cell_is_lit(cell):
    """True if any ring of the cell has a non-zero channel."""
    for ring in _normalize_rings(cell):
        if ring[0] or ring[1] or ring[2]:
            return True
    return False


def _cell_is_red(cell):
    """True if any ring is RED-dominant ((254,0,0)-like). Red = penalty tile."""
    for r, g, b in _normalize_rings(cell):
        if r >= 200 and g < 80 and b < 80:
            return True
    return False


def _group_main_color(color):
    """A group's representative color = its middle ring (ring[1]); ring[0] is a
    constant green marker. Returns an (r,g,b) tuple."""
    rings = _normalize_rings(color)
    return tuple(rings[1])


def _rgb_is_deduct(rgb):
    """DEDUCT_COLOR (254,0,48): consume + penalty (distinct from plain red)."""
    return rgb[0] >= 200 and rgb[1] < 80 and 30 <= rgb[2] <= 90


def _rgb_is_red(rgb):
    """Plain RED (254,0,0): hazard, stays, repeats. Excludes DEDUCT (b~48)."""
    return rgb[0] >= 200 and rgb[1] < 80 and rgb[2] < 30


class HeadlessGameGUI:
    """Mock GUI parent for Play.running_new() - provides LED update callback"""

    def __init__(self, led_table):
        self.led_table = led_table

    def update_draw_led_table_idle_game(self, dict_group, total_pass=0, time_pass=0):
        """Called by Play.running_new() to update LED display"""
        try:
            if dict_group:
                for key, value in dict_group.items():
                    group = value
                    set_cell = group.start_member
                    start_time = group.start_time_sec
                    end_time = group.end_time_sec
                    if set_cell is not None and total_pass > start_time and total_pass < end_time:
                        color = getattr(group, 'color', (0, 255, 0))
                        if hasattr(self.led_table, 'set_color_table_by_set_cell'):
                            self.led_table.set_color_table_by_set_cell(set_cell, color)
        except Exception as e:
            logger.debug(f"LED update error: {e}")

    def clear_last_wall_display(self):
        """Clear display for next frame"""
        pass


class GameInstance:
    """Single running game instance"""

    def __init__(self, game_id: str, card_id: str, level: int, difficulty: str,
                 mode: str = None):
        self.game_id = game_id
        self.card_id = card_id
        self.level = level
        self.difficulty = difficulty
        self.mode = (mode or "").strip().lower() or None  # "group" or None
        self.created_at = time.time()
        self.play = None  # Play object
        self.led_table = None  # LedTable instance (for press input)
        self.dict_group = None  # level groups (for consume-on-hit)
        self.flashes = {}  # cell -> wall-clock start time (display-only hit flash)
        self.score = 0  # accumulated score from presses on lit tiles
        self.scored_active = set()  # goal cells already scored this appearance
        # Per-frame cell classification (rebuilt each frame from dict_group):
        self.goal_cells = set()    # floor cells matching P1 goal color (scoreable)
        self.goal2_cells = set()   # floor cells matching P2 goal color (2-player)
        self.red_cells = set()     # in-time red hazard cells (penalty, stays)
        self.deduct_cells = set()  # DEDUCT_COLOR cells (penalty + consume)
        self.goal_color = None     # P1 goal color (from goal_led indicator)
        self.goal2_color = None    # P2 goal color (from goal2_led indicator)
        self.score2 = 0            # P2 score (0 in single-player)
        self.scored_active2 = set()# P2 scored cells this appearance
        self.multiplayer = False   # True when level has goal2_led
        self.zone = None          # (row_from,row_to,col_from,col_to) active area
        # 2P respawn: consumed goal tiles reappear after delay (only for .ledb multiplayer)
        self.pending_respawn = []  # [[group, (i,j), reappear_wall_time], ...]
        self.respawn_delay = 8.0   # seconds; tunable
        # Same-color 2P (e.g. DK03 cyan==cyan): alternate P1→P2→P1→P2 per cell.
        # Cells in this set score P2 next; others score P1.
        self.p2_next_cells = set()
        self.input_lock = threading.RLock()
        self.sim_pressed = set()
        self.hw_state_table = None
        self.accepting_input = False  # gated until a prepared level is fully set up
        self._suppress_until_release = set()  # held-at-transition cells; ignore until release
        self.state_lock = threading.Lock()
        self.running = False

        # Real settings (game length + HP). Loaded from led_parameter.
        _s = load_real_settings()
        self.game_time_sec = _s["game_time_sec"]   # session limit (300s)

        # Runtime override pushed from the central RFID server (Settings page):
        # default_difficulty/session_minutes. Applied after the shelve-derived
        # defaults above but only takes effect for difficulty when the caller
        # didn't already pass one explicitly (StartGameRequest.difficulty is
        # required today, so this is a no-op until a caller omits it).
        _override_path = GAMES_ROOT / "setting" / "runtime_overrides.json"
        if _override_path.exists():
            try:
                with open(_override_path) as _f:
                    _overrides = json.load(_f)
                if _overrides.get("session_minutes"):
                    self.game_time_sec = float(_overrides["session_minutes"]) * 60.0
                if _overrides.get("default_difficulty") and not getattr(self, "difficulty", None):
                    self.difficulty = _overrides["default_difficulty"]
            except Exception as _e:
                logger.warning(f"Could not read runtime overrides: {_e}")

        self.board_time_sec = 1e9                   # board length (max group end); set on load
        self.result = None                          # 0 lose / 1 complete / 2 timeout
        self.max_life = _s["life_value"]           # 20 HP
        self.life = self.max_life
        # Final-score normalization (game_scode_rule): divide raw score by
        # player count and/or game-time (minutes). Applied at session end only;
        # live `score` stays raw for display.
        self._scode_divide_person = _s.get("scode_divide_person", True)
        self._scode_divide_time = _s.get("scode_divide_time", True)
        # Default 1 player; _setup_level bumps to 2 for actual 2P (DK) levels.
        # (player_num_sw is the machine's max-player config, not per-game.)
        self._player_num = 1
        self.last_life_loss_time = 0.0             # for life_value_count_time gate
        self._life_count_time = _s["life_value_count_time"]

        # ── SESSION (5-min marathon) state ──────────────────────────────
        # Score + lives persist across levels; session ends on life<=0 or
        # timer<=0. Player picks a starting level; we marathon to series end.
        self.session_start = None      # wall-clock when first level begins
        self.level_sequence = []       # ordered list of level FILE PATHS
        self.current_level_id = None   # e.g. "A005" (for frontend display)
        self.levels_cleared = 0        # how many levels finished this session
        self._session_over = False     # True -> stop the session loop
        self._level_cleared = False    # True -> advance to next level
        self._restart_level = False    # True -> replay same level (life=0, time left)
        self._no_reachable_goal_since = None
        self._end_reason = None        # why the marathon loop exited (timeout/None)
        self._session_end_played = False

        self.current_state = {
            "score": 0,
            "time_elapsed": 0.0,
            "time_left": self.game_time_sec,
            "life": self.max_life,
            "max_life": self.max_life,
            "display_lives": 5,   # always 5 hearts at full HP, whatever max_life is
            "display_max": 5,
            "score2": 0,
            "multiplayer": False,
            "player_pos": [0, 0],
            "led_display": [],
            "pressed_tiles": [],
            "input_events": [],
            "game_over": False,
            "game_over_reason": "",
            "result": None,
            "current_level": None,
            "levels_cleared": 0,
            "started_at": "",
            "phase": "idle",
            "accepting_input": False,
            "phase_step": None,
            "bgm_active": False,
            "effect_name": None,
        }
        self.audio = AudioManager()
        self.unused_cells = set(_s.get("unused_cells", set()))
        self._input_event_seq = 0
        self._input_events = []
        self.event_lock = threading.Lock()
        self.thread = None

    def compute_final_score(self, raw_score):
        """Leaderboard score normalization (faithful to game_scode_rule):
          final = raw / player_count (if divide_person) / minutes (if divide_time)
        game_time is in MINUTES (game_time_sw). Live display uses raw score;
        this is only for the saved/leaderboard result."""
        scode = float(raw_score)
        if self._scode_divide_person and self._player_num:
            scode /= self._player_num
        if self._scode_divide_time:
            minutes = self.game_time_sec / 60.0
            if minutes > 0:
                scode /= minutes
        return round(scode, 2)

    def reset_for_level(self):
        """Clear PER-LEVEL board state before loading the next level.
        Score, score2, life, session timer all PERSIST (not reset)."""
        with self.input_lock:
            self.flashes = {}
            self.scored_active = set()
            self.scored_active2 = set()
            self.pending_respawn = []
            self.p2_next_cells = set()
            self.goal_cells = set()
            self.goal2_cells = set()
            self.red_cells = set()
            self.deduct_cells = set()
            self.last_life_loss_time = 0.0
            self._level_cleared = False
            self._restart_level = False
            self._no_reachable_goal_since = None

    def _collect_pressed_cells(self) -> set:
        """Snapshot of cells currently pressed (effective, sim, or hardware)."""
        pressed = set(self.sim_pressed)
        if self.led_table is not None:
            for row_index, row in enumerate(self.led_table.state_table):
                for col_index, is_pressed in enumerate(row):
                    if is_pressed:
                        pressed.add((row_index, col_index))
        if self.hw_state_table is not None:
            for row_index, row in enumerate(self.hw_state_table):
                for col_index, is_pressed in enumerate(row):
                    if is_pressed:
                        pressed.add((row_index, col_index))
        return pressed

    def _note_input_release(self, row: int, col: int) -> None:
        self._suppress_until_release.discard((row, col))

    def begin_level_transition(self):
        """Fail closed while level geometry and classification are changing."""
        with self.input_lock:
            self.accepting_input = False
            self._suppress_until_release = self._collect_pressed_cells()
            if self.led_table is not None:
                for row in self.led_table.state_table:
                    for col_index in range(len(row)):
                        row[col_index] = False
            self.sim_pressed.clear()
            self.goal_cells = set()
            self.goal2_cells = set()
            self.red_cells = set()
            self.deduct_cells = set()
            self.scored_active = set()
            self.scored_active2 = set()
            self.flashes = {}
            self.current_state["accepting_input"] = False

    def finish_level_transition(self):
        """Enable input only after the prepared level has been installed."""
        with self.input_lock:
            if self.running and not self.current_state.get("game_over"):
                self.accepting_input = True
                self.current_state["accepting_input"] = True
                self.current_state["phase"] = "playing"
                self.current_state["phase_step"] = None
                self.current_state["effect_name"] = None

    def mark_session_failed(self, reason, error):
        """Record a terminal session error and prevent success resolution."""
        self.begin_level_transition()
        self._session_over = True
        self._end_reason = reason
        self.update_state(
            game_over=True,
            game_over_reason=reason,
            result=0,
            accepting_input=False,
        )

    def refill_life_for_restart(self):
        """Refill and publish HP immediately while the replay is prepared."""
        self.begin_level_transition()
        self.life = self.max_life
        self.last_life_loss_time = 0.0
        self.update_state(
            life=self.life,
            display_lives=5,
            current_level=self.current_level_id,
            accepting_input=False,
        )

    def _current_level_time(self) -> float:
        """Level timeline for consume/scoring (Play.total_pass)."""
        if self.play is not None:
            return float(getattr(self.play, "total_pass", 0.0))
        return 0.0

    def is_expired(self) -> bool:
        """Check if game timed out"""
        elapsed = time.time() - self.created_at
        return elapsed > GAME_TIMEOUT_SECONDS

    def get_state(self) -> dict:
        """Get current game state"""
        with self.state_lock:
            return dict(self.current_state)

    def update_state(self, **kwargs):
        """Update game state"""
        with self.state_lock:
            self.current_state.update(kwargs)

    def _record_input_event(self, row: int, col: int, source: str):
        """Record rising press edges so browser audio does not infer presses
        from sampled score changes. Keep a bounded replay window for clients."""
        with self.event_lock:
            self._input_event_seq += 1
            self._input_events.append({
                "seq": self._input_event_seq,
                "type": "press",
                "source": source,
                "row": row,
                "col": col,
            })
            if len(self._input_events) > 64:
                del self._input_events[:-64]

    def _input_event_snapshot(self):
        with self.event_lock:
            return [dict(event) for event in self._input_events]

    def is_active_cell(self, row: int, col: int) -> bool:
        if self.led_table is None:
            return False
        return (
            0 <= row < self.led_table.led_row and
            0 <= col < self.led_table.led_col and
            (row, col) not in self.unused_cells
        )

    def try_score_cell(self, i, j, total_pass=None):
        """Type-aware scoring for a press on cell (i,j):
          - red hazard cell  -> -1 point + -1 HP (HP rate-limited)
          - goal_led target  -> +1 point + consume (tile blanks) + flash
          - background decor  -> nothing (neutral)
        goal/red membership is classified per frame in the callback."""
        if not self.accepting_input:
            return
        if (i, j) in self._suppress_until_release:
            return
        if total_pass is None:
            total_pass = self._current_level_time()
        # Red hazard: penalty + HP loss (gated). Not edge-limited by
        # scored_active (standing on red keeps hurting, rate-limited by time).
        if (i, j) in self.red_cells:
            now = time.time()
            if now - self.last_life_loss_time >= self._life_count_time:
                self.score -= 1
                if self.score < 0:
                    self.score = 0
                if self.multiplayer:          # red hurts both players in 2P
                    self.score2 -= 1
                    if self.score2 < 0:
                        self.score2 = 0
                self.life -= 1
                self.last_life_loss_time = now
            return
        # DEDUCT tile: -1 SCORE only (NO life loss), then consume.
        # Faithful to original gui_editor_game.py (DEDUCT_COLOR block):
        # scode_value -= ONE_SCODE_VALUE, no life_value change.
        if (i, j) in self.deduct_cells and (i, j) not in self.scored_active:
            self.scored_active.add((i, j))
            self.score -= 1
            if self.score < 0:
                self.score = 0
            self._consume_cell(i, j, total_pass)
            return
        in_p1 = (i, j) in self.goal_cells
        in_p2 = (i, j) in self.goal2_cells
        same_color = in_p1 and in_p2   # DK03-style: both players same color

        if same_color:
            # Alternate P1→P2→P1→P2 per cell so both players score fairly.
            if (i, j) in self.p2_next_cells:
                if (i, j) not in self.scored_active2:
                    self.scored_active2.add((i, j))
                    self.score2 += 1
                    self.p2_next_cells.discard((i, j))
                    self._consume_cell(i, j, total_pass)
            else:
                if (i, j) not in self.scored_active:
                    self.scored_active.add((i, j))
                    self.score += 1
                    self.p2_next_cells.add((i, j))  # next time → P2
                    self._consume_cell(i, j, total_pass)
            return

        # P1 goal: score + consume
        if in_p1 and (i, j) not in self.scored_active:
            self.scored_active.add((i, j))
            self.score += 1
            self._consume_cell(i, j, total_pass)
            return
        # P2 goal: separate score + consume
        if in_p2 and (i, j) not in self.scored_active2:
            self.scored_active2.add((i, j))
            self.score2 += 1
            self._consume_cell(i, j, total_pass)
            return
        # else: background decor — neutral, no effect.

    def _consume_cell(self, i, j, total_pass=None):
        """Remove a stepped goal tile from the group(s) whose time window is
        CURRENTLY ACTIVE, so it blanks. No artificial respawn — consumed =
        gone (matches real game). Level completes when all scoreable tiles
        cleared. Time-staggered waves (groups with later start_times)
        provide natural progression.

        Must filter by time window: the same (row,col) coordinate is
        sometimes reused across separate groups/waves at different times
        (confirmed e.g. in A020.led). Without this filter, consuming one
        occurrence silently wipes every future occurrence sharing that
        coordinate too, ending the level early."""
        if total_pass is None:
            total_pass = self._current_level_time()
        reappear_at = None  # respawn disabled — clear progression for 1P + 2P
        if self.dict_group:
            for g in self.dict_group.values():
                sm = getattr(g, "start_member", None)
                if not sm:
                    continue
                st = getattr(g, "start_time_sec", 0)
                et = getattr(g, "end_time_sec", 0)
                if not (st <= total_pass <= et):
                    continue
                if (i, j) in sm:
                    try:
                        if isinstance(sm, set):
                            sm.discard((i, j))
                        else:
                            sm.remove((i, j))
                        if reappear_at is not None:
                            self.pending_respawn.append([g, (i, j), reappear_at])
                    except Exception:
                        pass
        # display-only hit flash (white blink) for ~0.4s
        self.flashes[(i, j)] = time.time()

    def process_respawns(self):
        """Re-add consumed 2P goal tiles after respawn_delay. Per-frame."""
        if not self.pending_respawn:
            return
        now = time.time(); still = []
        for entry in self.pending_respawn:
            g, cell, t = entry
            if now >= t:
                sm = getattr(g, "start_member", None)
                try:
                    if isinstance(sm, set): sm.add(cell)
                    elif sm is not None and cell not in sm: sm.append(cell)
                except Exception:
                    pass
            else:
                still.append(entry)
        self.pending_respawn = still

    def apply_input(self, row: int, col: int, action: str):
        """Player input from simulator: press/release a tile.
        Simulator presses are tracked separately from physical sensors, then
        merged into the effective state table so a hardware read cannot erase
        a held mouse/touch press."""
        if not self.accepting_input:
            return False
        if self.led_table is None:
            return False
        if not self.is_active_cell(row, col):
            return False
        # Ignore presses outside the level's active zone (e.g. 5x9).
        z = self.zone
        if z and not (z[0] <= row < z[1] and z[2] <= col < z[3]):
            return False
        with self.input_lock:
            if action == "press":
                was_pressed = self.led_table.state_table[row][col]
                self.sim_pressed.add((row, col))
                self.led_table.press_cell(row, col)
                if not was_pressed:
                    self._record_input_event(row, col, "simulator")
                self.try_score_cell(row, col)  # score on press (instant clicks)
            elif action == "release":
                self.sim_pressed.discard((row, col))
                self._note_input_release(row, col)
                hardware_pressed = (
                    self.hw_state_table is not None and
                    self.hw_state_table[row][col]
                )
                if hardware_pressed:
                    self.led_table.press_cell(row, col)
                else:
                    self.led_table.release_cell(row, col)
            else:
                return False
        return True

    def merge_input_states(self):
        """Merge physical and simulator input into the game-facing table."""
        if self.led_table is None or self.hw_state_table is None:
            return
        with self.input_lock:
            for row in range(self.led_table.led_row):
                for col in range(self.led_table.led_col):
                    was_pressed = self.led_table.state_table[row][col]
                    is_pressed = (
                        (row, col) not in self.unused_cells and
                        (
                            self.hw_state_table[row][col] or
                            (row, col) in self.sim_pressed
                        )
                    )
                    self.led_table.state_table[row][col] = is_pressed
                    if not is_pressed:
                        self._note_input_release(row, col)
                    elif not was_pressed and (row, col) not in self._suppress_until_release:
                        source = "simulator" if (row, col) in self.sim_pressed else "hardware"
                        self._record_input_event(row, col, source)


class GameManager:
    """Manages all running game instances"""

    def __init__(self):
        self.games: Dict[str, GameInstance] = {}
        self.lock = threading.Lock()
        self._create_lock = threading.Lock()
        self.zombie_threads = []
        logger.info("GameManager initialized")

    def clear_all(self):
        """Stop and remove all existing games. Joins threads (3s timeout) before clearing."""
        with self.lock:
            for gid, g in list(self.games.items()):
                g.begin_level_transition()
                g.running = False
            threads = [(gid, g.thread) for gid, g in self.games.items() if getattr(g, "thread", None)]
            led_tables = [g.led_table for g in self.games.values() if getattr(g, "led_table", None) is not None]
            self.games.clear()
        for gid, t in threads:
            t.join(timeout=3.0)
            if t.is_alive():
                logger.warning(f"Thread {gid} didn't stop in 3s — zombie")
                self.zombie_threads.append(gid)
        # Blank the physical floor so a stale frame doesn't linger from
        # whichever game was just cleared out (kiosk model: clear_all()
        # runs at the start of every new game via create_game()).
        for lt in led_tables:
            _hw_blank_floor(lt)
        logger.info("Cleared all existing games")

    def create_game(self, card_id: str, level: int, difficulty: str,
                    mode: str = None) -> str:
        """Create new game instance. Clears any prior games first (kiosk model)."""
        self.clear_all()
        with self.lock:
            game_id = str(uuid.uuid4())[:8]
            game = GameInstance(game_id, card_id, level, difficulty, mode=mode)

            # Eagerly set multiplayer from file extension BEFORE the load
            # thread starts, so _consume_cell respawns correctly even if
            # a press arrives before the shelve is fully loaded (~7s).
            # Group mode is always 1P (.led under source_group/).
            if game.mode != "group":
                _clone = str(GAMES_ROOT)
                _ledb = os.path.join(_clone, "source", "---", f"{level}.ledb")
                if os.path.exists(_ledb):
                    game.multiplayer = True
                    logger.info(
                        f"Game created: {game_id} multiplayer=True "
                        f"(card={card_id}, level={level})"
                    )
                else:
                    logger.info(
                        f"Game created: {game_id} (card={card_id}, level={level})"
                    )
            else:
                logger.info(
                    f"Game created: {game_id} mode=group "
                    f"(card={card_id}, level={level})"
                )

            self.games[game_id] = game
            return game_id

    def get_game(self, game_id: str) -> Optional[GameInstance]:
        """Get game by ID"""
        with self.lock:
            return self.games.get(game_id)

    def snapshot_games(self):
        """Return a stable registry snapshot for API readers."""
        with self.lock:
            return list(self.games.items())

    def get_active_game(self) -> Optional[GameInstance]:
        """Return the first live kiosk game from a stable snapshot."""
        for _game_id, game in self.snapshot_games():
            if game.running and not game.get_state().get("game_over"):
                return game
        return None

    def start_game(self, game_id: str):
        """Start game loop in background thread"""
        game = self.get_game(game_id)
        if not game:
            raise ValueError(f"Game not found: {game_id}")

        def _run_game():
            try:
                # Double-check: reinstall mocks in this thread
                if not USE_SERIAL_HD:
                    if 'serial' not in sys.modules:
                        sys.modules['serial'] = MagicMock()
                    if 'led' not in sys.modules:
                        sys.modules['led'] = MagicMock()
                    if 'led.led_control' not in sys.modules:
                        sys.modules['led.led_control'] = MagicMock()
                else:
                    _hw_init()

                logger.info(f"Starting game loop: {game_id}")

                # Import game modules (with fallback to mock loop on import error)
                Play = None
                LedTable = None
                Setting = None
                try:
                    logger.info(f"Importing game modules for {game_id}")
                    import shelve
                    import os
                    from game_play.Play import Play
                    from game_play.game_running import LedTable
                    from model.setting import Setting
                    logger.info(f"✓ Game modules imported")
                except Exception as import_err:
                    logger.warning(f"Game module import failed, using mock loop: {import_err}")
                    import traceback
                    logger.warning(f"Import traceback: {traceback.format_exc()}")
                    Play = None
                    LedTable = None
                    Setting = None
                    # If imports failed, force dict_group to None to skip to mock loop
                    dict_group = None

                # Initialize game components — always use HeadlessLedTable
                # (never the mocked gui2 LedTable — that's MagicMock, comparisons fail)
                _s = load_real_settings()
                _rows = _s.get("grid_rows", 6)
                _cols = _s.get("grid_cols", 33)
                led_table = HeadlessLedTable(wall_light_arr_len=100, led_row=_rows, led_col=_cols)
                logger.info(f"HeadlessLedTable ready: {led_table.led_row}x{led_table.led_col} (Climb square grid)")

                # Create mock settings object with required attributes
                # Climb's Play.__init__ expects setting.leval_span.get(), setting.blue_hide_max_time.get(), etc.
                class MockSetting:
                    def __init__(self):
                        class MockAttr:
                            def get(self):
                                return 0.9  # leval_span default
                        self.leval_span = MockAttr()
                        self.blue_hide_max_time = MockAttr()
                        self.blue_hide_max_time.get = lambda: 5.0
                        self.corner_line_start = MockAttr()
                        self.corner_line_start.get = lambda: 0

                mock_setting = MockSetting()

                # Create dummy callback (Play expects partial_fun_cb for UI updates)
                def dummy_callback(*args, **kwargs):
                    pass

                # game_level: numeric difficulty (1=easy, 2=normal, 3=hard), not level ID
                difficulty_map = {"easy": 1, "normal": 2, "hard": 3}
                game_level_num = difficulty_map.get(game.difficulty, 2)  # default to normal

                play = None
                try:
                    logger.debug(f"Creating Play instance for game {game_id}")
                    play = Play(led_table, mock_setting, dummy_callback, game_level=game_level_num)
                    # Sweep speed scale (cells/sec = (1/group.speed) * game_level_speed).
                    # Lower = slower sweep. Tune per difficulty to match real game pace.
                    difficulty_speed = {"easy": 0.25, "normal": 0.4, "hard": 0.6}
                    play.game_level_speed = difficulty_speed.get(game.difficulty, 0.4)
                except Exception as e:
                    logger.warning(f"Play creation failed, using mock loop: {e}")
                    play = None

                # ── SESSION SETUP ────────────────────────────────────────────
                # Build the level marathon sequence from the chosen start level
                # to the end of its series (A001..A025 / B01..B31 / DK01..DK10).
                game.play = play
                game.led_table = led_table          # expose for press input
                game.hw_state_table = [
                    [False] * led_table.led_col
                    for _ in range(led_table.led_row)
                ]
                game.session_start = time.time()
                game._end_reason = None
                import datetime as _dt
                game.update_state(started_at=_dt.datetime.now().isoformat(timespec="seconds"))
                if game.mode == "group":
                    game.level_sequence = _build_group_level_sequence(game.level)
                    # Sync display start level to first playlist entry
                    if game.level_sequence:
                        game.level = os.path.basename(
                            game.level_sequence[0]
                        ).rsplit(".", 1)[0]
                else:
                    game.level_sequence = _build_level_sequence(game.level)
                # Group mode is always 1P (.led under source_group/).
                if game.mode == "group":
                    game.multiplayer = False
                logger.info(
                    f"Session: {len(game.level_sequence)} levels from "
                    f"'{game.level}' mode={game.mode or 'single'} (5-min marathon)"
                )

                game_start_time = game.session_start  # legacy alias for mock loop

                BLACK3 = [(0, 0, 0), (0, 0, 0), (0, 0, 0)]

                def _ensure_anim(g):
                    """Pickled groups lack breath state; init it lazily so
                    group.breath() works (shimmer effect)."""
                    if not isinstance(getattr(g, "breath_color_float", None), list) \
                            or not (g.breath_color_float and isinstance(g.breath_color_float[0], (list, tuple))):
                        col = g.color if (isinstance(g.color, (list, tuple)) and g.color
                                          and isinstance(g.color[0], (list, tuple))) else BLACK3
                        g.breath_color = [list(c) for c in col]
                        g.breath_color_float = [list(c) for c in col]
                        g.breath_switch = [True, True, True]
                    if not hasattr(g, "trigger_span_tm"):
                        g.trigger_span_tm = 0

                def _setup_level(dg, go):
                    """Configure game state for a freshly-loaded level. Score,
                    score2, life, session timer all PERSIST (set elsewhere)."""
                    game.dict_group = dg
                    # Per-level board time = max group end_time.
                    try:
                        game.board_time_sec = max(
                            (getattr(g, "end_time_sec", 0) for g in dg.values()),
                            default=1e9)
                    except Exception:
                        game.board_time_sec = 1e9
                    # Play zone (guards input).
                    if go is not None:
                        try:
                            game.zone = (int(getattr(go, "zone_row_from", 0)),
                                         int(getattr(go, "zone_row_to", 16)),
                                         int(getattr(go, "zone_col_from", 0)),
                                         int(getattr(go, "zone_col_to", 26)))
                        except Exception:
                            game.zone = None
                    # Multiplayer: 2P levels have BOTH blue(P1) and orange(P2)
                    # scoreable groups. Upgrade only (never override to False).
                    _P1 = (0, 0, 254); _P2 = (254, 128, 0)
                    has_p1 = has_p2 = False
                    for g in dg.values():
                        mc = _group_main_color(g.color)
                        if mc == _P1: has_p1 = True
                        elif mc == _P2: has_p2 = True
                    if has_p1 and has_p2:
                        game.multiplayer = True
                        game._player_num = 2   # 2P: divide score by 2 players
                    # Init breath/anim state for all groups.
                    for g in dg.values():
                        try:
                            _ensure_anim(g)
                        except Exception:
                            pass

                # Per-frame callback fired by Play.update() inside Play.running().
                # By this point Play has: moved groups (deal_all_direction by
                # speed), advanced total_pass, cleared+redrawn led_table for the
                # current frame. We score presses and publish the frame.
                # Returning False makes Play.running() stop (timeout / Stop btn).
                frame_counter = {"n": 0}

                def _frame_callback(play_self, dgroup, time_pass, total_pass):
                    # total_pass is PER-LEVEL (reset each level). Session timing
                    # is wall-clock from game.session_start.
                    try:
                        session_elapsed = time.time() - game.session_start

                        # ── SESSION-END conditions (stop the whole marathon) ──
                        #   life<=0          -> result 0 (out of lives)
                        #   session timer up -> result 2 (5-min timeout)
                        if game.life <= 0:
                            time_left = game.game_time_sec - session_elapsed
                            if time_left > 10.0:
                                # Lives gone but time remains: restart same level,
                                # keep score. Session loop refills HP and replays.
                                game._restart_level = True
                                return False
                            game._session_over = True
                            game.update_state(game_over_reason="out_of_life", result=0)
                            return False
                        if (not game.running) or session_elapsed > game.game_time_sec:
                            game._session_over = True
                            game.update_state(game_over_reason="timeout", result=2)
                            return False
                        # ── LEVEL-END by TIME (advance to next level) ──
                        # board_time_sec = max group end_time. For short levels
                        # this fires; long (600s) levels advance by all-cleared.
                        if total_pass > game.board_time_sec:
                            game._level_cleared = True
                            return False

                        grid = led_table.led_table
                        state = led_table.state_table

                        # ── CLIMB CLASSIFICATION ─────────────────────────────
                        # Climb has NO goal_led indicator.  Scoring is
                        # color-based: any FLOOR_LIGHT tile whose main-ring
                        # color is in _CLIMB_COLOR_ARR is scoreable.
                        # 2P DK levels: P1=blue (0,0,254), P2=orange (254,128,0).
                        # Same-color 2P (DK-series same color): checkerboard split.
                        # RED/DEDUCT = hazard as before.
                        goal_cells  = set()
                        goal2_cells = set()
                        red_cells   = set()
                        deduct_cells = set()
                        green_cells = set()   # safe platforms — shield from RED

                        _P1_COLOR = (0, 0, 254)    # blue   (P1)
                        _P2_COLOR = (254, 128, 0)  # orange (P2)
                        _GREEN    = (0, 254, 0)    # safe platform (non-scoring)

                        def _stationary(group):
                            try:
                                return float(getattr(group, "speed", 0) or 0) == 0.0
                            except (TypeError, ValueError):
                                return False

                        # ── PRIORITY OVERLAP RESOLUTION ──────────────────────
                        # When multiple groups occupy the SAME cell, ONE wins by
                        # rank: green(3) > red/deduct(2) > blue/orange/goal(1).
                        # This gives each cell exactly ONE category + display
                        # color, so a blue tile under a moving red reads red NOW
                        # (and becomes scoreable again once red moves off it).
                        #   cell_win[(i,j)] = (rank, category, rgb)
                        cell_win = {}
                        _scoreset = set(_CLIMB_COLOR_ARR)
                        for g in dgroup.values():
                            sm = getattr(g, "start_member", None)
                            if not sm:
                                continue
                            if getattr(g, "type", None) != Setting.FLOOR_LIGHT:
                                continue
                            if not (g.start_time_sec <= total_pass <= g.end_time_sec):
                                continue
                            mc = _group_main_color(g.color)
                            if mc == _GREEN:
                                rank, cat = 3, "green"
                            elif _rgb_is_deduct(mc):
                                rank, cat = 2, "deduct"
                            elif mc in _CLIMB_HAZARD_COLORS:
                                rank, cat = 2, "red"
                            elif game.multiplayer and mc == _P1_COLOR:
                                rank, cat = 1, "p1"
                            elif game.multiplayer and mc == _P2_COLOR:
                                rank, cat = 1, "p2"
                            elif (not game.multiplayer) and mc in _scoreset:
                                rank, cat = 1, "goal"
                            else:
                                rank, cat = 0, "decor"
                            for cell in sm:
                                ci = round(cell[0]); cj = round(cell[1])
                                if not (0 <= ci < led_table.led_row and 0 <= cj < led_table.led_col):
                                    continue
                                if (ci, cj) in game.unused_cells:
                                    continue
                                prev = cell_win.get((ci, cj))
                                if prev is None or rank > prev[0]:
                                    cell_win[(ci, cj)] = (rank, cat, mc)

                        # Derive mutually-exclusive category sets from winners.
                        for (ci, cj), (rank, cat, mc) in cell_win.items():
                            if cat == "green":
                                green_cells.add((ci, cj))
                            elif cat == "deduct":
                                deduct_cells.add((ci, cj))
                            elif cat == "red":
                                red_cells.add((ci, cj))
                            elif cat == "p1" or cat == "goal":
                                goal_cells.add((ci, cj))
                            elif cat == "p2":
                                goal2_cells.add((ci, cj))

                        # ── LEVEL COMPLETION ─────────────────────────────────
                        # Count scoreable tiles remaining across ALL groups
                        # (active + future waves). When all consumed → complete.
                        # Scoreable: PLUS_ARR (1P) or blue+orange (2P). Green/red
                        # /deduct are NEVER scoreable so don't block completion.
                        _scoreable_colors = ({_P1_COLOR, _P2_COLOR} if game.multiplayer
                                             else set(_CLIMB_COLOR_ARR))
                        remaining_scoreable = 0
                        for g in dgroup.values():
                            if getattr(g, "type", None) != Setting.FLOOR_LIGHT:
                                continue
                            mc = _group_main_color(g.color)
                            if mc in _scoreable_colors:
                                sm = getattr(g, "start_member", None)
                                if not sm or g.end_time_sec < total_pass:
                                    continue
                                for cell in sm:
                                    ci = round(cell[0]); cj = round(cell[1])
                                    if not (0 <= ci < led_table.led_row and
                                            0 <= cj < led_table.led_col):
                                        continue
                                    # The active-coordinate map is authoritative:
                                    # unwired cells never participate in this
                                    # venue's scoring or completion.
                                    if (ci, cj) in game.unused_cells:
                                        continue

                                    # A static green group that covers this static
                                    # goal for its entire time window makes the
                                    # goal permanently unreachable (DK07). Moving
                                    # masks remain countable because they can clear.
                                    permanently_green_masked = False
                                    if _stationary(g):
                                        for green in dgroup.values():
                                            if green is g or not _stationary(green):
                                                continue
                                            if getattr(green, "type", None) != Setting.FLOOR_LIGHT:
                                                continue
                                            if _group_main_color(green.color) != _GREEN:
                                                continue
                                            if (green.start_time_sec <= g.start_time_sec and
                                                    green.end_time_sec >= g.end_time_sec and
                                                    (ci, cj) in (getattr(green, "start_member", None) or ())):
                                                permanently_green_masked = True
                                                break
                                    if not permanently_green_masked:
                                        remaining_scoreable += 1
                        # Grace period (>1.5s) so level has time to spawn first wave.
                        # All scoreable cleared -> LEVEL done -> ADVANCE to next
                        # level (NOT game over). Score/life persist via instance.
                        if total_pass > 1.5 and remaining_scoreable == 0:
                            logger.info(f"Level cleared (all tiles): "
                                        f"score={game.score}, score2={game.score2}, "
                                        f"life={game.life}")
                            game._level_cleared = True
                            return False

                        # AUTO-JUMP: scoreable remain but none active NOW (current
                        # wave cleared, next wave is in the future). Skip dead time
                        # by advancing total_pass to the next scoreable wave's start.
                        # Mirrors real game's running_by_blue auto-jump.
                        if total_pass > 1.5 and remaining_scoreable > 0 \
                                and not goal_cells and not goal2_cells:
                            next_start = None
                            for g in dgroup.values():
                                if getattr(g, "type", None) != Setting.FLOOR_LIGHT:
                                    continue
                                mc = _group_main_color(g.color)
                                if mc not in _scoreable_colors:
                                    continue
                                sm = getattr(g, "start_member", None)
                                if not sm:
                                    continue
                                st = g.start_time_sec
                                if st > total_pass and (next_start is None or st < next_start):
                                    next_start = st
                            if next_start is not None:
                                game._no_reachable_goal_since = None
                                logger.debug(f"Auto-jump: {total_pass:.1f}s -> {next_start:.1f}s")
                                play_self.total_pass = next_start
                                game.last_life_loss_time = 0.0  # reset hazard gate
                            else:
                                # No visible goals and no future wave can expose
                                # the remaining source members. Give moving masks
                                # a short chance to clear, then finish instead of
                                # deadlocking forever (B31 green conveyor case).
                                now_mono = time.monotonic()
                                if game._no_reachable_goal_since is None:
                                    game._no_reachable_goal_since = now_mono
                                elif now_mono - game._no_reachable_goal_since >= _MASKED_GOAL_GRACE:
                                    logger.warning(
                                        "Level cleared with {} unreachable masked goal(s)",
                                        remaining_scoreable,
                                    )
                                    game._level_cleared = True
                                    return False
                        else:
                            game._no_reachable_goal_since = None

                        # DEBUG: log tile classification every 60 frames
                        if frame_counter["n"] % 60 == 0:
                            logger.debug(f"Frame {frame_counter['n']}: goal={len(goal_cells)}, "
                                         f"goal2={len(goal2_cells)}, red={len(red_cells)}, "
                                         f"deduct={len(deduct_cells)}, remaining_scoreable={remaining_scoreable}, "
                                         f"mp={game.multiplayer}")

                        # 2) SCORE pressed cells (type-aware). Drop scored marks
                        #    for goals that are no longer active so they can score
                        #    again if they reappear.
                        with game.input_lock:
                            game.goal_cells = goal_cells
                            game.goal2_cells = goal2_cells
                            game.red_cells = red_cells
                            game.deduct_cells = deduct_cells
                            if game.accepting_input:
                                if game.multiplayer:
                                    game.process_respawns()
                                # Keep scored marks for ACTIVE goal/deduct cells only.
                                # Deduct cells must stay in scored_active while pressed
                                # or they fire every single frame (life drain per frame).
                                active_consumables = goal_cells | goal2_cells | deduct_cells
                                game.scored_active &= active_consumables
                                game.scored_active2 &= goal2_cells
                                prev_score = game.score
                                prev_score2 = game.score2
                                prev_life = game.life
                                for i in range(led_table.led_row):
                                    for j in range(led_table.led_col):
                                        if state[i][j]:
                                            game.try_score_cell(i, j)
                                if game.audio.backend_active:
                                    if game.score > prev_score or game.score2 > prev_score2:
                                        game.audio.play_score_positive()
                                    elif (
                                        game.score < prev_score
                                        or game.score2 < prev_score2
                                        or game.life < prev_life
                                    ):
                                        game.audio.play_score_negative()

                        # 2) Build display buffer from the PRIORITY winner map so
                        #    overlapping cells render the WINNING color (green >
                        #    red/deduct > blue/orange), matching interaction.
                        #    Single RGB per cell (Climb = square single-color).
                        cols = led_table.led_col
                        rows = led_table.led_row
                        import math as _math
                        pulse = 0.60 + 0.40 * (0.5 + 0.5 * _math.sin(total_pass * _math.pi * 2))
                        led_display = [[0, 0, 0] for _ in range(rows * cols)]
                        for (ci, cj), (rank, cat, mc) in cell_win.items():
                            idx = ci * cols + cj
                            if cat in ("goal", "p1", "p2"):
                                # scoreable tiles shimmer
                                led_display[idx] = [int(ch * pulse) for ch in mc]
                            else:
                                led_display[idx] = [int(mc[0]), int(mc[1]), int(mc[2])]

                        # 2b) FLASH: stepped tiles blink white ~0.4s then vanish.
                        now = time.time()
                        with game.input_lock:
                            for cell, t0 in list(game.flashes.items()):
                                el = now - t0
                                if el > 0.4:
                                    game.flashes.pop(cell, None)
                                    continue
                                fi, fj = cell
                                on = int(el / 0.1) % 2 == 0
                                led_display[fi * cols + fj] = [254, 254, 254] if on else [0, 0, 0]

                        _now = time.time()
                        if USE_SERIAL_HD and _hw_led_control is not None and \
                                _now - getattr(game, "_hw_last_draw", 0) >= _HW_DRAW_INTERVAL:
                            _hw_io_started = time.perf_counter()
                            with _hw_serial_lock:
                                try:
                                    _rc = led_table.led_row
                                    _cc = led_table.led_col
                                    _ld2 = [[_normalize_rgb(led_display[r * _cc + c]) for c in range(_cc)] for r in range(_rc)]
                                    _hw_led_control.draw_screen_by_com(_hw_layout_type, _ld2)
                                    game._hw_last_draw = _now
                                    game._hw_draw_count = getattr(game, "_hw_draw_count", 0) + 1
                                    _hw_led_control.update_screen_state_by_com(
                                        _hw_layout_type,
                                        game.hw_state_table,
                                        game.hw_state_table,
                                    )
                                    game.merge_input_states()
                                except Exception as _hw_err:
                                    logger.warning(f"HW I/O: {_hw_err}")
                                finally:
                                    _hw_io_ms = (
                                        time.perf_counter() - _hw_io_started
                                    ) * 1000.0
                                    game._hw_io_last_ms = _hw_io_ms
                                    game._hw_io_total_ms = (
                                        getattr(game, "_hw_io_total_ms", 0.0) +
                                        _hw_io_ms
                                    )
                                    game._hw_io_max_ms = max(
                                        getattr(game, "_hw_io_max_ms", 0.0),
                                        _hw_io_ms,
                                    )

                        with game.input_lock:
                            pressed_tiles = [
                                [r, c]
                                for r in range(led_table.led_row)
                                for c in range(led_table.led_col)
                                if led_table.state_table[r][c]
                            ]
                        input_events = game._input_event_snapshot()

                        game.update_state(
                            score=game.score,
                            score2=game.score2,
                            multiplayer=game.multiplayer,
                            time_elapsed=session_elapsed,                       # SESSION elapsed
                            time_left=max(0, game.game_time_sec - session_elapsed),  # SESSION countdown
                            life=game.life,
                            display_lives=math.ceil(game.life * 5 / game.max_life) if game.max_life else 0,
                            display_max=5,
                            game_over=False,
                            led_display=led_display,
                            pressed_tiles=pressed_tiles,
                            input_events=input_events,
                            grid_rows=led_table.led_row,
                            grid_cols=led_table.led_col,
                            current_level=game.current_level_id,
                            levels_cleared=game.levels_cleared,
                            phase="playing",
                            accepting_input=game.accepting_input,
                            bgm_active=bool(getattr(game.audio, "backend_active", False)),
                            effect_name=None,
                            phase_step=None,
                        )

                        frame_counter["n"] += 1
                        if frame_counter["n"] % 120 == 0:
                            logger.debug(f"Game {game_id}: score={game.score}, "
                                         f"t={total_pass:.1f}s")
                        # Pace ~100fps. running() is a tight loop with no sleep;
                        # wall-clock timing keeps movement correct regardless.
                        time.sleep(0.01)
                        return True
                    except Exception as cb_err:
                        logger.error(f"Frame callback error {game_id}: {cb_err}")
                        return False

                # ── SESSION LOOP ─────────────────────────────────────────────
                # Marathon through level_sequence. Score + lives + 5-min timer
                # persist across levels. Each level runs via Play.running() until
                # the callback returns False (level cleared -> advance, or session
                # over -> stop). End on life<=0, timer<=0, or sequence exhausted.
                if play is None or not game.level_sequence:
                    logger.warning(f"No Play object or empty level sequence; "
                                   f"session cannot run: {game_id}")
                    game.begin_level_transition()
                    game.update_state(game_over=True, game_over_reason="no_levels",
                                      time_left=0, accepting_input=False)
                    game.running = False
                    _hw_blank_floor(led_table)
                    return

                play.callback = _frame_callback
                effect_runner = EffectRunner(
                    game,
                    play,
                    led_table,
                    _s,
                    game.audio,
                    blank_floor=_hw_blank_floor,
                )

                def _finish_session():
                    if not game._session_end_played:
                        effect_runner.run_session_end()

                for lvl_idx, lvl_path in enumerate(game.level_sequence):
                    if game._session_over or not game.running:
                        break
                    session_elapsed = time.time() - game.session_start
                    if session_elapsed > game.game_time_sec:
                        game._session_over = True
                        game._end_reason = "timeout"
                        _finish_session()
                        break

                    lvl_id = os.path.basename(lvl_path).rsplit(".", 1)[0]

                    if not effect_runner.run("countdown"):
                        break
                    effect_runner.enter_gameplay()

                    # ── RESTART LOOP: replay this level whenever lives hit 0 with
                    #    >10s left (score persists, HP refills). Exits on level
                    #    clear, session timeout, or true game-over (life=0, <10s).
                    while True:
                        # Reload + prepare (24→33 scale) fresh every attempt.
                        # Groups are mutated in-place as tiles are scored/consumed,
                        # so reusing an unprepared/raw board would leave blank
                        # columns and already-scored tiles missing on restart.
                        try:
                            def _play_level(dg):
                                play.running_state = True
                                play.total_pass = 0
                                play.callback = _frame_callback
                                play.running(dg)

                            def _setup_attempt(groups, game_obj):
                                game.current_level_id = lvl_id
                                _setup_level(groups, game_obj)
                                session_elapsed = time.time() - game.session_start
                                logger.info(
                                    f"▶ Level {lvl_id}: groups={len(groups)}, "
                                    f"mp={game.multiplayer}, "
                                    f"board_time={game.board_time_sec}s, "
                                    f"score={game.score}, life={game.life}, "
                                    f"t_left={game.game_time_sec - session_elapsed:.0f}s"
                                )

                            _run_level_attempt(
                                lvl_path,
                                led_table=led_table,
                                settings=_s,
                                level_id=lvl_id,
                                reset_consumer=game.reset_for_level,
                                setup_consumer=_setup_attempt,
                                play_consumer=_play_level,
                                transition_consumer=game.begin_level_transition,
                                ready_consumer=game.finish_level_transition,
                            )
                        except LevelAttemptPreparationError as prep_err:
                            logger.warning(
                                f"Skipping unprepared level {lvl_id}: {prep_err}"
                            )
                            break
                        except Exception as run_err:
                            import traceback
                            logger.warning(f"Level {lvl_id} run error: {run_err}\n"
                                           f"{traceback.format_exc()}")
                            game._session_over = True
                            break

                        if game._session_over:
                            _finish_session()
                            break

                        if game._restart_level:
                            game._restart_level = False
                            game.refill_life_for_restart()
                            effect_runner.run("level_fail", play_stinger=True)
                            if game._session_over or not game.running:
                                break
                            effect_runner.run("countdown")
                            if game._session_over or not game.running:
                                break
                            effect_runner.enter_gameplay()
                            logger.info(f"↻ Life restart: level={lvl_id}, score={game.score}")
                            continue

                        if game._level_cleared:
                            game.levels_cleared += 1
                            logger.info(f"✓ Level {lvl_id} cleared "
                                        f"(total cleared={game.levels_cleared})")
                            session_elapsed = time.time() - game.session_start
                            more_levels = lvl_idx < len(game.level_sequence) - 1
                            if more_levels and session_elapsed < game.game_time_sec:
                                effect_runner.run("level_clear", play_stinger=True)
                            else:
                                game._session_over = True
                                _finish_session()
                        break

                    if game._session_over:
                        break

                if game._session_over and not game._session_end_played:
                    _finish_session()

                # Session finished (timer/lives/sequence end).
                game._session_over = True
                # Result honesty: 1 = cleared the whole level chain within time,
                # 2 = ran out of session time, 0 = out of life. Only a genuine
                # chain-exhaustion (loop finished with no timeout/out-of-life
                # reason) counts as "complete".
                state_result = game.get_state().get("result")
                if state_result is not None:
                    final_result = state_result          # frame callback already decided (out-of-life/timeout)
                elif game._end_reason == "timeout":
                    final_result = 2
                else:
                    final_result = 1                     # chain fully cleared in time
                final_reason = (game.get_state().get("game_over_reason")
                                 or game._end_reason or "session_end")
                final_score = game.compute_final_score(game.score)
                final_score2 = game.compute_final_score(game.score2)
                logger.info(f"Session over: reason={final_reason}, "
                            f"raw_score={game.score} -> final={final_score}, "
                            f"raw_score2={game.score2} -> final2={final_score2}, "
                            f"levels_cleared={game.levels_cleared}")
                game.update_state(game_over=True, time_left=0,
                                  game_over_reason=final_reason, result=final_result,
                                  levels_cleared=game.levels_cleared,
                                  final_score=final_score, final_score2=final_score2)
                game.running = False
                game.begin_level_transition()
                if not game._session_end_played:
                    _hw_blank_floor(led_table)

            except Exception as e:
                import traceback
                logger.error(f"Game error {game_id}: {e}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                game.begin_level_transition()
                game.running = False
                game.update_state(
                    game_over=True,
                    game_over_reason=str(e)
                )
                # Best-effort blank even on a crash path; game.led_table
                # may still be None if the crash happened before setup.
                _hw_blank_floor(getattr(game, "led_table", None))

        game.running = True   # set synchronously — clear_all() won't skip this thread
        game.sim_pressed.clear()
        game.thread = threading.Thread(target=_run_game, daemon=True)
        game.thread.start()

    def stop_game(self, game_id: str) -> dict:
        """Stop game and return final state"""
        game = self.get_game(game_id)
        if not game:
            return {"success": False, "error": f"Game not found: {game_id}"}

        game.begin_level_transition()
        game.running = False
        if game.thread:
            game.thread.join(timeout=5)

        # Manual stop (e.g. via /logout) — blank the physical floor so it
        # doesn't stay lit with the last frame drawn before the stop.
        _hw_blank_floor(getattr(game, "led_table", None))

        final_state = game.get_state()

        with self.lock:
            del self.games[game_id]

        logger.info(f"Game stopped: {game_id}")
        return {"success": True, "state": final_state}

    def cleanup_expired(self):
        """Remove expired games"""
        with self.lock:
            expired = [gid for gid, game in self.games.items() if game.is_expired()]
            for gid in expired:
                del self.games[gid]
                logger.warning(f"Game expired and removed: {gid}")

    def get_stats(self) -> dict:
        """Get manager statistics"""
        with self.lock:
            return {
                "active_games": len(self.games),
                "max_games": MAX_CONCURRENT_GAMES,
                "timeout_seconds": GAME_TIMEOUT_SECONDS
            }


# Global instance
_manager = None

def get_manager() -> GameManager:
    """Get GameManager singleton"""
    global _manager
    if _manager is None:
        _manager = GameManager()
    return _manager
