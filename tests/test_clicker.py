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


def test_install_bundled_files_copies_without_overwriting(tmp_path, monkeypatch):
    import tpac.config as cfg
    bundle = tmp_path / "bundle"
    (bundle / "templates").mkdir(parents=True)
    (bundle / "templates" / "a.png").write_bytes(b"new")
    (bundle / "templates" / "b.png").write_bytes(b"new")
    app = tmp_path / "app"
    (app / "templates").mkdir(parents=True)
    (app / "templates" / "a.png").write_bytes(b"mine")
    monkeypatch.setattr(cfg.sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setattr(cfg, "app_dir", lambda: str(app))
    monkeypatch.setattr(cfg, "TEMPLATES_DIR", str(app / "templates"))
    monkeypatch.setattr(cfg, "SEQUENCES_DIR", str(app / "sequences"))
    cfg.install_bundled_files()
    assert (app / "templates" / "a.png").read_bytes() == b"mine"
    assert (app / "templates" / "b.png").read_bytes() == b"new"


def test_unedited_old_bundled_sequence_is_upgraded(tmp_path, monkeypatch):
    import subprocess

    import tpac.config as cfg
    old = subprocess.run(["git", "show", "850c8c7:sequences/tower_defense_retry_loop.json"],
                         cwd=ROOT, capture_output=True)
    if old.returncode != 0:
        import pytest
        pytest.skip("git history not available")
    bundle = tmp_path / "bundle"
    (bundle / "sequences").mkdir(parents=True)
    new = open(os.path.join(ROOT, "sequences", "tower_defense_retry_loop.json"), "rb").read()
    (bundle / "sequences" / "tower_defense_retry_loop.json").write_bytes(new)
    (bundle / "sequences" / "mine.json").write_bytes(b"{}")
    app = tmp_path / "app"
    (app / "sequences").mkdir(parents=True)
    (app / "sequences" / "tower_defense_retry_loop.json").write_bytes(old.stdout.replace(b"\n", b"\r\n"))
    (app / "sequences" / "mine.json").write_bytes(b'{"edited": true}')
    monkeypatch.setattr(cfg.sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setattr(cfg, "app_dir", lambda: str(app))
    monkeypatch.setattr(cfg, "TEMPLATES_DIR", str(app / "templates"))
    monkeypatch.setattr(cfg, "SEQUENCES_DIR", str(app / "sequences"))
    cfg.install_bundled_files()
    assert (app / "sequences" / "tower_defense_retry_loop.json").read_bytes() == new
    assert (app / "sequences" / "mine.json").read_bytes() == b'{"edited": true}'


def test_v4_settings_move_to_dashboard_look(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"theme_mode": "System", "accent": "#6750A4"}))
    s = load_settings(str(p))
    assert s["theme_mode"] == "Dark" and s["accent"] == "#6C5DD3" and s["design"] == 2
    # a colour the user picked is kept, and later choices are respected
    p.write_text(json.dumps({"theme_mode": "Light", "accent": "#0B57D0"}))
    assert load_settings(str(p))["accent"] == "#0B57D0"
    p.write_text(json.dumps({"theme_mode": "Light", "accent": "#0B57D0", "design": 2}))
    assert load_settings(str(p))["theme_mode"] == "Light"
