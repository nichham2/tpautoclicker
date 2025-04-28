import sys, os, json, threading, time, random, requests
import keyboard, mouse, winsound
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QComboBox, QDoubleSpinBox, QTabWidget, QFormLayout,
    QHBoxLayout, QVBoxLayout, QSystemTrayIcon, QMenu, QMessageBox, QGroupBox, QCheckBox
)
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor

APP_NAME      = "OP Auto Clicker 3.5-Qt"
VERSION       = "3.5"
UPDATE_URL    = "https://raw.githubusercontent.com/nichham2/auto-clicker/main/version.txt"
SETTINGS_FILE = "settings_qt.json"

class AutoClicker(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(400, 350)

        # load or default settings
        self._load_settings()

        # state
        self.clicking = False
        self.afk      = False

        # build UI
        self._build_ui()

        # tray icon
        self._create_tray()

        # bind the toggle hotkey
        self._bind_hotkey(self.settings["hotkey"])

    def _build_ui(self):
        tabs = QTabWidget()
        tabs.addTab(self._controls_tab(), "Controls")
        tabs.addTab(self._settings_tab(), "Settings")
        self.setCentralWidget(tabs)

    def _controls_tab(self):
        w = QWidget(); v = QVBoxLayout()

        # Start / Stop
        h1 = QHBoxLayout()
        btn_start = QPushButton("Start Clicking"); btn_start.clicked.connect(self.start_clicking)
        btn_stop  = QPushButton("Stop Clicking");  btn_stop.clicked.connect(self.stop_clicking)
        h1.addWidget(btn_start); h1.addWidget(btn_stop)
        v.addLayout(h1)

        # AFK
        h2 = QHBoxLayout()
        btn_afk_on  = QPushButton("Start AFK"); btn_afk_on.clicked.connect(self.start_afk)
        btn_afk_off = QPushButton("Stop AFK");  btn_afk_off.clicked.connect(self.stop_afk)
        h2.addWidget(btn_afk_on); h2.addWidget(btn_afk_off)
        v.addLayout(h2)

        # Status
        self.status = QLabel("Status: Stopped"); self.status.setAlignment(Qt.AlignCenter)
        v.addWidget(self.status)

        w.setLayout(v)
        return w

    def _settings_tab(self):
        w = QWidget(); form = QFormLayout()

        # Hold Key dropdown
        keys = ["None"] + [chr(c) for c in range(65,91)] + ["Ctrl","Alt","Shift","Space","Enter","Esc"]
        self.hold_key = QComboBox(); self.hold_key.addItems(keys)
        self.hold_key.setCurrentText(self.settings.get("hold_key","None"))
        form.addRow("Hold Key:", self.hold_key)

        # Mouse Button
        self.mb = QComboBox(); self.mb.addItems(["Left","Right","Middle"])
        self.mb.setCurrentText(self.settings.get("mouse_button","Left"))
        form.addRow("Mouse Button:", self.mb)

        # Click Speed + Presets
        hspd = QHBoxLayout()
        self.spd = QDoubleSpinBox(); self.spd.setRange(0.01,5.0); self.spd.setSingleStep(0.01)
        self.spd.setValue(self.settings.get("speed",0.05))
        hspd.addWidget(self.spd)
        for name,val in [("Slow",0.2),("Med",0.1),("Fast",0.05)]:
            b = QPushButton(name)
            b.clicked.connect(lambda _,v=val: self.spd.setValue(v))
            hspd.addWidget(b)
        form.addRow("Click Speed (s):", hspd)

        # Toggle Hotkey
        hotkeys = [f"F{i}" for i in range(1,13)] + ["Space","Ctrl","Alt","Shift","Enter","Esc"]
        self.hk = QComboBox(); self.hk.addItems(hotkeys)
        self.hk.setCurrentText(self.settings.get("hotkey","F6"))
        self.hk.currentTextChanged.connect(self._change_hotkey)
        form.addRow("Toggle Hotkey:", self.hk)

        # Feature toggles
        feat = QGroupBox("Features")
        fl = QVBoxLayout()
        self.chk_tray = QCheckBox("Minimize to tray on close")
        self.chk_tray.setChecked(self.settings.get("minimize_to_tray", True))
        fl.addWidget(self.chk_tray)
        self.chk_notif = QCheckBox("Enable notifications")
        self.chk_notif.setChecked(self.settings.get("notifications", True))
        fl.addWidget(self.chk_notif)
        self.chk_sound = QCheckBox("Enable sounds")
        self.chk_sound.setChecked(self.settings.get("sounds", True))
        fl.addWidget(self.chk_sound)
        feat.setLayout(fl)
        form.addRow(feat)

        # Update & Save
        hbtn = QHBoxLayout()
        btn_upd = QPushButton("Check for Updates"); btn_upd.clicked.connect(self._check_update)
        btn_sav = QPushButton("Save Settings");      btn_sav.clicked.connect(self._save_settings)
        hbtn.addWidget(btn_upd); hbtn.addWidget(btn_sav)
        form.addRow(hbtn)

        w.setLayout(form)
        return w

    def _create_tray(self):
        ico = self._make_icon()
        self.tray = QSystemTrayIcon(ico, self)
        menu = QMenu()
        menu.addAction("Show", self.showNormal)
        menu.addAction("Exit", QApplication.instance().quit)
        self.tray.setContextMenu(menu)
        self.tray.show()

    def _make_icon(self):
        pix = QPixmap(64,64); pix.fill(QColor(30,30,30))
        p = QPainter(pix)
        p.setBrush(QColor(200,200,200)); p.drawRect(8,8,48,48); p.end()
        return QIcon(pix)

    def closeEvent(self, ev):
        if self.chk_tray.isChecked():
            ev.ignore()
            self.hide()
            if self.chk_notif.isChecked():
                self.tray.showMessage(APP_NAME, "Minimized to tray", QSystemTrayIcon.Information, 1500)
        else:
            ev.accept()

    # ─── Clicking & AFK ────────────────────────────────────────────────────────
    def start_clicking(self):
        if self.clicking: return
        self.clicking = True
        hold = self.hold_key.currentText()
        mb   = self.mb.currentText().lower()
        spd  = self.spd.value()

        def runner():
            while self.clicking:
                if hold!="None" and not keyboard.is_pressed(hold.lower()):
                    keyboard.press(hold.lower())
                mouse.click(mb)
                time.sleep(spd)
            if hold!="None" and keyboard.is_pressed(hold.lower()):
                keyboard.release(hold.lower())

        threading.Thread(target=runner, daemon=True).start()
        self.status.setText("Status: Clicking…")
        if self.chk_sound.isChecked():
            winsound.Beep(1000,150)
        if self.chk_notif.isChecked():
            self.tray.showMessage(APP_NAME, "Clicking started", QSystemTrayIcon.Information, 1000)

    def stop_clicking(self):
        self.clicking = False
        self.status.setText("Status: Stopped")
        if self.chk_sound.isChecked():
            winsound.Beep(500,150)
        if self.chk_notif.isChecked():
            self.tray.showMessage(APP_NAME, "Clicking stopped", QSystemTrayIcon.Information, 1000)

    def start_afk(self):
        if self.afk: return
        self.afk = True
        def mover():
            while self.afk:
                mouse.move(random.randint(-5,5), random.randint(-5,5),
                           absolute=False, duration=0.2)
                time.sleep(30)
        threading.Thread(target=mover, daemon=True).start()
        self.status.setText("Status: AFK Mode")

    def stop_afk(self):
        self.afk = False
        self.status.setText("Status: AFK Stopped")

    # ─── Hotkey Binding ────────────────────────────────────────────────────────
    def _bind_hotkey(self, key):
        try:
            if hasattr(self, "_hk_handle"):
                keyboard.remove_hotkey(self._hk_handle)
            self._hk_handle = keyboard.add_hotkey(key.lower(), self._toggle)
        except Exception as e:
            QMessageBox.warning(self, "Hotkey Error", str(e))

    def _change_hotkey(self, new):
        self.settings["hotkey"] = new
        self._bind_hotkey(new)

    def _toggle(self):
        if self.clicking: self.stop_clicking()
        else:             self.start_clicking()

    # ─── Update & Persistence ─────────────────────────────────────────────────
    def _check_update(self):
        try:
            r = requests.get(UPDATE_URL, timeout=5)
            ver = r.text.strip()
            if ver != VERSION:
                QMessageBox.information(self, "Update", f"New version {ver} available")
            else:
                QMessageBox.information(self, "Update", "You're up to date")
        except:
            QMessageBox.warning(self, "Update", "Failed to check updates")

    def _save_settings(self):
        self.settings.update({
            "hold_key":         self.hold_key.currentText(),
            "mouse_button":     self.mb.currentText(),
            "speed":            self.spd.value(),
            "hotkey":           self.hk.currentText(),
            "minimize_to_tray": self.chk_tray.isChecked(),
            "notifications":    self.chk_notif.isChecked(),
            "sounds":           self.chk_sound.isChecked()
        })
        with open(SETTINGS_FILE, "w") as f:
            json.dump(self.settings, f, indent=2)
        QMessageBox.information(self, "Settings", "Saved successfully!")

    def _load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE) as f:
                self.settings = json.load(f)
        else:
            self.settings = {
                "hold_key":"None", "mouse_button":"Left",
                "speed":0.05,     "hotkey":"F6",
                "minimize_to_tray": True,
                "notifications":    True,
                "sounds":           True
            }

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AutoClicker()
    window.show()
    sys.exit(app.exec())
