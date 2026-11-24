"""Dialogs: step editor, key capture and the screen-capture helper."""
from __future__ import annotations

import copy
import os
import re
from typing import Any, Callable

from PySide6.QtCore import QObject, QRect, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

from .picker import ScreenPicker
from .sequence import COMMON_FIELDS, STEP_TYPES
from .vision import save_image

# ---------------------------------------------------------------------------
# Key capture
# ---------------------------------------------------------------------------
_QT_TO_KB = {
    "return": "enter", "escape": "esc", "pgup": "page up", "pgdown": "page down",
    "del": "delete", "ins": "insert", "backspace": "backspace", "meta": "windows",
}


def qt_key_to_name(key: int, mods) -> str:
    """Qt key event -> name understood by the ``keyboard`` package."""
    names = {Qt.Key_Control: "ctrl", Qt.Key_Shift: "shift", Qt.Key_Alt: "alt", Qt.Key_Meta: "windows"}
    if key in names:
        return names[key]
    parts = []
    if mods & Qt.ControlModifier:
        parts.append("ctrl")
    if mods & Qt.AltModifier:
        parts.append("alt")
    if mods & Qt.ShiftModifier:
        parts.append("shift")
    base = QKeySequence(key).toString().lower()
    base = _QT_TO_KB.get(base, base)
    parts.append(base)
    return "+".join(parts)


class KeyCaptureDialog(QDialog):
    def __init__(self, parent=None, title="Press a key", allow_clear=True):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.result_key: str | None = None
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Press the key or key combo now.\nEsc cancels."))
        if allow_clear:
            b = QPushButton("Clear (no key)")
            b.clicked.connect(self._clear)
            v.addWidget(b)
        self.setMinimumWidth(260)

    def _clear(self):
        self.result_key = ""
        self.accept()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.reject()
            return
        if e.isAutoRepeat():
            return
        self.result_key = qt_key_to_name(e.key(), e.modifiers())
        self.accept()

    # Set by the main window: called before/after recording so the global
    # hotkeys don't fire while the user presses the key they want to record.
    pause_hotkeys: Callable[[], None] | None = None
    resume_hotkeys: Callable[[], None] | None = None

    @staticmethod
    def ask(parent, title="Press a key", allow_clear=True) -> str | None:
        d = KeyCaptureDialog(parent, title, allow_clear)
        if KeyCaptureDialog.pause_hotkeys:
            KeyCaptureDialog.pause_hotkeys()
        try:
            return d.result_key if d.exec() == QDialog.Accepted else None
        finally:
            if KeyCaptureDialog.resume_hotkeys:
                KeyCaptureDialog.resume_hotkeys()


# ---------------------------------------------------------------------------
# Screen capture helper
# ---------------------------------------------------------------------------
def match_screen(qt_screens, monitor, tolerance: int = 8):
    """Index of the Qt screen showing ``monitor`` (left, top, width, height in
    physical pixels, as mss reports it), or None.

    ``qt_screens`` holds (x, y, width, height, device_pixel_ratio) from
    ``QScreen.geometry()``. Qt 6 keeps each screen's top-left at its physical
    position but divides the size by that screen's scale, so a 150% monitor at
    x=1920 reports x=1920, not 1280. Older/other platforms scale the origin
    too. Both are tried, and the size has to agree as well, so a monitor
    whose position happens to line up with another's can't be mistaken for it.
    """
    left, top, width, height = monitor
    best, best_err = None, None
    for i, (x, y, w, h, dpr) in enumerate(qt_screens):
        size_err = abs(w * dpr - width) + abs(h * dpr - height)
        for ox, oy in ((x, y), (x * dpr, y * dpr)):
            err = abs(ox - left) + abs(oy - top) + size_err
            if best_err is None or err < best_err:
                best, best_err = i, err
    return best if best_err is not None and best_err <= tolerance else None


class CaptureHelper(QObject):
    """Hides the app, waits, screenshots the game, then shows a picker."""

    def __init__(self, get_screen: Callable, get_delay: Callable[[], float], parent=None):
        super().__init__(parent)
        self.get_screen = get_screen
        self.get_delay = get_delay
        self._picker = None

    def _qt_geometry_for(self, screen) -> QRect:
        """The Qt screen that shows the monitor being captured, so the picker
        overlay covers the right display."""
        try:
            left, top = screen.offset()
            width, height = screen.size()
            screens = QGuiApplication.screens()
            rects = [(qs.geometry().x(), qs.geometry().y(), qs.geometry().width(), qs.geometry().height(),
                      qs.devicePixelRatio()) for qs in screens]
            i = match_screen(rects, (left, top, width, height))
            if i is not None:
                return screens[i].geometry()
        except Exception:
            pass
        return QGuiApplication.primaryScreen().geometry()

    def pick(self, mode: str, hide: list[QWidget], done: Callable, hint: str = "") -> None:
        """mode 'point' -> done((x, y), img); 'region' -> done((x, y, w, h), img); None if cancelled."""
        visible = [w for w in hide if w is not None and w.isVisible()]
        for w in visible:
            w.hide()

        def restore():
            for w in visible:
                w.show()
                w.raise_()
                w.activateWindow()

        def go():
            screen = self.get_screen()
            try:
                img = screen.grab()
            except Exception as e:
                restore()
                QMessageBox.warning(None, "Screen capture", f"Could not capture the screen:\n{e}")
                done(None, None)
                return
            picker = ScreenPicker(img, mode, self._qt_geometry_for(screen), hint)

            def ok(x, y, w, h):
                restore()
                done((x, y) if mode == "point" else (x, y, w, h), img)

            def cancel():
                restore()
                done(None, img)

            picker.picked.connect(ok)
            picker.cancelled.connect(cancel)
            self._picker = picker
            picker.show()
            picker.raise_()
            picker.activateWindow()

        QTimer.singleShot(int(max(0.2, float(self.get_delay())) * 1000), go)

    def capture_template(self, templates_dir: str, hide: list[QWidget], done: Callable[[str | None], None],
                         suggested: str = "") -> None:
        """Drag a box on screen and save it as a template PNG. done(filename or None)."""

        def got(rect, img):
            if rect is None:
                done(None)
                return
            x, y, w, h = rect
            name, ok = QInputDialog.getText(None, "Save template", "Name for this image:", text=suggested or "button")
            if not ok or not name.strip():
                done(None)
                return
            fname = re.sub(r"[^\w\-]+", "_", name.strip()).strip("_") or "template"
            if not fname.lower().endswith(".png"):
                fname += ".png"
            os.makedirs(templates_dir, exist_ok=True)
            path = os.path.join(templates_dir, fname)
            if os.path.exists(path) and QMessageBox.question(
                    None, "Overwrite?", f"{fname} already exists. Replace it?") != QMessageBox.Yes:
                done(None)
                return
            save_image(path, img[y:y + h, x:x + w])
            done(fname)

        self.pick("region", hide, got, "Drag a tight box around the button/text to detect. Esc cancels.")


# ---------------------------------------------------------------------------
# Step editor
# ---------------------------------------------------------------------------
class StepDialog(QDialog):
    """Form generated from the step schema in ``sequence.STEP_TYPES``."""

    def __init__(self, step: dict[str, Any], *, templates_dir: str, capture: CaptureHelper,
                 ref_res: tuple[int, int], screen_size: Callable[[], tuple[int, int]],
                 test_template: Callable[[str, Any], str], parent=None):
        super().__init__(parent)
        self.step = copy.deepcopy(step)
        self.templates_dir = templates_dir
        self.capture = capture
        self.ref_res = ref_res
        self.screen_size = screen_size
        self.test_template = test_template
        spec = STEP_TYPES[step["type"]]
        self.setWindowTitle(f"Edit step: {spec['title']}")
        self.setMinimumWidth(480)
        self._getters: dict[str, Callable[[], Any]] = {}

        v = QVBoxLayout(self)
        form = QFormLayout()
        v.addLayout(form)
        for name, kind, default, help_ in spec["fields"] + COMMON_FIELDS:
            w, getter = self._make_field(name, kind, self.step.get(name, default))
            w.setToolTip(help_)
            label = QLabel(name.replace("_", " ").capitalize() + ":")
            label.setToolTip(help_)
            form.addRow(label, w)
            self._getters[name] = getter
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    # screen px <-> reference px
    def _to_ref(self, x, y):
        sw, sh = self.screen_size()
        return int(round(x * self.ref_res[0] / sw)), int(round(y * self.ref_res[1] / sh))

    def _make_field(self, name, kind, value):
        if kind == "bool":
            w = QCheckBox()
            w.setChecked(bool(value))
            return w, w.isChecked
        if kind == "int":
            w = QSpinBox()
            w.setRange(0, 1_000_000)
            w.setValue(int(value or 0))
            return w, w.value
        if kind == "float":
            w = QDoubleSpinBox()
            w.setRange(0, 86_400)
            w.setDecimals(2)
            w.setSingleStep(0.1 if name != "timeout" else 5)
            w.setValue(float(value or 0))
            if name == "timeout":
                w.setSpecialValueText("forever")
            return w, w.value
        if kind == "str":
            w = QLineEdit(str(value or ""))
            return w, w.text
        if kind.startswith("choice:"):
            w = QComboBox()
            w.addItems(kind.split(":", 1)[1].split("|"))
            w.setCurrentText(str(value))
            return w, w.currentText
        if kind == "button":
            w = QComboBox()
            w.addItems(["left", "right", "middle"])
            w.setCurrentText(str(value or "left"))
            return w, w.currentText
        if kind == "key":
            box = QWidget()
            h = QHBoxLayout(box)
            h.setContentsMargins(0, 0, 0, 0)
            e = QLineEdit(str(value or ""))
            e.setPlaceholderText("e.g. space, enter, ctrl+s")
            b = QPushButton("Record…")
            b.clicked.connect(lambda: self._record_key(e))
            h.addWidget(e, 1)
            h.addWidget(b)
            return box, lambda: e.text().strip()
        if kind == "template":
            return self._template_field(value)
        if kind == "point":
            return self._point_field(value, pickable=(name != "offset"))
        if kind == "region":
            return self._region_field(value)
        raise ValueError(kind)

    def _record_key(self, edit: QLineEdit):
        k = KeyCaptureDialog.ask(self)
        if k is not None:
            edit.setText(k)

    def _template_field(self, value):
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        combo = QComboBox()
        combo.setEditable(True)
        files = sorted(f for f in os.listdir(self.templates_dir) if f.lower().endswith(".png")) \
            if os.path.isdir(self.templates_dir) else []
        combo.addItems(files)
        combo.setCurrentText(str(value or ""))
        cap = QPushButton("Capture…")
        cap.setToolTip("Screenshot the game and drag a box around what to detect")
        test = QPushButton("Test")
        test.setToolTip("Check right now whether this image is on screen")

        def do_capture():
            def done(fname):
                if fname:
                    if combo.findText(fname) < 0:
                        combo.addItem(fname)
                    combo.setCurrentText(fname)
            self.capture.capture_template(self.templates_dir, [self.parent(), self], done,
                                          os.path.splitext(combo.currentText())[0])

        def do_test():
            region = self._getters["region"]() if "region" in self._getters else None
            QMessageBox.information(self, "Template test", self.test_template(combo.currentText(), region))

        cap.clicked.connect(do_capture)
        test.clicked.connect(do_test)
        h.addWidget(combo, 1)
        h.addWidget(cap)
        h.addWidget(test)
        return box, lambda: combo.currentText().strip()

    def _point_field(self, value, pickable=True):
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        xs, ys = QSpinBox(), QSpinBox()
        for s in (xs, ys):
            s.setRange(-10000, 10000)
        value = value or [0, 0]
        xs.setValue(int(value[0]))
        ys.setValue(int(value[1]))
        h.addWidget(QLabel("x"))
        h.addWidget(xs)
        h.addWidget(QLabel("y"))
        h.addWidget(ys)
        b = QPushButton("Pick on screen…")

        def pick():
            def done(pt, _img):
                if pt:
                    rx, ry = self._to_ref(*pt)
                    xs.setValue(rx)
                    ys.setValue(ry)
            self.capture.pick("point", [self.parent(), self], done)

        b.clicked.connect(pick)
        if pickable:
            h.addWidget(b)
        return box, lambda: [xs.value(), ys.value()]

    def _region_field(self, value):
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        on = QCheckBox("Limit to")
        spins = [QSpinBox() for _ in range(4)]
        for s in spins:
            s.setRange(0, 10000)
        if value:
            on.setChecked(True)
            for s, v in zip(spins, value):
                s.setValue(int(v))
        h.addWidget(on)
        for s, lab in zip(spins, "xywh"):
            s.setToolTip(lab)
            h.addWidget(s)
        b = QPushButton("Select…")

        def pick():
            def done(r, _img):
                if r:
                    x0, y0 = self._to_ref(r[0], r[1])
                    x1, y1 = self._to_ref(r[0] + r[2], r[1] + r[3])
                    for s, v in zip(spins, (x0, y0, x1 - x0, y1 - y0)):
                        s.setValue(v)
                    on.setChecked(True)
            self.capture.pick("region", [self.parent(), self], done, "Drag the area to search in. Esc cancels.")

        b.clicked.connect(pick)
        h.addWidget(b)
        return box, lambda: [s.value() for s in spins] if on.isChecked() else None

    def result_step(self) -> dict[str, Any]:
        out = {"type": self.step["type"]}
        for name, getter in self._getters.items():
            out[name] = getter()
        return out
