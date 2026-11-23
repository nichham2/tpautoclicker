"""Automation sequences: a list of steps that watch the screen and click.

A sequence is plain JSON (see ``sequences/``) so it can be edited in the app or
by hand. Positions in a sequence are in the sequence's *reference resolution*
and are scaled to the real screen, so the same file keeps working if the game
runs at a different resolution.

Each step is a dict with a ``type`` plus that type's fields. Every step also
accepts:

    label       text shown in the log / editor
    enabled     false to skip the step without deleting it
    on_fail     "stop" (default), "skip" (carry on with the next step), or
                "restart" (go back to the first step)
    delay_after seconds to pause after the step succeeds
"""
from __future__ import annotations

import json
import os
import random
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .clicker import in_corner

# ---------------------------------------------------------------------------
# Step schema: drives validation and the editor form.
# (field name, kind, default, help)
# kinds: template, float, int, bool, str, key, button, point, region, choice:<a|b>
# ---------------------------------------------------------------------------
COMMON_FIELDS = [
    ("label", "str", "", "Name shown in the log"),
    ("enabled", "bool", True, "Untick to skip this step"),
    ("on_fail", "choice:stop|skip|restart", "stop", "What to do if the step times out"),
    ("delay_after", "float", 0.0, "Seconds to wait after the step"),
]

STEP_TYPES: dict[str, dict[str, Any]] = {
    "wait_image": {
        "title": "Wait until image appears",
        "fields": [
            ("template", "template", "", "Image to look for"),
            ("timeout", "float", 60.0, "Give up after this many seconds (0 = wait forever)"),
            ("threshold", "float", 0.0, "Match confidence 0-1 (0 = use the global setting)"),
            ("region", "region", None, "Only search this part of the screen (optional)"),
        ],
    },
    "wait_image_gone": {
        "title": "Wait until image disappears",
        "fields": [
            ("template", "template", "", "Image that should go away"),
            ("timeout", "float", 30.0, "Give up after this many seconds (0 = wait forever)"),
            ("threshold", "float", 0.0, "Match confidence 0-1 (0 = use the global setting)"),
            ("region", "region", None, "Only search this part of the screen (optional)"),
        ],
    },
    "click_image": {
        "title": "Find image and click it",
        "fields": [
            ("template", "template", "", "Image to click"),
            ("timeout", "float", 10.0, "Keep looking for this many seconds"),
            ("offset", "point", [0, 0], "Click this far from the image centre (reference px)"),
            ("button", "button", "left", "Mouse button"),
            ("clicks", "int", 1, "1 = single click, 2 = double click"),
            ("until_gone", "bool", False, "Click again until the image disappears"),
            ("fallback_key", "key", "", "Press this key instead if the image is never found"),
            ("threshold", "float", 0.0, "Match confidence 0-1 (0 = use the global setting)"),
            ("region", "region", None, "Only search this part of the screen (optional)"),
        ],
    },
    "click": {
        "title": "Click a fixed position",
        "fields": [
            ("pos", "point", [0, 0], "Where to click (reference px)"),
            ("button", "button", "left", "Mouse button"),
            ("clicks", "int", 1, "1 = single click, 2 = double click"),
        ],
    },
    "key": {
        "title": "Press a key",
        "fields": [
            ("key", "key", "space", "Key or combo, e.g. space, enter, ctrl+s"),
            ("presses", "int", 1, "How many times"),
        ],
    },
    "wait": {
        "title": "Wait",
        "fields": [
            ("seconds", "float", 1.0, "How long"),
            ("jitter", "float", 0.0, "Add up to this many random extra seconds"),
        ],
    },
    "wait_pixel": {
        "title": "Wait until a pixel is a colour",
        "fields": [
            ("pos", "point", [0, 0], "Pixel to watch (reference px)"),
            ("color", "str", "#ffffff", "Colour as #rrggbb"),
            ("tolerance", "int", 20, "How far each channel may differ (0-255)"),
            ("timeout", "float", 60.0, "Give up after this many seconds (0 = wait forever)"),
        ],
    },
}


# ---------------------------------------------------------------------------
# Validation: sequence files are often shared, so every field is checked when a
# file is loaded instead of crashing a run hours later.
# ---------------------------------------------------------------------------
_HEX = re.compile(r"#?[0-9a-fA-F]{6}")
_BOOL_STR = {"true": True, "1": True, "yes": True, "false": False, "0": False, "no": False}


def _coerce(kind: str, v: Any) -> Any:
    if kind == "float":
        if isinstance(v, bool):
            raise ValueError("must be a number")
        return float(v)
    if kind == "int":
        if isinstance(v, bool):
            raise ValueError("must be a whole number")
        f = float(v)
        if f != int(f):
            raise ValueError("must be a whole number")
        return int(f)
    if kind == "bool":
        if isinstance(v, bool):
            return v
        if isinstance(v, str) and v.strip().lower() in _BOOL_STR:
            return _BOOL_STR[v.strip().lower()]
        raise ValueError("must be true or false")
    if kind == "point":
        if not isinstance(v, (list, tuple)) or len(v) != 2:
            raise ValueError("must be [x, y]")
        return [int(v[0]), int(v[1])]
    if kind == "region":
        if v in (None, "", [], ()):
            return None
        if not isinstance(v, (list, tuple)) or len(v) != 4:
            raise ValueError("must be [x, y, w, h]")
        r = [int(x) for x in v]
        if r[2] <= 0 or r[3] <= 0:
            raise ValueError("width and height must be above 0")
        return r
    if kind == "button":
        v = str(v).lower()
        if v not in ("left", "right", "middle"):
            raise ValueError("must be left, right or middle")
        return v
    if kind.startswith("choice:"):
        options = kind.split(":", 1)[1].split("|")
        if v not in options:
            raise ValueError(f"must be one of {', '.join(options)}")
        return v
    if kind in ("str", "key", "template"):
        if v is None:
            return ""
        if not isinstance(v, (str, int, float)) or isinstance(v, bool):
            raise ValueError("must be text")
        return str(v)
    return v


# Keys that reach the operating system rather than the game. A shared sequence
# that presses these could open the Run box and type a command, so they need
# the user's explicit OK (``allow_system_keys``).
SYSTEM_KEYS = {"windows", "win", "leftwindows", "rightwindows", "cmd", "command", "super", "meta"}
SYSTEM_COMBOS = {"ctrl+esc", "alt+f4", "ctrl+alt+delete", "ctrl+alt+del", "ctrl+shift+esc", "alt+tab"}


def is_system_key(key: str) -> bool:
    k = str(key or "").lower().replace(" ", "")
    if not k:
        return False
    parts = set(k.split("+"))
    return bool(parts & SYSTEM_KEYS) or k in SYSTEM_COMBOS


def risky_keys(seq: "Sequence") -> list[str]:
    """Human-readable list of steps that press system keys."""
    out = []
    for i, st in enumerate(seq.steps, 1):
        for field_name in ("key", "fallback_key"):
            k = st.get(field_name)
            if k and is_system_key(k):
                out.append(f"Step {i}: {k}")
    return out


def keys_pressed(seq: "Sequence") -> list[str]:
    """Every distinct key a sequence can press, for the 'check this file' prompt."""
    keys = set()
    for st in seq.steps:
        for field_name in ("key", "fallback_key"):
            if st.get(field_name):
                keys.add(str(st[field_name]))
    return sorted(keys)


def default_step(step_type: str) -> dict[str, Any]:
    spec = STEP_TYPES[step_type]
    step: dict[str, Any] = {"type": step_type}
    for name, _kind, default, _help in spec["fields"] + COMMON_FIELDS:
        step[name] = list(default) if isinstance(default, list) else default
    return step


def normalize_step(step: dict[str, Any], index: int = 0) -> dict[str, Any]:
    """Fill in defaults and check every field. ``index`` (1-based) is only
    used in error messages."""
    where = f"Step {index}: " if index else ""
    if not isinstance(step, dict):
        raise ValueError(f"{where}must be an object, got {type(step).__name__}")
    if step.get("type") not in STEP_TYPES:
        raise ValueError(f"{where}unknown step type {step.get('type')!r}")
    out = default_step(step["type"])
    out.update(step)
    for name, kind, _default, _help in STEP_TYPES[step["type"]]["fields"] + COMMON_FIELDS:
        try:
            out[name] = _coerce(kind, out[name])
        except (TypeError, ValueError, IndexError) as e:
            raise ValueError(f"{where}'{name}' {e} (got {out[name]!r})") from None
    if out["type"] == "wait_pixel" and not _HEX.fullmatch(out["color"]):
        raise ValueError(f"{where}'color' must be #rrggbb (got {out['color']!r})")
    for name in ("timeout", "delay_after", "seconds", "jitter", "threshold"):
        if name in out and out[name] < 0:
            raise ValueError(f"{where}'{name}' can't be negative (got {out[name]!r})")
    return out


def describe_step(step: dict[str, Any]) -> str:
    t = step["type"]
    if t in ("wait_image", "wait_image_gone"):
        to = step.get("timeout", 0)
        return f"{step.get('template')}  (timeout {'∞' if not to else f'{to:g}s'})"
    if t == "click_image":
        extra = " until gone" if step.get("until_gone") else ""
        fb = f", else press {step['fallback_key']}" if step.get("fallback_key") else ""
        return f"{step.get('template')}{extra}{fb}"
    if t == "click":
        return f"at {tuple(step.get('pos', (0, 0)))} {step.get('button', 'left')}"
    if t == "key":
        n = step.get("presses", 1)
        return f"{step.get('key')}" + (f" ×{n}" if n > 1 else "")
    if t == "wait":
        j = step.get("jitter", 0)
        return f"{step.get('seconds', 0):g}s" + (f" (+0-{j:g}s)" if j else "")
    if t == "wait_pixel":
        return f"{tuple(step.get('pos', (0, 0)))} ≈ {step.get('color')}"
    return ""


@dataclass
class Sequence:
    name: str = "New sequence"
    reference_resolution: tuple[int, int] = (1920, 1080)
    repeat: int = 0                 # 0 = loop forever
    steps: list[dict[str, Any]] = field(default_factory=list)
    notes: str = ""
    allow_system_keys: bool = False  # the user OK'd key steps such as windows+r

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Sequence":
        if not isinstance(d, dict):
            raise ValueError("A sequence file must contain a JSON object")
        rr = d.get("reference_resolution", [1920, 1080])
        try:
            ref = (int(rr[0]), int(rr[1]))
            if len(rr) != 2 or ref[0] <= 0 or ref[1] <= 0:
                raise ValueError
        except (TypeError, ValueError, IndexError):
            raise ValueError(f"'reference_resolution' must be [width, height] (got {rr!r})") from None
        try:
            repeat = int(d.get("repeat", 0))
            if repeat < 0:
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError(f"'repeat' must be 0 or more (got {d.get('repeat')!r})") from None
        steps = d.get("steps", [])
        if not isinstance(steps, list):
            raise ValueError("'steps' must be a list")
        return cls(
            name=str(d.get("name", "Sequence")),
            reference_resolution=ref,
            repeat=repeat,
            steps=[normalize_step(s, i) for i, s in enumerate(steps, 1)],
            notes=str(d.get("notes", "") or ""),
            allow_system_keys=d.get("allow_system_keys") is True,
        )

    def to_dict(self) -> dict[str, Any]:
        d = {
            "name": self.name,
            "notes": self.notes,
            "reference_resolution": list(self.reference_resolution),
            "repeat": self.repeat,
            "steps": self.steps,
        }
        if self.allow_system_keys:
            d["allow_system_keys"] = True
        return d

    @classmethod
    def load(cls, path: str) -> "Sequence":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def save(self, path: str) -> None:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        os.replace(tmp, path)


class StopRequested(Exception):
    pass


class StepFailed(Exception):
    pass


# A loop that takes no time (e.g. a lone "Wait 0 s" step) would otherwise spin
# hundreds of thousands of times a second and flood the UI with signals.
MIN_LOOP_S = 0.05


class SequenceRunner:
    """Runs a Sequence on a worker thread.

    ``screen`` provides ``grab()``, ``size()`` and ``offset()``; ``matcher`` is a
    ``vision.Matcher``. Callbacks are invoked from the worker thread; the GUI
    forwards them to the UI thread with Qt signals.
    """

    def __init__(self, backend, screen, matcher, *,
                 scan_interval: float = 0.5,
                 corner_failsafe: bool = True,
                 log: Callable[[str], None] | None = None,
                 on_state: Callable[[bool], None] | None = None,
                 on_step: Callable[[int, int], None] | None = None,
                 on_loop: Callable[[int, float], None] | None = None,
                 sleep: Callable[[float], None] | None = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.backend = backend
        self.screen = screen
        self.matcher = matcher
        self.scan_interval = scan_interval
        self.corner_failsafe = corner_failsafe
        self.log = log or (lambda msg: None)
        self.on_state = on_state or (lambda running: None)
        self.on_step = on_step or (lambda idx, loop: None)
        self.on_loop = on_loop or (lambda loops, secs: None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._sleep_impl = sleep
        self._clock = clock
        self.loops_done = 0
        self.seq: Optional[Sequence] = None

    # ---- lifecycle ---------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, seq: Sequence, start_at: int = 0) -> bool:
        if self.running:
            return False
        self._stop.clear()
        self.seq = seq
        self._thread = threading.Thread(target=self._run, args=(seq, start_at), daemon=True, name="sequence")
        self._thread.start()
        self.on_state(True)
        return True

    def stop(self) -> None:
        self._stop.set()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    # ---- helpers -----------------------------------------------------------
    def _sleep(self, secs: float) -> None:
        if secs <= 0:
            self._check()
            return
        if self._sleep_impl is not None:
            self._sleep_impl(secs)
            self._check()
            return
        # Wake up often so the corner failsafe works during long waits too.
        end = time.monotonic() + secs
        while True:
            self._check()
            left = end - time.monotonic()
            if left <= 0:
                return
            if self._stop.wait(min(left, 0.1)):
                raise StopRequested()

    def _check(self) -> None:
        if self._stop.is_set():
            raise StopRequested()
        if self.corner_failsafe:
            try:
                x, y = self.backend.position()
                ox, oy = self.screen.offset()
                if in_corner((x, y), (ox, oy)):
                    self.log("Mouse moved to the top-left corner: failsafe stop.")
                    raise StopRequested()
            except StopRequested:
                raise
            except Exception:
                pass

    def _scale(self) -> tuple[float, float]:
        sw, sh = self.screen.size()
        rw, rh = self.seq.reference_resolution if self.seq else (sw, sh)
        return sw / float(rw), sh / float(rh)

    def to_screen(self, pos) -> tuple[int, int]:
        """Reference coords -> absolute screen coords for the mouse."""
        sx, sy = self._scale()
        ox, oy = self.screen.offset()
        return int(round(pos[0] * sx)) + ox, int(round(pos[1] * sy)) + oy

    def _region(self, step) -> Optional[tuple[int, int, int, int]]:
        r = step.get("region")
        if not r:
            return None
        sx, sy = self._scale()
        return int(r[0] * sx), int(r[1] * sy), int(r[2] * sx), int(r[3] * sy)

    def _threshold(self, step) -> Optional[float]:
        t = step.get("threshold") or 0
        return float(t) if t > 0 else None

    def _find(self, step):
        img = self.screen.grab()
        return self.matcher.find(img, step["template"], self._threshold(step), self._region(step))

    def _poll(self, step, want_present: bool, timeout: float):
        """Poll until the template is present/absent. Returns the last match."""
        deadline = None if not timeout else self._clock() + timeout
        while True:
            self._check()
            m = self._find(step)
            if (m is not None) == want_present:
                return m
            if deadline is not None and self._clock() >= deadline:
                raise StepFailed(
                    f"'{step['template']}' {'never appeared' if want_present else 'did not go away'} "
                    f"within {timeout:g}s"
                )
            self._sleep(self.scan_interval)

    def _click_at(self, x: int, y: int, button: str, clicks: int) -> None:
        self._check()
        self.backend.move(x, y)
        time.sleep(0.05)  # let the game register the hover before pressing
        self.backend.click(button, clicks, hold_s=0.03)

    # ---- step implementations ---------------------------------------------
    def _do_step(self, step: dict[str, Any]) -> None:
        t = step["type"]
        if t == "wait":
            self._sleep(float(step["seconds"]) + random.uniform(0, float(step.get("jitter") or 0)))

        elif t == "wait_image":
            self._poll(step, True, float(step.get("timeout") or 0))

        elif t == "wait_image_gone":
            self._poll(step, False, float(step.get("timeout") or 0))

        elif t == "click_image":
            try:
                m = self._poll(step, True, float(step.get("timeout") or 0))
            except StepFailed:
                if step.get("fallback_key"):
                    self._guard_key(step["fallback_key"])
                    self.log(f"  '{step['template']}' not found; pressing {step['fallback_key']} instead")
                    self.backend.tap(step["fallback_key"])
                    return
                raise
            sx, sy = self._scale()
            ox, oy = self.screen.offset()
            dx, dy = step.get("offset") or (0, 0)
            attempts = 0
            while True:
                cx, cy = m.center
                self._click_at(cx + ox + int(dx * sx), cy + oy + int(dy * sy),
                               step.get("button", "left"), int(step.get("clicks", 1)))
                if not step.get("until_gone"):
                    return
                # Give the game a moment, then confirm the click landed.
                gone_by = self._clock() + 2.0
                while self._clock() < gone_by:
                    self._sleep(min(self.scan_interval, 0.25))
                    m2 = self._find(step)
                    if m2 is None:
                        return
                    m = m2
                attempts += 1
                if attempts >= 5:
                    raise StepFailed(f"'{step['template']}' still showing after {attempts} clicks")
                self.log(f"  still showing, clicking again ({attempts})")

        elif t == "click":
            x, y = self.to_screen(step["pos"])
            self._click_at(x, y, step.get("button", "left"), int(step.get("clicks", 1)))

        elif t == "key":
            self._guard_key(step["key"])
            for _ in range(max(1, int(step.get("presses", 1)))):
                self._check()
                self.backend.tap(step["key"])
                self._sleep(0.05)

        elif t == "wait_pixel":
            self._wait_pixel(step)

        else:  # pragma: no cover - guarded by normalize_step
            raise StepFailed(f"Unknown step type {t}")

    def _guard_key(self, key: str) -> None:
        if is_system_key(key) and not (self.seq and self.seq.allow_system_keys):
            raise StepFailed(f"'{key}' is a system key; allow system keys for this sequence to use it")

    def _wait_pixel(self, step) -> None:
        sx, sy = self._scale()
        px, py = int(step["pos"][0] * sx), int(step["pos"][1] * sy)
        hexc = step["color"].lstrip("#")
        want = (int(hexc[4:6], 16), int(hexc[2:4], 16), int(hexc[0:2], 16))  # BGR
        tol = int(step.get("tolerance", 20))
        timeout = float(step.get("timeout") or 0)
        deadline = None if not timeout else self._clock() + timeout
        while True:
            self._check()
            img = self.screen.grab()
            if 0 <= py < img.shape[0] and 0 <= px < img.shape[1]:
                got = img[py, px]
                if all(abs(int(got[i]) - want[i]) <= tol for i in range(3)):
                    return
            if deadline is not None and self._clock() >= deadline:
                raise StepFailed(f"pixel {tuple(step['pos'])} never became {step['color']}")
            self._sleep(self.scan_interval)

    # ---- main loop ---------------------------------------------------------
    def _run(self, seq: Sequence, start_at: int) -> None:
        self.loops_done = 0
        try:
            loop = 0
            idx = start_at
            loop_started = self._clock()
            restarts = 0
            self.log(f"Started '{seq.name}'" + (f" ({seq.repeat} loops)" if seq.repeat else " (loops until stopped)"))
            while True:
                if idx >= len(seq.steps):
                    loop += 1
                    self.loops_done = loop
                    secs = self._clock() - loop_started
                    if secs < MIN_LOOP_S:
                        self._sleep(MIN_LOOP_S - secs)  # never spin; lets stop/failsafe in
                        secs = self._clock() - loop_started
                    self.on_loop(loop, secs)
                    self.log(f"Loop {loop} done in {secs:.1f}s")
                    if seq.repeat and loop >= seq.repeat:
                        break
                    idx = 0
                    loop_started = self._clock()
                    if not seq.steps:
                        break
                step = seq.steps[idx]
                if not step.get("enabled", True):
                    idx += 1
                    continue
                self.on_step(idx, loop)
                name = step.get("label") or STEP_TYPES[step["type"]]["title"]
                self.log(f"[{idx + 1}] {name}: {describe_step(step)}")
                try:
                    self._do_step(step)
                    if step.get("delay_after"):
                        self._sleep(float(step["delay_after"]))
                    idx += 1
                    restarts = 0
                except (StepFailed, ValueError, TypeError, KeyError, IndexError) as e:
                    # Bad values that slipped past validation go through the
                    # step's failure policy instead of killing the whole run.
                    policy = step.get("on_fail", "stop")
                    self.log(f"  failed: {e} -> {policy}")
                    if policy == "skip":
                        idx += 1
                    elif policy == "restart":
                        restarts += 1
                        if restarts > 20:
                            self.log("Restarted 20 times in a row without progress; stopping.")
                            break
                        idx = 0
                        loop_started = self._clock()
                    else:
                        break
        except StopRequested:
            self.log("Stopped.")
        except Exception as e:  # never let the worker die silently
            self.log(f"Error: {e!r}")
        finally:
            close = getattr(self.screen, "close_thread", None)
            if close is not None:
                close()
            self.on_step(-1, self.loops_done)
            self.on_state(False)
