import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tpac.clicker import AfkEngine, ClickConfig, ClickEngine  # noqa: E402
from tpac.config import DEFAULTS, load_settings  # noqa: E402
from tpac.inputs import NullBackend  # noqa: E402


def test_stop_after_clicks_and_hold_key_released():
    b = NullBackend()
    eng = ClickEngine(b)
    eng.start(ClickConfig(interval_s=0.001, stop_after_clicks=25, hold_key="shift"))
    eng._thread.join(2)
    clicks = [c for c in b.calls if c[0] == "click"]
    assert len(clicks) == 25
    assert b.calls[0] == ("key_down", "shift")
    assert b.calls[-1] == ("key_up", "shift")


def test_double_start_does_not_spawn_second_loop():
    b = NullBackend()
    eng = ClickEngine(b)
    assert eng.start(ClickConfig(interval_s=0.01))
    assert not eng.start(ClickConfig(interval_s=0.01))
    eng.stop(wait=True)
    assert not eng.running


def test_stop_is_immediate_even_with_long_interval():
    b = NullBackend()
    eng = ClickEngine(b)
    eng.start(ClickConfig(interval_s=5.0))
    time.sleep(0.05)
    t0 = time.perf_counter()
    eng.stop(wait=True)
    assert time.perf_counter() - t0 < 0.5


def test_rate_is_close_to_interval():
    b = NullBackend()
    eng = ClickEngine(b)
    eng.start(ClickConfig(interval_s=0.02, stop_after_seconds=0.5))
    eng._thread.join(2)
    n = len([c for c in b.calls if c[0] == "click"])
    assert 18 <= n <= 28, n


def test_fixed_position_moves_first():
    b = NullBackend()
    eng = ClickEngine(b)
    eng.start(ClickConfig(interval_s=0.001, stop_after_clicks=2, fixed_pos=(10, 20)))
    eng._thread.join(2)
    assert b.calls[0] == ("move", 10, 20)
    assert b.calls[1][3] == (10, 20)


def test_afk_stops_promptly():
    b = NullBackend()
    afk = AfkEngine(b)
    afk.start(interval_s=30)
    t0 = time.perf_counter()
    afk.stop()
    afk._thread.join(1)
    assert not afk.running and time.perf_counter() - t0 < 0.5


def test_legacy_settings_migrate(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"hold_key": "None", "speed": 0.2, "hotkey": "F9", "sounds": False}))
    s = load_settings(str(p))
    assert s["interval_ms"] == 200
    assert s["hold_key"] == ""
    assert s["hotkey"] == "F9" and s["sounds"] is False
    assert "speed" not in s
    assert set(DEFAULTS) <= set(s)


def test_corrupt_settings_fall_back_to_defaults(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{not json")
    assert load_settings(str(p)) == DEFAULTS
