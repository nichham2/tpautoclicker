import sys, os
import json
import threading
import time
import random
import requests

import keyboard
import mouse
import winsound

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QKeySequence, QPalette
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QLineEdit, QComboBox, QDoubleSpinBox, QTabWidget, QFormLayout,
    QHBoxLayout, QVBoxLayout, QSystemTrayIcon, QMenu,
    QMessageBox, QGroupBox, QCheckBox
)

APP_NAME      = "TP Auto Clicker"
VERSION       = "3.6"
UPDATE_URL    = "https://raw.githubusercontent.com/nichham2/auto-clicker/main/version.txt"
SETTINGS_FILE = "settings.json"

class AutoClicker(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(420, 360)

        # load or default settings
        self._load_settings()

        # apply theme before building UI
        self._apply_theme()

        # state flags
        self.clicking = False
        self.afk      = False
        self._capturing = None  # "hold" or "hotkey" when capturing

        # build UI
        self._build_ui()

        # tray icon
        self._create_tray()

        # bind the toggle hotkey from settings
        self._bind_hotkey(self.settings["hotkey"])

        # ensure settings are saved on exit
        QApplication.instance().aboutToQuit.connect(self._save_settings)

    # ─── UI BUILD
    def _build_ui(self):
        tabs = QTabWidget()
        tabs.addTab(self._controls_tab(), "Controls")
        tabs.addTab(self._settings_tab(), "Settings")
        self.setCentralWidget(tabs)

    def _controls_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)

        # Start / Stop
        h1 = QHBoxLayout()
        b1 = QPushButton("Start Clicking"); b1.clicked.connect(self.start_clicking)
        b2 = QPushButton("Stop Clicking");  b2.clicked.connect(self.stop_clicking)
        h1.addWidget(b1); h1.addWidget(b2)
        v.addLayout(h1)

        # AFK
        h2 = QHBoxLayout()
        a1 = QPushButton("Start AFK"); a1.clicked.connect(self.start_afk)
        a2 = QPushButton("Stop AFK");  a2.clicked.connect(self.stop_afk)
        h2.addWidget(a1); h2.addWidget(a2)
        v.addLayout(h2)

        # Status
        self.status = QLabel("Status: Stopped")
        self.status.setAlignment(Qt.AlignCenter)
        v.addWidget(self.status)

        return w

    def _settings_tab(self):
        w = QWidget()
        form = QFormLayout(w)

        # Hold Key capture
        self.hold_key_edit = QLineEdit(self.settings.get("hold_key",""))
        self.hold_key_edit.setReadOnly(True)
        btn_hold = QPushButton("Set Hold Key")
        btn_hold.clicked.connect(lambda: self._start_capture("hold"))
        frm = QHBoxLayout()
        frm.addWidget(self.hold_key_edit); frm.addWidget(btn_hold)
        form.addRow("Hold Key:", frm)

        # Mouse Button
        self.mb = QComboBox()
        self.mb.addItems(["Left","Right","Middle"])
        self.mb.setCurrentText(self.settings.get("mouse_button","Left"))
        form.addRow("Mouse Button:", self.mb)

        # Click Speed + presets + inc/dec
        hspd = QHBoxLayout()
        self.spd = QDoubleSpinBox()
        self.spd.setRange(0.01,5.0); self.spd.setSingleStep(0.01)
        self.spd.setValue(self.settings.get("speed",0.05))
        btn_dec = QPushButton("-")
        btn_dec.clicked.connect(lambda: self.spd.setValue(max(self.spd.minimum(), self.spd.value() - self.spd.singleStep())))
        btn_inc = QPushButton("+")
        btn_inc.clicked.connect(lambda: self.spd.setValue(min(self.spd.maximum(), self.spd.value() + self.spd.singleStep())))
        hspd.addWidget(btn_dec); hspd.addWidget(self.spd); hspd.addWidget(btn_inc)
        for name,val in [("Slow",0.2),("Med",0.1),("Fast",0.05)]:
            btn = QPushButton(name)
            btn.clicked.connect(lambda _,v=val: self.spd.setValue(v))
            hspd.addWidget(btn)
        form.addRow("Click Speed (s):", hspd)

        # Toggle Hotkey capture
        self.hk_edit = QLineEdit(self.settings.get("hotkey","F6"))
        self.hk_edit.setReadOnly(True)
        btn_hot = QPushButton("Set Hotkey")
        btn_hot.clicked.connect(lambda: self._start_capture("hotkey"))
        frm2 = QHBoxLayout()
        frm2.addWidget(self.hk_edit); frm2.addWidget(btn_hot)
        form.addRow("Toggle Hotkey:", frm2)

        # Feature toggles
        feat = QGroupBox("Features")
        fl = QVBoxLayout(feat)
        self.chk_tray  = QCheckBox("Minimize to tray on close")
        self.chk_tray.setChecked(self.settings.get("minimize_to_tray", True))
        self.chk_notif = QCheckBox("Enable notifications")
        self.chk_notif.setChecked(self.settings.get("notifications", True))
        self.chk_sound = QCheckBox("Enable sounds")
        self.chk_sound.setChecked(self.settings.get("sounds", True))
        fl.addWidget(self.chk_tray); fl.addWidget(self.chk_notif); fl.addWidget(self.chk_sound)
        form.addRow(feat)

        # Update, Save & Reset
        hbtn = QHBoxLayout()
        btn_upd = QPushButton("Check for Updates"); btn_upd.clicked.connect(self._check_update)
        btn_sav = QPushButton("Save Settings");      btn_sav.clicked.connect(self._save_settings)
        btn_res = QPushButton("Reset Defaults");    btn_res.clicked.connect(self._reset_defaults)
        hbtn.addWidget(btn_upd); hbtn.addWidget(btn_sav); hbtn.addWidget(btn_res)
        form.addRow(hbtn)

        return w

    # ─── THEME
    def _apply_theme(self):
        pal = QApplication.instance().palette()
        bg = pal.color(QPalette.Window)
        lum = 0.299*bg.redF() + 0.587*bg.greenF() + 0.114*bg.blueF()
        if lum < 0.5:
            qss = """
            QWidget { background: #2e2e2e; color: #ddd; }
            QGroupBox { border:1px solid #555; margin-top:10px; }
            QGroupBox::title { subcontrol-origin:margin; subcontrol-position:top center; padding:0 3px; }
            QPushButton { background:#3a3a3a; border:1px solid #555; padding:4px; }
            QPushButton:hover { background:#444; }
            QLineEdit, QDoubleSpinBox, QComboBox { background:#3a3a3a; border:1px solid #555; color:#fff; }
            QCheckBox { color:#ddd; }
            """
            QApplication.instance().setStyleSheet(qss)
        else:
            QApplication.instance().setStyleSheet("")

    # ─── TRAY
    def _make_icon(self):
        pix = QPixmap(64,64); pix.fill(QColor(30,30,30))
        p = QPainter(pix); p.setBrush(QColor(200,200,200)); p.drawRect(8,8,48,48); p.end()
        return QIcon(pix)

    def _create_tray(self):
        ico = self._make_icon()
        self.tray = QSystemTrayIcon(ico, self)
        menu = QMenu()
        menu.addAction("Show", self.showNormal)
        menu.addAction("Exit", QApplication.instance().quit)
        self.tray.setContextMenu(menu)
        self.tray.show()

    # ─── CLICK & AFK
    def start_clicking(self):
        if self.clicking: return
        self.clicking = True
        # minimize on start clicking
        self.showMinimized()
        hold = self.hold_key_edit.text()
        mb   = self.mb.currentText().lower()
        spd  = self.spd.value()
        def runner():
            while self.clicking:
                if hold and hold != "None" and not keyboard.is_pressed(hold.lower()):
                    keyboard.press(hold.lower())
                mouse.click(mb)
                time.sleep(spd)
            if hold and hold != "None" and keyboard.is_pressed(hold.lower()):
                keyboard.release(hold.lower())
        threading.Thread(target=runner, daemon=True).start()
        self.status.setText("Status: Clicking…")
        if self.chk_sound.isChecked(): winsound.Beep(1000,150)
        if self.chk_notif.isChecked():
            self.tray.showMessage(APP_NAME, "Clicking started", QSystemTrayIcon.Information, 1000)

    def stop_clicking(self):
        self.clicking = False
        self.status.setText("Status: Stopped")
        if self.chk_sound.isChecked(): winsound.Beep(500,150)
        if self.chk_notif.isChecked():
            self.tray.showMessage(APP_NAME, "Clicking stopped", QSystemTrayIcon.Information, 1000)

    def start_afk(self):
        if self.afk: return
        self.afk = True
        # minimize on start AFK
        self.showMinimized()
        def mover():
            while self.afk:
                mouse.move(random.randint(-5,5), random.randint(-5,5), absolute=False, duration=0.2)
                time.sleep(30)
        threading.Thread(target=mover, daemon=True).start()
        self.status.setText("Status: AFK Mode")

    def stop_afk(self):
        self.afk = False
        self.status.setText("Status: AFK Stopped")

    # ─── HOTKEY BIND
    def _bind_hotkey(self, keystr):
        try:
            if hasattr(self, "_hk_handle"):
                keyboard.remove_hotkey(self._hk_handle)
            self._hk_handle = keyboard.add_hotkey(keystr.lower(), self._toggle)
            self.hk_edit.setText(keystr)
        except Exception as e:
            QMessageBox.warning(self, "Hotkey Error", str(e))

    def _toggle(self):
        if self.clicking: self.stop_clicking()
        else:             self.start_clicking()

    # ─── KEY CAPTURE
    def _start_capture(self, which):
        self._capturing = which
        self.status.setText(f"Press a key to set {which}…")
        self.grabKeyboard()

    def keyPressEvent(self, event):
        if self._capturing:
            key = event.key()
            if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
                full = {Qt.Key_Control: 'Ctrl', Qt.Key_Shift:'Shift', Qt.Key_Alt:'Alt', Qt.Key_Meta:'Meta'}[key]
            else:
                mods=[]
                m = event.modifiers()
                if m & Qt.ControlModifier: mods.append('Ctrl')
                if m & Qt.AltModifier:     mods.append('Alt')
                if m & Qt.ShiftModifier:   mods.append('Shift')
                if m & Qt.MetaModifier:    mods.append('Meta')
                txt = event.text().upper() or QKeySequence(key).toString()
                full = '+'.join(mods+[txt]) if mods else txt
            if self._capturing == 'hold':
                self.hold_key_edit.setText(full)
                self.settings['hold_key'] = full
            else:
                self.settings['hotkey'] = full
                self._bind_hotkey(full)
            self._capturing=None
            self.releaseKeyboard()
            self.status.setText('Status: Stopped')
        else:
            super().keyPressEvent(event)

    # ─── UPDATE & PERSIST
    def _check_update(self):
        try:
            r = requests.get(UPDATE_URL, timeout=5)
            ver = r.text.strip()
            if ver != VERSION:
                QMessageBox.information(self, 'Update', f'New version {ver} available')
            else:
                QMessageBox.information(self, 'Update', "You're up to date")
        except:
            QMessageBox.warning(self, 'Update', 'Failed to check updates')

    def _reset_defaults(self):
        defaults = {
            'hold_key':'None','mouse_button':'Left','speed':0.05,
            'hotkey':'F6','minimize_to_tray':True,'notifications':True,'sounds':True
        }
        self.settings.update(defaults)
        self.hold_key_edit.setText(defaults['hold_key'])
        self.mb.setCurrentText(defaults['mouse_button'])
        self.spd.setValue(defaults['speed'])
        self.hk_edit.setText(defaults['hotkey'])
        self.chk_tray.setChecked(defaults['minimize_to_tray'])
        self.chk_notif.setChecked(defaults['notifications'])
        self.chk_sound.setChecked(defaults['sounds'])
        self._bind_hotkey(defaults['hotkey'])

    def _save_settings(self):
        self.settings.update({
            'hold_key':        self.hold_key_edit.text(),
            'mouse_button':    self.mb.currentText(),
            'speed':           self.spd.value(),
            'hotkey':          self.hk_edit.text(),
            'minimize_to_tray':self.chk_tray.isChecked(),
            'notifications':   self.chk_notif.isChecked(),
            'sounds':          self.chk_sound.isChecked()
        })
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(self.settings, f, indent=2)

    def _load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE) as f:
                self.settings = json.load(f)
        else:
            self.settings = {
                'hold_key':'None','mouse_button':'Left','speed':0.05,
                'hotkey':'F6','minimize_to_tray':True,'notifications':True,'sounds':True
            }

    def closeEvent(self, ev):
        if self.chk_tray.isChecked():
            ev.ignore(); self.hide()
            if self.chk_notif.isChecked():
                self.tray.showMessage(APP_NAME, 'Minimized to tray', QSystemTrayIcon.Information, 1500)
        else:
            self._save_settings(); ev.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = AutoClicker()
    window.show()
    sys.exit(app.exec())
