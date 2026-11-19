"""Main window."""
from __future__ import annotations

import copy
import os
import sys
import threading
import webbrowser

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QMenu, QMessageBox, QPlainTextEdit, QPushButton, QRadioButton, QSpinBox,
    QSystemTrayIcon, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from . import APP_NAME, REPO_NAME, REPO_OWNER, VERSION
from .clicker import AfkEngine, ClickConfig, ClickEngine
from .config import (
    DEFAULTS, SEQUENCES_DIR, SETTINGS_FILE, TEMPLATES_DIR, app_dir, bundled_dir,
    install_bundled_files, load_settings, save_settings,
)
from .editor import CaptureHelper, KeyCaptureDialog, StepDialog
from .inputs import enable_dpi_awareness, make_backend
from .sequence import STEP_TYPES, Sequence, SequenceRunner, default_step, describe_step

try:
    import winsound
except ImportError:  # not Windows
    winsound = None


class Bridge(QObject):
    """Worker threads -> UI thread. Qt widgets must only be touched on the UI thread."""

    log = Signal(str)
    clicker_state = Signal(bool)
    clicker_count = Signal(int)
    afk_state = Signal(bool)
    seq_state = Signal(bool)
    seq_step = Signal(int, int)
    seq_loop = Signal(int, float)
    hotkey = Signal(str)


def _icon() -> QIcon:
    path = os.path.join(bundled_dir(), "icon.ico")
    if os.path.exists(path):
        return QIcon(path)
    pix = QPixmap(64, 64)
    pix.fill(QColor(30, 30, 30))
    p = QPainter(pix)
    p.setBrush(QColor(0, 180, 220))
    p.drawEllipse(12, 12, 40, 40)
    p.end()
    return QIcon(pix)


def _version_tuple(v: str):
    parts = []
    for piece in v.lstrip("vV").split("."):
        num = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(num) if num else 0)
    return tuple(parts + [0] * (3 - len(parts)))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        self.setWindowIcon(_icon())
        self.setMinimumSize(640, 560)

        self.settings = load_settings()
        self.backend, backend_err = make_backend()
        self.bridge = Bridge()
        self._hotkey_handles = []
        self._screen = None
        self._screen_monitor = None
        self.seq: Sequence = Sequence()
        self.seq_path: str | None = None
        self.seq_dirty = False

        self.clicker = ClickEngine(self.backend, self.bridge.clicker_state.emit, self.bridge.clicker_count.emit)
        self.afk = AfkEngine(self.backend, self.bridge.afk_state.emit)
        self.runner: SequenceRunner | None = None
        self.capture = CaptureHelper(self._get_screen, lambda: self.capture_delay.value(), self)

        self._apply_theme()
        self._build_ui()
        self._create_tray()
        self._connect_bridge()
        self._load_initial_sequence()
        self._bind_hotkeys()

        if backend_err is not None:
            self.log(f"Mouse/keyboard control unavailable ({backend_err}). "
                     "Install requirements and, on Linux, run as root.")
        QApplication.instance().aboutToQuit.connect(self._on_quit)

    # ==================================================================== UI
    def _build_ui(self):
        self.tabs = QTabWidget()
        self.tabs.addTab(self._clicker_tab(), "Clicker")
        self.tabs.addTab(self._automation_tab(), "Automation")
        self.tabs.addTab(self._log_tab(), "Log")
        self.tabs.addTab(self._settings_tab(), "Settings")
        self.setCentralWidget(self.tabs)
        self.statusBar().showMessage("Ready")

    # ---------------------------------------------------------------- clicker
    def _clicker_tab(self):
        s = self.settings
        w = QWidget()
        v = QVBoxLayout(w)

        top = QHBoxLayout()
        self.btn_click = QPushButton()
        self.btn_click.setMinimumHeight(48)
        self.btn_click.clicked.connect(self.toggle_clicker)
        top.addWidget(self.btn_click, 3)
        self.lbl_clicks = QLabel("0 clicks")
        self.lbl_clicks.setAlignment(Qt.AlignCenter)
        self.lbl_clicks.setMinimumWidth(120)
        top.addWidget(self.lbl_clicks, 1)
        v.addLayout(top)

        g = QGroupBox("Click")
        f = QFormLayout(g)
        self.mb = QComboBox()
        self.mb.addItems(["Left", "Right", "Middle"])
        self.mb.setCurrentText(s["mouse_button"])
        self.click_type = QComboBox()
        self.click_type.addItems(["Single", "Double"])
        self.click_type.setCurrentText(s["click_type"])
        row = QHBoxLayout()
        row.addWidget(self.mb)
        row.addWidget(self.click_type)
        f.addRow("Button:", row)

        row = QHBoxLayout()
        self.interval = QSpinBox()
        self.interval.setRange(1, 3_600_000)
        self.interval.setSuffix(" ms")
        self.interval.setValue(s["interval_ms"])
        self.lbl_cps = QLabel()
        self.interval.valueChanged.connect(self._update_cps)
        row.addWidget(self.interval)
        row.addWidget(self.lbl_cps)
        for label, ms in [("Slow", 200), ("Med", 100), ("Fast", 50), ("Max", 10)]:
            b = QPushButton(label)
            b.setMaximumWidth(56)
            b.clicked.connect(lambda _=False, m=ms: self.interval.setValue(m))
            row.addWidget(b)
        f.addRow("Interval:", row)

        self.jitter = QSpinBox()
        self.jitter.setRange(0, 50)
        self.jitter.setSuffix(" %")
        self.jitter.setValue(s["jitter_pct"])
        self.jitter.setToolTip("Randomise each interval by up to this much so clicks look less robotic")
        f.addRow("Random variation:", self.jitter)
        v.addWidget(g)

        g = QGroupBox("Where to click")
        h = QHBoxLayout(g)
        self.loc_cursor = QRadioButton("Wherever the cursor is")
        self.loc_fixed = QRadioButton("Fixed spot")
        grp = QButtonGroup(g)
        grp.addButton(self.loc_cursor)
        grp.addButton(self.loc_fixed)
        (self.loc_fixed if s["location_mode"] == "Fixed" else self.loc_cursor).setChecked(True)
        self.fx, self.fy = QSpinBox(), QSpinBox()
        for sp, val in ((self.fx, s["fixed_x"]), (self.fy, s["fixed_y"])):
            sp.setRange(-20000, 20000)
            sp.setValue(val)
        btn_pick = QPushButton("Pick…")
        btn_pick.clicked.connect(self._pick_fixed)
        h.addWidget(self.loc_cursor)
        h.addWidget(self.loc_fixed)
        h.addWidget(QLabel("x"))
        h.addWidget(self.fx)
        h.addWidget(QLabel("y"))
        h.addWidget(self.fy)
        h.addWidget(btn_pick)
        v.addWidget(g)

        g = QGroupBox("Options")
        f = QFormLayout(g)
        row = QHBoxLayout()
        self.stop_clicks = QSpinBox()
        self.stop_clicks.setRange(0, 10_000_000)
        self.stop_clicks.setSpecialValueText("never")
        self.stop_clicks.setSuffix(" clicks")
        self.stop_clicks.setValue(s["stop_after_clicks"])
        self.stop_secs = QSpinBox()
        self.stop_secs.setRange(0, 86_400)
        self.stop_secs.setSpecialValueText("never")
        self.stop_secs.setSuffix(" s")
        self.stop_secs.setValue(s["stop_after_seconds"])
        row.addWidget(self.stop_clicks)
        row.addWidget(QLabel("or"))
        row.addWidget(self.stop_secs)
        f.addRow("Stop after:", row)

        row = QHBoxLayout()
        self.hold_key = QLineEdit(s["hold_key"])
        self.hold_key.setReadOnly(True)
        self.hold_key.setPlaceholderText("none")
        b = QPushButton("Set…")
        b.clicked.connect(self._set_hold_key)
        row.addWidget(self.hold_key)
        row.addWidget(b)
        f.addRow("Hold key while clicking:", row)

        self.start_delay = QDoubleSpinBox()
        self.start_delay.setRange(0, 60)
        self.start_delay.setSuffix(" s")
        self.start_delay.setValue(s["start_delay_s"])
        f.addRow("Delay before starting:", self.start_delay)
        v.addWidget(g)

        g = QGroupBox("Anti-AFK")
        h = QHBoxLayout(g)
        self.btn_afk = QPushButton("Start anti-AFK")
        self.btn_afk.clicked.connect(self.toggle_afk)
        self.afk_interval = QSpinBox()
        self.afk_interval.setRange(1, 3600)
        self.afk_interval.setSuffix(" s")
        self.afk_interval.setPrefix("every ")
        self.afk_interval.setValue(s["afk_interval_s"])
        h.addWidget(self.btn_afk)
        h.addWidget(self.afk_interval)
        h.addStretch()
        v.addWidget(g)
        v.addStretch()

        self._update_cps()
        self._set_clicker_ui(False)
        return w

    def _update_cps(self):
        ms = self.interval.value()
        self.lbl_cps.setText(f"≈ {1000.0 / ms:.1f} clicks/s")

    # ------------------------------------------------------------- automation
    def _automation_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)

        row = QHBoxLayout()
        self.seq_combo = QComboBox()
        self.seq_combo.setMinimumWidth(220)
        self.seq_combo.activated.connect(self._on_seq_combo)
        row.addWidget(QLabel("Sequence:"))
        row.addWidget(self.seq_combo, 1)
        for text, fn in [("New", self._seq_new), ("Open…", self._seq_open),
                         ("Save", self._seq_save), ("Save as…", self._seq_save_as)]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        v.addLayout(row)

        row = QHBoxLayout()
        self.seq_name = QLineEdit()
        self.seq_name.textEdited.connect(self._seq_meta_changed)
        self.seq_repeat = QSpinBox()
        self.seq_repeat.setRange(0, 1_000_000)
        self.seq_repeat.setSpecialValueText("forever")
        self.seq_repeat.setSuffix(" loops")
        self.seq_repeat.valueChanged.connect(self._seq_meta_changed)
        self.lbl_ref = QLabel()
        row.addWidget(QLabel("Name:"))
        row.addWidget(self.seq_name, 1)
        row.addWidget(QLabel("Repeat:"))
        row.addWidget(self.seq_repeat)
        row.addWidget(self.lbl_ref)
        v.addLayout(row)

        self.seq_notes = QLabel()
        self.seq_notes.setWordWrap(True)
        self.seq_notes.setStyleSheet("color: gray")
        v.addWidget(self.seq_notes)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["On", "Step", "Details", "If it fails"])
        self.table.verticalHeader().setVisible(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.cellDoubleClicked.connect(lambda r, c: self._step_edit())
        self.table.itemChanged.connect(self._on_table_item_changed)
        v.addWidget(self.table, 1)

        row = QHBoxLayout()
        add = QPushButton("Add step ▾")
        menu = QMenu(add)
        for t, spec in STEP_TYPES.items():
            act = menu.addAction(spec["title"])
            act.triggered.connect(lambda _=False, tt=t: self._step_add(tt))
        add.setMenu(menu)
        row.addWidget(add)
        for text, fn in [("Edit", self._step_edit), ("Duplicate", self._step_dup), ("Delete", self._step_del),
                         ("▲", lambda: self._step_move(-1)), ("▼", lambda: self._step_move(1)),
                         ("Capture image…", self._capture_template_only)]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            if text in ("▲", "▼"):
                b.setMaximumWidth(36)
            row.addWidget(b)
        row.addStretch()
        v.addLayout(row)

        row = QHBoxLayout()
        self.btn_seq = QPushButton()
        self.btn_seq.setMinimumHeight(44)
        self.btn_seq.clicked.connect(lambda: self.toggle_sequence(0))
        self.btn_seq_from = QPushButton("Start from selected step")
        self.btn_seq_from.clicked.connect(lambda: self.toggle_sequence(max(0, self.table.currentRow())))
        row.addWidget(self.btn_seq, 2)
        row.addWidget(self.btn_seq_from, 1)
        v.addLayout(row)

        self.lbl_seq = QLabel("Idle")
        v.addWidget(self.lbl_seq)
        tip = QLabel("Tip: slam the mouse into the top-left corner of the screen, or press the stop "
                     "hotkey, to stop instantly.")
        tip.setStyleSheet("color: gray")
        tip.setWordWrap(True)
        v.addWidget(tip)
        self._set_seq_ui(False)
        return w

    def _log_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        v.addWidget(self.log_view)
        b = QPushButton("Clear")
        b.clicked.connect(self.log_view.clear)
        v.addWidget(b, 0, Qt.AlignRight)
        return w

    # --------------------------------------------------------------- settings
    def _hotkey_row(self, key):
        edit = QLineEdit(self.settings[key])
        edit.setReadOnly(True)
        b = QPushButton("Set…")

        def set_():
            k = KeyCaptureDialog.ask(self, "Press the new hotkey", allow_clear=False)
            if k:
                edit.setText(k)
                self.settings[key] = k
                self._bind_hotkeys()
                self._refresh_button_texts()
        b.clicked.connect(set_)
        row = QHBoxLayout()
        row.addWidget(edit)
        row.addWidget(b)
        return row, edit

    def _settings_tab(self):
        s = self.settings
        w = QWidget()
        v = QVBoxLayout(w)

        g = QGroupBox("Hotkeys (work while the game is focused)")
        f = QFormLayout(g)
        r, self.hk_click = self._hotkey_row("hotkey")
        f.addRow("Start/stop clicker:", r)
        r, self.hk_seq = self._hotkey_row("sequence_hotkey")
        f.addRow("Start/stop automation:", r)
        r, self.hk_panic = self._hotkey_row("panic_hotkey")
        f.addRow("Stop everything:", r)
        v.addWidget(g)

        g = QGroupBox("Automation")
        f = QFormLayout(g)
        self.monitor = QSpinBox()
        self.monitor.setRange(1, 16)
        self.monitor.setValue(s["monitor"])
        self.monitor.setToolTip("Which monitor the game is on (1 = main monitor)")
        f.addRow("Game monitor:", self.monitor)
        self.scan = QDoubleSpinBox()
        self.scan.setRange(0.05, 10)
        self.scan.setSingleStep(0.1)
        self.scan.setSuffix(" s")
        self.scan.setValue(s["scan_interval_s"])
        f.addRow("Check screen every:", self.scan)
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(0.3, 0.99)
        self.threshold.setSingleStep(0.05)
        self.threshold.setValue(s["match_threshold"])
        self.threshold.setToolTip("How closely the screen must match a captured image. Lower = looser.")
        f.addRow("Match confidence:", self.threshold)
        self.multi_scale = QCheckBox("Also look for images at other sizes (different resolutions)")
        self.multi_scale.setChecked(s["multi_scale"])
        f.addRow(self.multi_scale)
        self.failsafe = QCheckBox("Stop when the mouse hits the top-left corner")
        self.failsafe.setChecked(s["mouse_corner_failsafe"])
        f.addRow(self.failsafe)
        self.capture_delay = QDoubleSpinBox()
        self.capture_delay.setRange(0, 15)
        self.capture_delay.setSuffix(" s")
        self.capture_delay.setValue(s["capture_delay_s"])
        self.capture_delay.setToolTip("Time to switch to the game before a screenshot is taken")
        f.addRow("Capture delay:", self.capture_delay)
        v.addWidget(g)

        g = QGroupBox("App")
        f = QVBoxLayout(g)
        self.chk_min_start = QCheckBox("Minimise this window when starting")
        self.chk_min_start.setChecked(s["minimize_on_start"])
        self.chk_tray = QCheckBox("Closing the window hides it to the tray")
        self.chk_tray.setChecked(s["minimize_to_tray"])
        self.chk_notif = QCheckBox("Show notifications")
        self.chk_notif.setChecked(s["notifications"])
        self.chk_sound = QCheckBox("Play sounds")
        self.chk_sound.setChecked(s["sounds"])
        for c in (self.chk_min_start, self.chk_tray, self.chk_notif, self.chk_sound):
            f.addWidget(c)
        v.addWidget(g)

        row = QHBoxLayout()
        for label, fn in [("Check for updates", self._check_update), ("Save settings", self._save_settings_clicked),
                          ("Reset to defaults", self._reset_defaults), ("Open app folder", self._open_folder)]:
            b = QPushButton(label)
            b.clicked.connect(fn)
            row.addWidget(b)
        v.addLayout(row)
        v.addStretch()
        return w

    def _apply_theme(self):
        app = QApplication.instance()
        bg = app.palette().color(QPalette.Window)
        if 0.299 * bg.redF() + 0.587 * bg.greenF() + 0.114 * bg.blueF() < 0.5:
            app.setStyle("Fusion")

    def _create_tray(self):
        self.tray = QSystemTrayIcon(_icon(), self)
        menu = QMenu()
        menu.addAction("Show", self._show_window)
        menu.addAction("Start/stop clicker", self.toggle_clicker)
        menu.addAction("Start/stop automation", lambda: self.toggle_sequence(0))
        menu.addSeparator()
        menu.addAction("Exit", QApplication.instance().quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: self._show_window() if r == QSystemTrayIcon.DoubleClick else None)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def _show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # ============================================================== plumbing
    def _connect_bridge(self):
        b = self.bridge
        b.log.connect(self.log)
        b.clicker_state.connect(self._on_clicker_state)
        b.clicker_count.connect(lambda n: self.lbl_clicks.setText(f"{n:,} clicks"))
        b.afk_state.connect(self._on_afk_state)
        b.seq_state.connect(self._on_seq_state)
        b.seq_step.connect(self._on_seq_step)
        b.seq_loop.connect(self._on_seq_loop)
        b.hotkey.connect(self._on_hotkey)

    def log(self, msg: str):
        from datetime import datetime
        self.log_view.appendPlainText(f"{datetime.now():%H:%M:%S}  {msg}")
        self.statusBar().showMessage(msg, 5000)

    def _notify(self, msg: str, high: bool):
        if self.chk_sound.isChecked():
            if winsound is not None:
                threading.Thread(target=winsound.Beep, args=(1000 if high else 500, 120), daemon=True).start()
            else:
                QApplication.beep()
        if self.chk_notif.isChecked() and self.tray.isVisible():
            self.tray.showMessage(APP_NAME, msg, QSystemTrayIcon.Information, 1200)

    def _bind_hotkeys(self):
        for h in self._hotkey_handles:
            self.backend.remove_hotkey(h)
        self._hotkey_handles = []
        for name in ("hotkey", "sequence_hotkey", "panic_hotkey"):
            combo = self.settings.get(name)
            if not combo:
                continue
            try:
                # keyboard calls back on its own thread: hop to the UI thread.
                self._hotkey_handles.append(
                    self.backend.add_hotkey(combo, lambda n=name: self.bridge.hotkey.emit(n)))
            except Exception as e:
                self.log(f"Could not bind hotkey {combo!r}: {e}")
        self._refresh_button_texts()

    def _on_hotkey(self, name):
        if name == "hotkey":
            self.toggle_clicker(from_hotkey=True)
        elif name == "sequence_hotkey":
            self.toggle_sequence(0, from_hotkey=True)
        elif name == "panic_hotkey":
            self.stop_all()

    def _refresh_button_texts(self):
        if not hasattr(self, "btn_seq"):
            return
        self._set_clicker_ui(self.clicker.running)
        self._set_seq_ui(self.runner is not None and self.runner.running)

    # ================================================================ clicker
    def _click_config(self) -> ClickConfig:
        fixed = (self.fx.value(), self.fy.value()) if self.loc_fixed.isChecked() else None
        return ClickConfig(
            button=self.mb.currentText().lower(),
            clicks_per_event=2 if self.click_type.currentText() == "Double" else 1,
            interval_s=self.interval.value() / 1000.0,
            jitter_pct=self.jitter.value(),
            fixed_pos=fixed,
            stop_after_clicks=self.stop_clicks.value(),
            stop_after_seconds=self.stop_secs.value(),
            hold_key=self.hold_key.text().strip(),
            start_delay_s=self.start_delay.value(),
        )

    def toggle_clicker(self, from_hotkey=False):
        if self.clicker.running:
            self.clicker.stop()
            return
        if self.runner is not None and self.runner.running:
            self.log("Automation is running; stop it before using the clicker.")
            return
        cfg = self._click_config()
        if not from_hotkey:
            if self.chk_min_start.isChecked():
                self.showMinimized()
            if cfg.fixed_pos is None and cfg.start_delay_s < 2:
                cfg.start_delay_s = 2.0  # otherwise the first click lands on our own button
                self.log("Starting in 2 s: move the cursor to where you want to click")
        self.clicker.start(cfg)

    def _on_clicker_state(self, running):
        self._set_clicker_ui(running)
        self._notify("Clicking started" if running else f"Clicking stopped ({self.clicker.count:,} clicks)", running)
        self.log("Clicker started" if running else f"Clicker stopped after {self.clicker.count:,} clicks")

    def _set_clicker_ui(self, running):
        hk = self.settings.get("hotkey", "")
        self.btn_click.setText(("■ Stop clicking" if running else "▶ Start clicking") + (f"   [{hk.upper()}]" if hk else ""))

    def toggle_afk(self):
        if self.afk.running:
            self.afk.stop()
        else:
            self.afk.start(self.afk_interval.value(), self.settings.get("afk_radius_px", 5))

    def _on_afk_state(self, running):
        self.btn_afk.setText("Stop anti-AFK" if running else "Start anti-AFK")
        self.log("Anti-AFK on" if running else "Anti-AFK off")

    def _set_hold_key(self):
        k = KeyCaptureDialog.ask(self, "Key to hold while clicking")
        if k is not None:
            self.hold_key.setText(k)

    def _pick_fixed(self):
        def done(pt, _img):
            if pt:
                ox, oy = self._get_screen().offset()
                self.fx.setValue(pt[0] + ox)
                self.fy.setValue(pt[1] + oy)
                self.loc_fixed.setChecked(True)
        self.capture.pick("point", [self], done, "Click where the auto clicker should click. Esc cancels.")

    def stop_all(self):
        self.clicker.stop()
        self.afk.stop()
        if self.runner is not None:
            self.runner.stop()
        self.log("Stopped everything (panic hotkey)")

    # ============================================================= automation
    def _get_screen(self):
        from .vision import Screen
        mon = self.monitor.value() if hasattr(self, "monitor") else self.settings["monitor"]
        if self._screen is None or self._screen_monitor != mon:
            self._screen = Screen(mon)
            self._screen_monitor = mon
        return self._screen

    def _make_matcher(self, seq: Sequence):
        from .vision import Matcher
        return Matcher(TEMPLATES_DIR, reference_height=seq.reference_resolution[1],
                       threshold=self.threshold.value(), multi_scale=self.multi_scale.isChecked())

    def _validate_sequence(self, seq: Sequence) -> list[str]:
        problems = []
        for i, st in enumerate(seq.steps, 1):
            if not st.get("enabled", True):
                continue
            tpl = st.get("template")
            if "template" in st and (not tpl or not os.path.exists(os.path.join(TEMPLATES_DIR, tpl))):
                problems.append(f"Step {i}: image '{tpl}' is missing from the templates folder")
        if not any(st.get("enabled", True) for st in seq.steps):
            problems.append("The sequence has no enabled steps")
        return problems

    def toggle_sequence(self, start_at=0, from_hotkey=False):
        if self.runner is not None and self.runner.running:
            self.runner.stop()
            return
        if self.clicker.running:
            self.clicker.stop(wait=True)
        problems = self._validate_sequence(self.seq)
        if problems:
            msg = "\n".join(problems)
            self.log("Cannot start: " + msg.replace("\n", "; "))
            if not from_hotkey:
                QMessageBox.warning(self, "Cannot start", msg)
            return
        try:
            matcher = self._make_matcher(self.seq)
            screen = self._get_screen()
            screen.size()
        except Exception as e:
            self.log(f"Cannot start automation: {e}")
            if not from_hotkey:
                QMessageBox.warning(self, "Cannot start", str(e))
            return
        b = self.bridge
        self.runner = SequenceRunner(
            self.backend, screen, matcher,
            scan_interval=self.scan.value(), corner_failsafe=self.failsafe.isChecked(),
            log=b.log.emit, on_state=b.seq_state.emit, on_step=b.seq_step.emit, on_loop=b.seq_loop.emit,
        )
        if not from_hotkey and self.chk_min_start.isChecked():
            self.showMinimized()
        self.runner.start(copy.deepcopy(self.seq), start_at)

    def _on_seq_state(self, running):
        self._set_seq_ui(running)
        self.table.setEnabled(not running)
        self._notify("Automation started" if running else "Automation stopped", running)

    def _set_seq_ui(self, running):
        hk = self.settings.get("sequence_hotkey", "")
        self.btn_seq.setText(("■ Stop automation" if running else "▶ Start automation") + (f"   [{hk.upper()}]" if hk else ""))
        self.btn_seq_from.setEnabled(not running)

    def _on_seq_step(self, idx, loop):
        if idx < 0:
            self.lbl_seq.setText(f"Idle — {loop} loop(s) completed")
            self.table.clearSelection()
            return
        self.table.selectRow(idx)
        st = self.seq.steps[idx] if idx < len(self.seq.steps) else {}
        name = st.get("label") or STEP_TYPES.get(st.get("type"), {}).get("title", "")
        self.lbl_seq.setText(f"Loop {loop + 1} · step {idx + 1}: {name}")

    def _on_seq_loop(self, loops, secs):
        self.statusBar().showMessage(f"{loops} loop(s) done · last one took {secs:.0f}s")

    def _test_template(self, name, region_ref):
        from .vision import Matcher
        try:
            screen = self._get_screen()
            img = screen.grab()
            m = Matcher(TEMPLATES_DIR, reference_height=self.seq.reference_resolution[1],
                        threshold=self.threshold.value(), multi_scale=True)
            region = None
            if region_ref:
                sw, sh = screen.size()
                rw, rh = self.seq.reference_resolution
                region = (int(region_ref[0] * sw / rw), int(region_ref[1] * sh / rh),
                          int(region_ref[2] * sw / rw), int(region_ref[3] * sh / rh))
            hit = m.find(img, name, threshold=-1, region=region)
        except Exception as e:
            return f"Test failed: {e}"
        if hit is None:
            return "Not found."
        verdict = "FOUND" if hit.score >= self.threshold.value() else "not matched"
        return (f"{verdict}: confidence {hit.score:.2f} (needs {self.threshold.value():.2f})\n"
                f"at ({hit.center[0]}, {hit.center[1]}), size scale {hit.scale:.2f}\n\n"
                "Make sure the game is showing this image when you test.")

    # ---- sequence files ----------------------------------------------------
    def _refresh_seq_combo(self):
        self.seq_combo.blockSignals(True)
        self.seq_combo.clear()
        if os.path.isdir(SEQUENCES_DIR):
            for f in sorted(os.listdir(SEQUENCES_DIR)):
                if f.lower().endswith(".json"):
                    self.seq_combo.addItem(f, os.path.join(SEQUENCES_DIR, f))
        if self.seq_path:
            i = self.seq_combo.findData(self.seq_path)
            if i < 0:
                self.seq_combo.addItem(os.path.basename(self.seq_path), self.seq_path)
                i = self.seq_combo.count() - 1
            self.seq_combo.setCurrentIndex(i)
        self.seq_combo.blockSignals(False)

    def _load_initial_sequence(self):
        path = os.path.join(SEQUENCES_DIR, self.settings.get("last_sequence", ""))
        if not os.path.isfile(path) and os.path.isdir(SEQUENCES_DIR):
            files = sorted(f for f in os.listdir(SEQUENCES_DIR) if f.endswith(".json"))
            path = os.path.join(SEQUENCES_DIR, files[0]) if files else ""
        if path and os.path.isfile(path):
            self._open_sequence(path)
        else:
            self._set_sequence(Sequence(), None)

    def _open_sequence(self, path):
        try:
            seq = Sequence.load(path)
        except Exception as e:
            QMessageBox.warning(self, "Open sequence", f"Could not open {path}:\n{e}")
            return
        self._set_sequence(seq, path)
        self.log(f"Loaded sequence '{seq.name}'")

    def _set_sequence(self, seq, path):
        self.seq = seq
        self.seq_path = path
        self.seq_dirty = False
        self.seq_name.setText(seq.name)
        self.seq_repeat.blockSignals(True)
        self.seq_repeat.setValue(seq.repeat)
        self.seq_repeat.blockSignals(False)
        self.seq_notes.setText(seq.notes)
        self.seq_notes.setVisible(bool(seq.notes))
        self.lbl_ref.setText(f"positions for {seq.reference_resolution[0]}×{seq.reference_resolution[1]}")
        self._refresh_seq_combo()
        self._refresh_table()

    def _confirm_discard(self) -> bool:
        if not self.seq_dirty:
            return True
        r = QMessageBox.question(self, "Unsaved changes", "Save changes to the current sequence first?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            return self._seq_save()
        return r == QMessageBox.Discard

    def _on_seq_combo(self, i):
        path = self.seq_combo.itemData(i)
        if path == self.seq_path:
            return
        if self._confirm_discard():
            self._open_sequence(path)
        else:
            self._refresh_seq_combo()

    def _seq_new(self):
        if not self._confirm_discard():
            return
        sw, sh = (1920, 1080)
        try:
            sw, sh = self._get_screen().size()
        except Exception:
            pass
        self._set_sequence(Sequence(name="New sequence", reference_resolution=(sw, sh)), None)
        self.seq_dirty = True

    def _seq_open(self):
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open sequence", SEQUENCES_DIR, "Sequences (*.json)")
        if path:
            self._open_sequence(path)

    def _seq_save(self) -> bool:
        if not self.seq_path:
            return self._seq_save_as()
        try:
            self.seq.save(self.seq_path)
        except Exception as e:
            QMessageBox.warning(self, "Save sequence", str(e))
            return False
        self.seq_dirty = False
        self.log(f"Saved {os.path.basename(self.seq_path)}")
        return True

    def _seq_save_as(self) -> bool:
        os.makedirs(SEQUENCES_DIR, exist_ok=True)
        default = os.path.join(SEQUENCES_DIR, (self.seq.name or "sequence").replace(" ", "_").lower() + ".json")
        path, _ = QFileDialog.getSaveFileName(self, "Save sequence", default, "Sequences (*.json)")
        if not path:
            return False
        if not path.lower().endswith(".json"):
            path += ".json"
        self.seq_path = path
        ok = self._seq_save()
        self._refresh_seq_combo()
        return ok

    def _seq_meta_changed(self, *_):
        self.seq.name = self.seq_name.text()
        self.seq.repeat = self.seq_repeat.value()
        self.seq_dirty = True

    # ---- step table --------------------------------------------------------
    def _refresh_table(self, select=None):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.seq.steps))
        for r, st in enumerate(self.seq.steps):
            on = QTableWidgetItem()
            on.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            on.setCheckState(Qt.Checked if st.get("enabled", True) else Qt.Unchecked)
            self.table.setItem(r, 0, on)
            title = st.get("label") or STEP_TYPES[st["type"]]["title"]
            self.table.setItem(r, 1, QTableWidgetItem(title))
            self.table.setItem(r, 2, QTableWidgetItem(describe_step(st)))
            self.table.setItem(r, 3, QTableWidgetItem(st.get("on_fail", "stop")))
            if not st.get("enabled", True):
                for c in range(1, 4):
                    self.table.item(r, c).setForeground(QColor(128, 128, 128))
        self.table.blockSignals(False)
        if select is not None and 0 <= select < len(self.seq.steps):
            self.table.selectRow(select)

    def _on_table_item_changed(self, item):
        if item.column() == 0:
            self.seq.steps[item.row()]["enabled"] = item.checkState() == Qt.Checked
            self.seq_dirty = True
            self._refresh_table(item.row())

    def _edit_dialog(self, step):
        d = StepDialog(step, templates_dir=TEMPLATES_DIR, capture=self.capture,
                       ref_res=self.seq.reference_resolution, screen_size=lambda: self._get_screen().size(),
                       test_template=self._test_template, parent=self)
        return d.result_step() if d.exec() == QDialog.Accepted else None

    def _step_add(self, step_type):
        st = self._edit_dialog(default_step(step_type))
        if st is None:
            return
        row = self.table.currentRow()
        at = row + 1 if row >= 0 else len(self.seq.steps)
        self.seq.steps.insert(at, st)
        self.seq_dirty = True
        self._refresh_table(at)

    def _step_edit(self):
        r = self.table.currentRow()
        if r < 0:
            return
        st = self._edit_dialog(self.seq.steps[r])
        if st is not None:
            self.seq.steps[r] = st
            self.seq_dirty = True
            self._refresh_table(r)

    def _step_dup(self):
        r = self.table.currentRow()
        if r >= 0:
            self.seq.steps.insert(r + 1, copy.deepcopy(self.seq.steps[r]))
            self.seq_dirty = True
            self._refresh_table(r + 1)

    def _step_del(self):
        r = self.table.currentRow()
        if r >= 0:
            del self.seq.steps[r]
            self.seq_dirty = True
            self._refresh_table(min(r, len(self.seq.steps) - 1))

    def _step_move(self, d):
        r = self.table.currentRow()
        n = r + d
        if r < 0 or not (0 <= n < len(self.seq.steps)):
            return
        s = self.seq.steps
        s[r], s[n] = s[n], s[r]
        self.seq_dirty = True
        self._refresh_table(n)

    def _capture_template_only(self):
        self.capture.capture_template(TEMPLATES_DIR, [self],
                                      lambda f: self.log(f"Saved image templates/{f}") if f else None)

    # ================================================================ settings
    def _collect_settings(self):
        s = self.settings
        s.update({
            "mouse_button": self.mb.currentText(),
            "click_type": self.click_type.currentText(),
            "interval_ms": self.interval.value(),
            "jitter_pct": self.jitter.value(),
            "location_mode": "Fixed" if self.loc_fixed.isChecked() else "Cursor",
            "fixed_x": self.fx.value(),
            "fixed_y": self.fy.value(),
            "stop_after_clicks": self.stop_clicks.value(),
            "stop_after_seconds": self.stop_secs.value(),
            "hold_key": self.hold_key.text(),
            "start_delay_s": self.start_delay.value(),
            "afk_interval_s": self.afk_interval.value(),
            "monitor": self.monitor.value(),
            "scan_interval_s": self.scan.value(),
            "match_threshold": self.threshold.value(),
            "multi_scale": self.multi_scale.isChecked(),
            "mouse_corner_failsafe": self.failsafe.isChecked(),
            "capture_delay_s": self.capture_delay.value(),
            "minimize_on_start": self.chk_min_start.isChecked(),
            "minimize_to_tray": self.chk_tray.isChecked(),
            "notifications": self.chk_notif.isChecked(),
            "sounds": self.chk_sound.isChecked(),
        })
        if self.seq_path and os.path.dirname(os.path.abspath(self.seq_path)) == os.path.abspath(SEQUENCES_DIR):
            s["last_sequence"] = os.path.basename(self.seq_path)
        return s

    def _save_settings(self, quiet=True):
        try:
            save_settings(self._collect_settings(), SETTINGS_FILE)
            if not quiet:
                self.log("Settings saved")
        except Exception as e:
            self.log(f"Could not save settings: {e}")

    def _save_settings_clicked(self):
        self._save_settings(quiet=False)

    def _reset_defaults(self):
        if QMessageBox.question(self, "Reset", "Reset all settings to defaults?") != QMessageBox.Yes:
            return
        last = self.settings.get("last_sequence")
        self.settings = copy.deepcopy(DEFAULTS)
        self.settings["last_sequence"] = last
        save_settings(self.settings, SETTINGS_FILE)
        QMessageBox.information(self, "Reset", "Defaults restored. Restart the app to apply them everywhere.")

    def _open_folder(self):
        webbrowser.open("file://" + app_dir())

    def _check_update(self):
        try:
            import requests
            r = requests.get(f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest",
                             timeout=6, headers={"Accept": "application/vnd.github+json"})
            if r.status_code == 404:
                QMessageBox.information(self, "Updates", "No releases have been published yet.")
                return
            r.raise_for_status()
            data = r.json()
            latest = data.get("tag_name", "0")
            if _version_tuple(latest) > _version_tuple(VERSION):
                if QMessageBox.question(self, "Update available",
                                        f"Version {latest} is available (you have {VERSION}). Open the download page?") \
                        == QMessageBox.Yes:
                    webbrowser.open(data.get("html_url") or f"https://github.com/{REPO_OWNER}/{REPO_NAME}/releases")
            else:
                QMessageBox.information(self, "Updates", f"You're on the latest version ({VERSION}).")
        except Exception as e:
            QMessageBox.warning(self, "Updates", f"Update check failed: {e}")

    # ================================================================ closing
    def closeEvent(self, ev):
        if self.chk_tray.isChecked() and self.tray.isVisible():
            ev.ignore()
            self.hide()
            if self.chk_notif.isChecked():
                self.tray.showMessage(APP_NAME, "Still running in the tray", QSystemTrayIcon.Information, 1500)
            return
        if not self._confirm_discard():
            ev.ignore()
            return
        ev.accept()
        QApplication.instance().quit()

    def _on_quit(self):
        self.clicker.stop()
        self.afk.stop()
        if self.runner is not None:
            self.runner.stop()
        for h in self._hotkey_handles:
            self.backend.remove_hotkey(h)
        self._save_settings()


def main():
    enable_dpi_awareness()
    install_bundled_files()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
