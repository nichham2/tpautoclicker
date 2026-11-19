"""Settings: one set of defaults, merged with whatever is on disk.

Settings live next to the app (not the current working directory), so launching
from a shortcut or another folder still finds them.
"""
from __future__ import annotations

import copy
import json
import os
import sys
from typing import Any


def app_dir() -> str:
    """Folder that holds settings.json, templates/ and sequences/."""
    if getattr(sys, "frozen", False):  # PyInstaller build
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


SETTINGS_FILE = os.path.join(app_dir(), "settings.json")
TEMPLATES_DIR = os.path.join(app_dir(), "templates")
SEQUENCES_DIR = os.path.join(app_dir(), "sequences")


def bundled_dir() -> str:
    """Where read-only bundled files live (inside the exe when frozen)."""
    return getattr(sys, "_MEIPASS", app_dir())


def install_bundled_files() -> None:
    """In the single-file exe, copy the bundled templates/ and sequences/ next to
    the exe on first run so they can be edited, and add any new bundled files
    later versions ship. Files the user already has are never overwritten."""
    src_root = bundled_dir()
    if os.path.abspath(src_root) == os.path.abspath(app_dir()):
        return
    import shutil

    for sub, dst in (("templates", TEMPLATES_DIR), ("sequences", SEQUENCES_DIR)):
        src = os.path.join(src_root, sub)
        if not os.path.isdir(src):
            continue
        try:
            os.makedirs(dst, exist_ok=True)
            for name in os.listdir(src):
                target = os.path.join(dst, name)
                if not os.path.exists(target) or _is_superseded(target):
                    shutil.copy2(os.path.join(src, name), target)
        except OSError:
            pass


# Fingerprints of bundled files from earlier releases. If the copy next to the
# exe is byte-for-byte one of these (the user never edited it), the newer
# bundled version replaces it; edited files are always left alone.
_SUPERSEDED = {
    # tower_defense_retry_loop.json v4.0.0: waited for the LEVEL CLEARED title,
    # which missed other results such as THE BASE DROWNED.
    "9027050950f71ca2ab6862ccd5d9e0fc787c97589d664890cc467f7094fae4ad",
}


def _fingerprint(path: str) -> str:
    import hashlib

    with open(path, "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()


def _is_superseded(path: str) -> bool:
    try:
        return _fingerprint(path) in _SUPERSEDED
    except OSError:
        return False

DEFAULTS: dict[str, Any] = {
    # Clicker
    "mouse_button": "Left",          # Left / Right / Middle
    "click_type": "Single",          # Single / Double
    "interval_ms": 50,               # time between clicks
    "jitter_pct": 0,                 # +/- random % applied to the interval
    "location_mode": "Cursor",       # Cursor / Fixed
    "fixed_x": 0,
    "fixed_y": 0,
    "stop_after_clicks": 0,          # 0 = never
    "stop_after_seconds": 0,         # 0 = never
    "hold_key": "",                  # optional key held while clicking
    "start_delay_s": 0.0,
    # Hotkeys
    "hotkey": "F6",                  # toggle clicker
    "sequence_hotkey": "F7",         # toggle automation sequence
    "panic_hotkey": "F8",            # stop everything
    # AFK
    "afk_interval_s": 30,
    "afk_radius_px": 5,
    # Automation
    "last_sequence": "tower_defense_retry_loop.json",
    "monitor": 1,                    # mss monitor index (1 = primary)
    "scan_interval_s": 0.5,
    "match_threshold": 0.8,
    "multi_scale": True,             # search nearby scales if not found at the expected one
    "mouse_corner_failsafe": True,   # slam the mouse into the top-left corner to stop
    "capture_delay_s": 3,
    # Appearance
    "theme_mode": "Dark",            # System / Light / Dark
    "accent": "#6C5DD3",             # accent (sidebar, main buttons)
    "design": 2,                     # bumped when the default look changes
    "show_minibar": True,            # always-on-top mini controls
    "minibar_x": -1,                 # -1 = default spot (top-right)
    "minibar_y": -1,
    "minibar_opacity": 0.95,
    # App
    "minimize_to_tray": False,
    "minimize_on_start": True,      # get the window out of the way so it is not clicked
    "notifications": True,
    "sounds": True,
}

# Keys renamed / reshaped since v3.x
_LEGACY = {"speed": "interval_ms"}


def _migrate(raw: dict[str, Any]) -> dict[str, Any]:
    out = dict(raw)
    if "speed" in out and "interval_ms" not in out:
        try:
            out["interval_ms"] = int(round(float(out["speed"]) * 1000))
        except (TypeError, ValueError):
            pass
    for old in _LEGACY:
        out.pop(old, None)
    if out.get("hold_key") in ("None", None):
        out["hold_key"] = ""
    if out.get("design", 1) < 2:
        # v4.0 saved the Material You defaults; move to the dashboard look,
        # but keep an accent the user picked themselves.
        out["design"] = 2
        out["theme_mode"] = "Dark"
        if out.get("accent", "#6750A4").lower() == "#6750a4":
            out["accent"] = "#6C5DD3"
    return out


def load_settings(path: str = SETTINGS_FILE) -> dict[str, Any]:
    settings = copy.deepcopy(DEFAULTS)
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            for k, v in _migrate(raw).items():
                if k in DEFAULTS and type(v) is not type(DEFAULTS[k]) and not (
                    isinstance(DEFAULTS[k], float) and isinstance(v, int)
                ):
                    try:
                        v = type(DEFAULTS[k])(v)
                    except (TypeError, ValueError):
                        continue
                settings[k] = v
    except FileNotFoundError:
        pass
    except (OSError, json.JSONDecodeError):
        # A corrupt settings file should never stop the app from starting.
        pass
    return settings


def save_settings(settings: dict[str, Any], path: str = SETTINGS_FILE) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
    os.replace(tmp, path)
