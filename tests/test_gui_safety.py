"""Main-window parts of the audit fixes: reset survives quitting, hotkey
clashes, the 'check this sequence' prompt and the system-key prompt."""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("cv2")


@pytest.fixture
def window(monkeypatch, tmp_path):
    from PySide6.QtWidgets import QApplication

    import tpac.app as appmod
    from tpac.inputs import NullBackend

    sf = tmp_path / "settings.json"
    sf.write_text(json.dumps({"interval_ms": 500, "jitter_pct": 20, "monitor": 2}))
    monkeypatch.setattr(appmod, "make_backend", lambda: (NullBackend(), None))
    monkeypatch.setattr(appmod, "SETTINGS_FILE", str(sf))
    monkeypatch.setattr(appmod, "load_settings", lambda: appmod._config.load_settings(str(sf)))
    QApplication.instance() or QApplication([])
    w = appmod.MainWindow()
    yield w, sf, appmod
    w.seq_dirty = False
    w.close()


def answer(monkeypatch, appmod, reply):
    """Make every QMessageBox question/warning return ``reply`` and record the texts."""
    seen = []

    def fake(*args, **kwargs):
        seen.append(" ".join(str(a) for a in args[1:3]))
        return reply

    for name in ("question", "warning", "information"):
        monkeypatch.setattr(appmod.QMessageBox, name, staticmethod(fake))
    return seen


def test_reset_to_defaults_survives_quit(window, monkeypatch):
    w, sf, appmod = window
    answer(monkeypatch, appmod, appmod.QMessageBox.Yes)
    w._reset_defaults()
    w._on_quit()
    on_disk = json.loads(sf.read_text())
    assert (on_disk["interval_ms"], on_disk["jitter_pct"], on_disk["monitor"]) == (50, 0, 1)


def test_quit_still_saves_normally(window):
    w, sf, _ = window
    w.interval.setValue(123)
    w._on_quit()
    assert json.loads(sf.read_text())["interval_ms"] == 123


def test_duplicate_hotkey_is_detected(window):
    w, _, _ = window
    assert w._hotkey_clash("panic_hotkey", "f6") == "Start/stop clicker"
    assert w._hotkey_clash("hotkey", "F6") is None  # its own key is fine
    w.hold_key.setText("shift")
    assert w._hotkey_clash("hotkey", "shift") == "the clicker's hold key"


def test_hotkeys_paused_while_recording(window, monkeypatch):
    w, _, _ = window
    from tpac.editor import KeyCaptureDialog
    calls = []
    monkeypatch.setattr(KeyCaptureDialog, "exec", lambda self: calls.append(len(w._hotkey_handles)) or 0)
    assert len(w._hotkey_handles) == 3
    KeyCaptureDialog.ask(w)
    assert calls == [0]                      # nothing bound while the dialog is open
    assert len(w._hotkey_handles) == 3       # and bound again afterwards


def test_opening_outside_sequence_shows_its_keys(window, monkeypatch, tmp_path):
    w, _, appmod = window
    p = tmp_path / "shared.json"
    p.write_text(json.dumps({"name": "Shared", "steps": [{"type": "key", "key": "windows+r"},
                                                        {"type": "key", "key": "enter"}]}))
    seen = answer(monkeypatch, appmod, appmod.QMessageBox.No)
    w._open_sequence(str(p))
    assert w.seq.name != "Shared"            # declined: not loaded
    assert "windows+r" in seen[0] and "enter" in seen[0]

    answer(monkeypatch, appmod, appmod.QMessageBox.Yes)
    w._open_sequence(str(p))
    assert w.seq.name == "Shared" and w.seq.allow_system_keys


def test_starting_with_system_keys_asks_first(window, monkeypatch):
    w, _, appmod = window
    from tpac.sequence import Sequence
    w._set_sequence(Sequence.from_dict({"steps": [{"type": "key", "key": "alt+tab"}]}), None)
    answer(monkeypatch, appmod, appmod.QMessageBox.No)
    w.toggle_sequence(0)
    assert w.runner is None
    w.toggle_sequence(0, from_hotkey=True)  # hotkey can't show a prompt: refuse and log
    assert w.runner is None


def test_template_outside_folder_is_a_problem(window):
    w, _, _ = window
    from tpac.sequence import Sequence
    seq = Sequence.from_dict({"steps": [{"type": "wait_image", "template": "../secret.png"}]})
    assert any("inside the templates folder" in p for p in w._validate_sequence(seq))
