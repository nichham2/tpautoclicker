"""Thin wrapper around the OS input libraries.

Everything that sends mouse/keyboard input goes through ``InputBackend`` so the
engines can be unit tested with a fake backend and so the libraries are only
imported when actually needed (``keyboard`` needs root on Linux).
"""
from __future__ import annotations

import sys
import time


def enable_dpi_awareness() -> None:
    """On Windows, make screen-capture pixels and mouse coordinates agree.

    Without this, a 125%/150% display scale makes screenshots physical-pixel
    sized while mouse moves are in scaled pixels, so image-matched clicks land
    in the wrong place.
    """
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor aware
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


class InputBackend:
    """Real input using the ``mouse`` and ``keyboard`` packages."""

    def __init__(self) -> None:
        import keyboard  # noqa: F401  (imported lazily, may raise)
        import mouse  # noqa: F401

        self._kb = keyboard
        self._mouse = mouse

    # ---- mouse -------------------------------------------------------------
    def position(self) -> tuple[int, int]:
        return tuple(int(v) for v in self._mouse.get_position())  # type: ignore[return-value]

    def move(self, x: int, y: int) -> None:
        self._mouse.move(int(x), int(y), absolute=True, duration=0)

    def move_relative(self, dx: int, dy: int, duration: float = 0.0) -> None:
        self._mouse.move(int(dx), int(dy), absolute=False, duration=duration)

    def click(self, button: str = "left", clicks: int = 1, hold_s: float = 0.0, gap_s: float = 0.03) -> None:
        button = button.lower()
        for i in range(max(1, clicks)):
            if hold_s > 0:
                self._mouse.press(button)
                time.sleep(hold_s)
                self._mouse.release(button)
            else:
                self._mouse.click(button)
            if i + 1 < clicks:
                time.sleep(gap_s)

    # ---- keyboard ----------------------------------------------------------
    def key_down(self, key: str) -> None:
        self._kb.press(key.lower())

    def key_up(self, key: str) -> None:
        self._kb.release(key.lower())

    def tap(self, key: str, hold_s: float = 0.03) -> None:
        self._kb.press(key.lower())
        time.sleep(hold_s)
        self._kb.release(key.lower())

    def add_hotkey(self, combo: str, callback):
        return self._kb.add_hotkey(combo.lower(), callback, suppress=False)

    def remove_hotkey(self, handle) -> None:
        try:
            self._kb.remove_hotkey(handle)
        except (KeyError, ValueError):
            pass


class NullBackend:
    """Used when the input libraries cannot load; records calls instead."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self._pos = (0, 0)

    def position(self):
        return self._pos

    def move(self, x, y):
        self._pos = (int(x), int(y))
        self.calls.append(("move", int(x), int(y)))

    def move_relative(self, dx, dy, duration=0.0):
        self._pos = (self._pos[0] + int(dx), self._pos[1] + int(dy))
        self.calls.append(("move_rel", int(dx), int(dy)))

    def click(self, button="left", clicks=1, hold_s=0.0, gap_s=0.03):
        self.calls.append(("click", button.lower(), clicks, self._pos))

    def key_down(self, key):
        self.calls.append(("key_down", key))

    def key_up(self, key):
        self.calls.append(("key_up", key))

    def tap(self, key, hold_s=0.03):
        self.calls.append(("tap", key))

    def add_hotkey(self, combo, callback):
        return combo

    def remove_hotkey(self, handle):
        pass


def make_backend():
    """Return the real backend, or a NullBackend plus the error if unavailable."""
    try:
        return InputBackend(), None
    except Exception as e:  # ImportError, or keyboard's "must be root" on Linux
        return NullBackend(), e
