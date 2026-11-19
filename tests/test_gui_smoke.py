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


def test_minibar_controls_main_window(monkeypatch, tmp_path):
    from PySide6.QtWidgets import QApplication

    import tpac.app as appmod
    from tpac.inputs import NullBackend

    monkeypatch.setattr(appmod, "make_backend", lambda: (NullBackend(), None))
    monkeypatch.setattr(appmod, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    app = QApplication.instance() or QApplication([])
    w = appmod.MainWindow()
    mb = w.minibar
    assert mb.isVisible()
    w.start_delay.setValue(0)
    mb.btn_click.click()            # start clicker from the mini bar
    app.processEvents()
    assert w.clicker.running
    mb.btn_stop.click()             # stop everything
    w.clicker._thread.join(3)
    app.processEvents()
    assert not w.clicker.running
    assert mb.btn_click.text().startswith("▶")
    w.chk_minibar.setChecked(False)
    assert not mb.isVisible() and w.settings["show_minibar"] is False
    for mode in ("Light", "Dark"):  # theme switches without errors
        w.theme_mode.setCurrentText(mode)
        app.processEvents()
        assert w.scheme.dark == (mode == "Dark")
    w.seq_dirty = False
    w.close()


@pytest.mark.parametrize("font_scale", [1.0, 1.6])
def test_layout_fits_at_narrow_and_wide_sizes(monkeypatch, tmp_path, font_scale):
    """Nothing is cut off at the smallest window size, and fields don't stretch
    across a maximised window. The larger font stands in for wider system fonts
    and Windows text scaling."""
    from PySide6.QtWidgets import QAbstractButton, QAbstractSpinBox, QApplication, QComboBox

    import tpac.app as appmod
    from tpac.inputs import NullBackend

    monkeypatch.setattr(appmod, "make_backend", lambda: (NullBackend(), None))
    monkeypatch.setattr(appmod, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    app = QApplication.instance() or QApplication([])
    if font_scale != 1.0:
        import re

        import tpac.theme as th
        orig = th.stylesheet

        def bigger(*a, **k):
            return re.sub(r"font-size: (\d+)pt",
                          lambda m: f"font-size: {round(int(m.group(1)) * font_scale)}pt", orig(*a, **k))
        monkeypatch.setattr(th, "stylesheet", bigger)
    w = appmod.MainWindow()
    w.minibar.hide()
    try:
        for tab in range(w.tabs.count()):
            w.tabs.setCurrentIndex(tab)
            w.resize(100, 600)  # clamped to the minimum width
            w.show()
            app.processEvents()
            page = w.tabs.currentWidget()
            for b in page.findChildren(QAbstractButton):
                if b.isVisible():
                    assert b.width() >= b.minimumSizeHint().width(), (tab, b.text(), b.width())
                    right = b.mapTo(w, b.rect().topRight()).x()
                    assert right <= w.width(), (tab, b.text(), right, w.width())
            w.resize(2400, 1000)
            app.processEvents()
            for f in page.findChildren(QAbstractSpinBox) + page.findChildren(QComboBox):
                if f.isVisible() and f is not w.seq_combo:
                    assert f.width() <= 260, (tab, f.objectName(), f.width())
    finally:
        w.seq_dirty = False
        w.close()


def test_sidebar_switches_pages_and_mini_controls(monkeypatch, tmp_path):
    from PySide6.QtWidgets import QApplication

    import tpac.app as appmod
    from tpac.inputs import NullBackend

    monkeypatch.setattr(appmod, "make_backend", lambda: (NullBackend(), None))
    monkeypatch.setattr(appmod, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    QApplication.instance() or QApplication([])
    w = appmod.MainWindow()
    try:
        assert not w.tabs.tabBar().isVisible()
        for i, b in enumerate(w.nav_buttons):
            b.click()
            assert w.tabs.currentIndex() == i and b.isChecked()
        w.tabs.setCurrentIndex(0)
        assert w.nav_buttons[0].isChecked()
        w.nav_mini.setChecked(False)
        assert not w.chk_minibar.isChecked() and not w.settings["show_minibar"]
        w.chk_minibar.setChecked(True)
        assert w.nav_mini.isChecked()
        w.statusBar().showMessage("hello")
        assert w.statusBar().currentMessage() == "hello"
    finally:
        w.seq_dirty = False
        w.minibar.hide()
        w.close()
