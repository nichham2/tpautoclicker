"""Regression tests for the v4.0.0 audit fixes: stop paths, sequence
validation, system-key guard, settings loading and template paths."""
import json
import os
import sys
import time

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tpac.clicker import ClickConfig, ClickEngine, in_corner  # noqa: E402
from tpac.config import load_settings  # noqa: E402
import tpac.config as config  # noqa: E402
from tpac.inputs import NullBackend  # noqa: E402
from tpac.sequence import Sequence, SequenceRunner, is_system_key, risky_keys  # noqa: E402


class Screen:
    def __init__(self, offset=(0, 0)):
        self._offset = offset

    def size(self):
        return 1920, 1080

    def offset(self):
        return self._offset

    def grab(self):
        return np.zeros((1080, 1920, 3), np.uint8)


def backend_at(x, y):
    b = NullBackend()
    b._pos = (x, y)
    return b


def run(seq, backend=None, screen=None, failsafe=False, timeout=3.0):
    logs = []
    r = SequenceRunner(backend or backend_at(800, 800), screen or Screen(), None,
                       corner_failsafe=failsafe, log=logs.append)
    r.start(seq)
    r.join(timeout)
    return r, logs


# ---- corner helper ------------------------------------------------------------
def test_in_corner_needs_both_bounds():
    assert in_corner((0, 0), (0, 0))
    assert in_corner((1922, 1081), (1920, 1080))
    # Up and to the left of the game monitor (another screen): not the corner.
    assert not in_corner((500, 500), (1920, 1080))
    assert not in_corner((-5, 0), (0, 0))


# ---- automation failsafe (F-02) --------------------------------------------------
def test_corner_failsafe_works_during_a_long_wait():
    b = backend_at(800, 800)
    seq = Sequence.from_dict({"repeat": 1, "steps": [{"type": "wait", "seconds": 3}]})
    logs = []
    r = SequenceRunner(b, Screen(), None, corner_failsafe=True, log=logs.append)
    t0 = time.monotonic()
    r.start(seq)
    time.sleep(0.3)
    b._pos = (0, 0)
    r.join(3)
    assert not r.running
    assert time.monotonic() - t0 < 0.8
    assert any("failsafe" in line for line in logs)


def test_cursor_on_another_monitor_does_not_stop_the_run():
    seq = Sequence.from_dict({"repeat": 3, "steps": [{"type": "key", "key": "space"}]})
    r, logs = run(seq, backend=backend_at(500, 500), screen=Screen(offset=(1920, 1080)), failsafe=True)
    assert r.loops_done == 3
    assert not any("failsafe" in line for line in logs)


# ---- zero-length loops (F-05) ----------------------------------------------------
def test_zero_second_loop_does_not_spin():
    loops = []
    seq = Sequence.from_dict({"steps": [{"type": "wait", "seconds": 0}]})
    r = SequenceRunner(NullBackend(), Screen(), None, corner_failsafe=False,
                       on_loop=lambda n, s: loops.append(n))
    r.start(seq)
    time.sleep(1.0)
    r.stop()
    r.join(2)
    assert 5 <= len(loops) <= 25, len(loops)


# ---- validation (F-04) -----------------------------------------------------------
@pytest.mark.parametrize("step, field", [
    ({"type": "wait_pixel", "color": "red"}, "color"),
    ({"type": "click", "pos": [5]}, "pos"),
    ({"type": "wait_image", "template": "a.png", "region": [1, 2]}, "region"),
    ({"type": "click", "button": "side"}, "button"),
    ({"type": "wait", "on_fail": "retry"}, "on_fail"),
    ({"type": "wait", "seconds": "abc"}, "seconds"),
    ({"type": "wait", "seconds": -1}, "seconds"),
])
def test_bad_step_values_are_rejected_on_load(step, field):
    with pytest.raises(ValueError) as e:
        Sequence.from_dict({"steps": [{"type": "wait"}, step]})
    assert "Step 2" in str(e.value) and field in str(e.value)


def test_bundled_sequence_still_loads():
    seq = Sequence.load(os.path.join(ROOT, "sequences", "tower_defense_retry_loop.json"))
    assert len(seq.steps) == 5 and not risky_keys(seq)


def test_bad_value_at_run_time_follows_on_fail():
    # Built by hand (as the editor could) to get past load-time validation.
    seq = Sequence(repeat=1, steps=[
        {"type": "wait_pixel", "pos": [1, 1], "color": "zz", "tolerance": 0, "timeout": 1, "on_fail": "skip",
         "enabled": True, "label": "", "delay_after": 0},
        {"type": "key", "key": "space", "presses": 1, "on_fail": "stop", "enabled": True, "label": "",
         "delay_after": 0},
    ])
    b = NullBackend()
    r, logs = run(seq, backend=b)
    assert r.loops_done == 1
    assert ("tap", "space") in b.calls


# ---- system keys (S-01) ----------------------------------------------------------
def test_system_key_detection():
    for k in ("windows+r", "win+x", "ctrl+esc", "Alt+F4", "left windows"):
        assert is_system_key(k), k
    for k in ("space", "ctrl+s", "enter", "f6", ""):
        assert not is_system_key(k), k


def test_runner_refuses_system_keys_unless_allowed():
    steps = [{"type": "key", "key": "windows+r"}] + [{"type": "key", "key": c} for c in "calc"]
    seq = Sequence.from_dict({"repeat": 1, "steps": steps})
    b = NullBackend()
    run(seq, backend=b)
    assert not any(c[0] == "tap" for c in b.calls)

    seq = Sequence.from_dict({"repeat": 1, "allow_system_keys": True, "steps": steps})
    b = NullBackend()
    run(seq, backend=b)
    assert ("tap", "windows+r") in b.calls


def test_allow_system_keys_round_trips(tmp_path):
    p = tmp_path / "s.json"
    Sequence(steps=[], allow_system_keys=True).save(str(p))
    assert json.loads(p.read_text())["allow_system_keys"] is True
    Sequence(steps=[]).save(str(p))
    assert "allow_system_keys" not in json.loads(p.read_text())


# ---- template paths (S-03) -------------------------------------------------------
def test_templates_must_stay_in_their_folder(tmp_path):
    pytest.importorskip("cv2")
    from tpac.vision import Matcher, template_path
    tdir = tmp_path / "templates"
    tdir.mkdir()
    assert template_path(str(tdir), "retry.png") == os.path.realpath(str(tdir / "retry.png"))
    m = Matcher(str(tdir))
    for bad in ("../x.png", str(tmp_path / "x.png"), "sub/../../x.png", ""):
        with pytest.raises(ValueError):
            m.template(bad)


# ---- clicker failsafe and time limit (F-01, F-08) --------------------------------
def test_clicker_stops_when_user_grabs_mouse_in_fixed_mode():
    class Grabby(NullBackend):
        def click(self, *a, **k):
            super().click(*a, **k)
            if len([c for c in self.calls if c[0] == "click"]) == 3:
                self._pos = (self._pos[0] + 100, self._pos[1])  # the user yanks the mouse

    b = Grabby()
    b._pos = (800, 800)
    eng = ClickEngine(b)
    eng.start(ClickConfig(interval_s=0.005, fixed_pos=(400, 300), failsafe=True))
    eng._thread.join(2)
    assert not eng.running and eng.stopped_by_failsafe
    assert len([c for c in b.calls if c[0] == "click"]) == 3


def test_clicker_stops_in_corner_in_cursor_mode():
    b = backend_at(0, 0)
    eng = ClickEngine(b)
    eng.start(ClickConfig(interval_s=0.005, failsafe=True))
    eng._thread.join(2)
    assert eng.stopped_by_failsafe and not [c for c in b.calls if c[0] == "click"]


def test_clicker_failsafe_off_keeps_clicking():
    b = backend_at(0, 0)
    eng = ClickEngine(b)
    eng.start(ClickConfig(interval_s=0.001, stop_after_clicks=5, failsafe=False))
    eng._thread.join(2)
    assert len([c for c in b.calls if c[0] == "click"]) == 5


def test_stop_after_seconds_does_not_wait_out_a_long_interval():
    eng = ClickEngine(NullBackend())
    t0 = time.perf_counter()
    eng.start(ClickConfig(interval_s=2.0, stop_after_seconds=0.3))
    eng._thread.join(3)
    assert time.perf_counter() - t0 < 0.8


def test_clicker_errors_are_reported():
    class Broken(NullBackend):
        def click(self, *a, **k):
            raise OSError("input blocked")

    errors = []
    eng = ClickEngine(Broken(), on_error=errors.append)
    eng.start(ClickConfig(interval_s=0.01))
    eng._thread.join(2)
    assert errors and "input blocked" in errors[0]


# ---- settings (F-07) -------------------------------------------------------------
def test_bool_strings_load_correctly(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"mouse_corner_failsafe": "false", "sounds": "0", "notifications": "yes",
                             "multi_scale": "maybe"}))
    s = load_settings(str(p))
    assert s["mouse_corner_failsafe"] is False
    assert s["sounds"] is False
    assert s["notifications"] is True
    assert s["multi_scale"] is True  # unreadable value -> default


def test_corrupt_settings_are_kept_as_backup(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{not json")
    load_settings(str(p))
    assert not p.exists()
    assert (tmp_path / "settings.json.bad").read_text() == "{not json"
    assert config.LAST_LOAD_PROBLEM and "settings.json.bad" in config.LAST_LOAD_PROBLEM


# ---- picker screen matching (F-13) ----------------------------------------------
def test_match_screen_mixed_dpi():
    from tpac.editor import match_screen
    # Primary 1920x1080 at 100%, second 2560x1440 at 150% to its right.
    # Qt 6 keeps the second screen's origin at x=1920 but shrinks its size.
    qt6 = [(0, 0, 1920, 1080, 1.0), (1920, 0, 1707, 960, 1.5)]
    assert match_screen(qt6, (1920, 0, 2560, 1440)) == 1
    assert match_screen(qt6, (0, 0, 1920, 1080)) == 0
    # A platform that scales the origin too (1920 / 1.5 = 1280).
    scaled = [(0, 0, 1920, 1080, 1.0), (1280, 0, 1707, 960, 1.5)]
    assert match_screen(scaled, (1920, 0, 2560, 1440)) == 1
    # Monitor to the left of the primary at 125%.
    left = [(0, 0, 1920, 1080, 1.0), (-2560, 0, 2048, 1152, 1.25)]
    assert match_screen(left, (-2560, 0, 2560, 1440)) == 1
    # No screen of that size at that spot: don't guess.
    assert match_screen(qt6, (5000, 0, 1920, 1080)) is None
