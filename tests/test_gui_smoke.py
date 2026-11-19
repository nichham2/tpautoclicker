"""Builds the main window off-screen with a fake input backend."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("cv2")


def test_main_window_builds(monkeypatch, tmp_path):
    from PySide6.QtWidgets import QApplication

    import tpac.app as appmod
    from tpac.inputs import NullBackend

    monkeypatch.setattr(appmod, "make_backend", lambda: (NullBackend(), None))
    monkeypatch.setattr(appmod, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    QApplication.instance() or QApplication([])
    w = appmod.MainWindow()
    assert w.seq.name.startswith("Tower defense")
    assert w.table.rowCount() == len(w.seq.steps) == 5
    assert w._validate_sequence(w.seq) == []
    # toggle a step off via the table checkbox
    from PySide6.QtCore import Qt
    w.table.item(3, 0).setCheckState(Qt.Unchecked)
    assert w.seq.steps[3]["enabled"] is False and w.seq_dirty
    w._save_settings()
    assert (tmp_path / "settings.json").exists()
    w.seq_dirty = False
    w.close()


def test_step_dialog_roundtrip_every_type():
    from PySide6.QtWidgets import QApplication

    from tpac.editor import CaptureHelper, StepDialog
    from tpac.sequence import STEP_TYPES, default_step

    QApplication.instance() or QApplication([])
    cap = CaptureHelper(lambda: None, lambda: 0)
    for t in STEP_TYPES:
        st = default_step(t)
        if "template" in st:
            st["template"] = "retry.png"
            st["region"] = [10, 20, 300, 400]
        d = StepDialog(st, templates_dir=os.path.join(ROOT, "templates"), capture=cap,
                       ref_res=(1920, 1080), screen_size=lambda: (1920, 1080),
                       test_template=lambda n, r: "ok")
        out = d.result_step()
        assert out == st, (t, out, st)


def test_gui_runs_bundled_sequence_against_fake_game(monkeypatch, tmp_path):
    from PySide6.QtWidgets import QApplication

    import tpac.app as appmod
    from tests.test_game_loop import FakeGame

    game = FakeGame()
    monkeypatch.setattr(appmod, "make_backend", lambda: (game, None))
    monkeypatch.setattr(appmod, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    app = QApplication.instance() or QApplication([])
    w = appmod.MainWindow()
    w._get_screen = lambda: game
    w.chk_min_start.setChecked(False)
    w.scan.setValue(0.05)
    w.seq.repeat = 1
    w.toggle_sequence(0)
    import time
    deadline = time.time() + 30
    while w.runner.running and time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()
    assert game.levels_started == 1 and game.speed_on
    assert "1 loop(s) completed" in w.lbl_seq.text()
    w.seq_dirty = False
    w.close()
