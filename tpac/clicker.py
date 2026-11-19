"""Auto-click and AFK engines.

Both run on a single worker thread each and stop through a ``threading.Event``,
so stopping is instant (no waiting out a long sleep) and starting twice can
never spawn two competing loops.
"""
from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class ClickConfig:
    button: str = "left"
    clicks_per_event: int = 1        # 1 = single, 2 = double
    interval_s: float = 0.05
    jitter_pct: float = 0.0          # 0-50: randomise interval by +/- this %
    fixed_pos: Optional[tuple[int, int]] = None  # None = click wherever the cursor is
    stop_after_clicks: int = 0
    stop_after_seconds: float = 0.0
    hold_key: str = ""
    start_delay_s: float = 0.0


class ClickEngine:
    def __init__(self, backend, on_state: Callable[[bool], None] | None = None,
                 on_tick: Callable[[int], None] | None = None) -> None:
        self.backend = backend
        self.on_state = on_state or (lambda running: None)
        self.on_tick = on_tick or (lambda count: None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.count = 0

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, cfg: ClickConfig) -> bool:
        with self._lock:
            if self.running:
                return False
            self._stop.clear()
            self.count = 0
            self._thread = threading.Thread(target=self._run, args=(cfg,), daemon=True, name="clicker")
            self._thread.start()
        self.on_state(True)
        return True

    def stop(self, wait: bool = False) -> None:
        self._stop.set()
        t = self._thread
        if wait and t is not None and t is not threading.current_thread():
            t.join(timeout=2)

    def toggle(self, cfg: ClickConfig) -> None:
        if self.running:
            self.stop()
        else:
            self.start(cfg)

    def _next_interval(self, cfg: ClickConfig) -> float:
        base = max(0.001, cfg.interval_s)
        if cfg.jitter_pct > 0:
            j = min(cfg.jitter_pct, 90) / 100.0
            base *= random.uniform(1 - j, 1 + j)
        return base

    def _run(self, cfg: ClickConfig) -> None:
        held = False
        try:
            if cfg.start_delay_s > 0 and self._stop.wait(cfg.start_delay_s):
                return
            if cfg.hold_key:
                self.backend.key_down(cfg.hold_key)
                held = True
            started = time.perf_counter()
            next_at = started
            last_report = 0.0
            while not self._stop.is_set():
                if cfg.fixed_pos is not None:
                    self.backend.move(*cfg.fixed_pos)
                self.backend.click(cfg.button, cfg.clicks_per_event)
                self.count += 1
                now = time.perf_counter()
                if now - last_report > 0.1:  # don't flood the UI thread
                    self.on_tick(self.count)
                    last_report = now
                if cfg.stop_after_clicks and self.count >= cfg.stop_after_clicks:
                    break
                if cfg.stop_after_seconds and now - started >= cfg.stop_after_seconds:
                    break
                # Schedule against a fixed timeline so the rate doesn't drift,
                # but never try to "catch up" with a burst after a stall.
                next_at = max(next_at + self._next_interval(cfg), now)
                delay = next_at - time.perf_counter()
                if delay > 0 and self._stop.wait(delay):
                    break
        finally:
            if held:
                try:
                    self.backend.key_up(cfg.hold_key)
                except Exception:
                    pass
            self.on_tick(self.count)
            self.on_state(False)


class AfkEngine:
    """Nudges the mouse a few pixels every so often to avoid idle kicks."""

    def __init__(self, backend, on_state: Callable[[bool], None] | None = None) -> None:
        self.backend = backend
        self.on_state = on_state or (lambda running: None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, interval_s: float = 30, radius: int = 5) -> bool:
        if self.running:
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, args=(interval_s, radius), daemon=True, name="afk")
        self._thread.start()
        self.on_state(True)
        return True

    def stop(self) -> None:
        self._stop.set()

    def _run(self, interval_s: float, radius: int) -> None:
        try:
            while not self._stop.wait(max(1.0, interval_s)):
                dx, dy = random.randint(-radius, radius), random.randint(-radius, radius)
                self.backend.move_relative(dx, dy, 0.15)
                time.sleep(0.2)
                self.backend.move_relative(-dx, -dy, 0.15)  # return to where it was
        finally:
            self.on_state(False)
