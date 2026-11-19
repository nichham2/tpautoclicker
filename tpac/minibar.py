"""Small always-on-top control bar.

Floats over the game so the clicker and automation can be started, stopped and
watched without switching windows. It never takes keyboard focus, so clicking
it doesn't pull focus away from the game. Drag it anywhere by the grip on the
left; right-click for options.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QGuiApplication, QPainter, QPainterPath
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout, QWidget



class MiniBar(QWidget):
    toggle_clicker = Signal()
    toggle_sequence = Signal()
    stop_all = Signal()
    show_main = Signal()
    hidden_by_user = Signal()
    moved = Signal(int, int)
    opacity_changed = Signal(float)

    def __init__(self, opacity: float = 0.92) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus)
        self.setObjectName("mini")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._bg = QColor(32, 33, 36, 240)
        self._border = QColor(70, 74, 82)
        self.setWindowTitle("TP Auto Clicker controls")
        self._drag: QPoint | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 8, 12, 8)
        outer.setSpacing(3)
        row = QHBoxLayout()
        row.setSpacing(5)
        grip = QLabel("⠿")
        grip.setObjectName("grip")
        grip.setToolTip("Drag to move")
        grip.setCursor(Qt.SizeAllCursor)
        row.addWidget(grip)

        self.btn_click = QPushButton("▶ Click")
        self.btn_click.clicked.connect(self.toggle_clicker)
        self.btn_seq = QPushButton("▶ Auto")
        self.btn_seq.clicked.connect(self.toggle_sequence)
        self.btn_stop = QPushButton("■")
        self.btn_stop.setObjectName("stop")
        self.btn_stop.clicked.connect(self.stop_all)
        for b in (self.btn_click, self.btn_seq, self.btn_stop):
            b.setFocusPolicy(Qt.NoFocus)
            b.setCursor(Qt.PointingHandCursor)
            row.addWidget(b)

        b_open = QPushButton("⤢")
        b_open.setObjectName("icon")
        b_open.setToolTip("Open the main window")
        b_open.clicked.connect(self.show_main)
        b_close = QPushButton("✕")
        b_close.setObjectName("icon")
        b_close.setToolTip("Hide mini controls (turn back on in Settings or the tray menu)")
        b_close.clicked.connect(self._user_hide)
        for b in (b_open, b_close):
            b.setFocusPolicy(Qt.NoFocus)
            row.addWidget(b)
        outer.addLayout(row)

        self.status = QLabel("Idle")
        self.status.setObjectName("status")
        self.status.setMinimumWidth(220)
        outer.addWidget(self.status)

        self._click_running = False
        self._seq_running = False
        self._clicks = 0
        self._seq_text = ""
        self.setWindowOpacity(opacity)
        self.set_hotkeys("", "", "")

    # ---------------------------------------------------------------- theme
    def apply_scheme(self, sc) -> None:
        from .theme import minibar_stylesheet
        self.setStyleSheet(minibar_stylesheet(sc))
        self._bg = QColor(sc.surface_container_low)
        self._bg.setAlpha(245)
        self._border = QColor(sc.outline_variant)
        for b in (self.btn_click, self.btn_seq):
            b.style().unpolish(b)
            b.style().polish(b)
        self.update()

    # ---------------------------------------------------------------- state
    def set_hotkeys(self, click_hk: str, seq_hk: str, stop_hk: str) -> None:
        self.btn_click.setToolTip(f"Start/stop the clicker{f' ({click_hk.upper()})' if click_hk else ''}")
        self.btn_seq.setToolTip(f"Start/stop the automation{f' ({seq_hk.upper()})' if seq_hk else ''}")
        self.btn_stop.setToolTip(f"Stop everything{f' ({stop_hk.upper()})' if stop_hk else ''}")

    @staticmethod
    def _set_running(btn: QPushButton, running: bool, label: str) -> None:
        btn.setText(("■ " if running else "▶ ") + label)
        btn.setProperty("running", "true" if running else "false")
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def set_clicker_running(self, running: bool) -> None:
        self._click_running = running
        self._set_running(self.btn_click, running, "Click")
        self._refresh_status()

    def set_click_count(self, n: int) -> None:
        self._clicks = n
        if self._click_running:
            self._refresh_status()

    def set_sequence_running(self, running: bool) -> None:
        self._seq_running = running
        self._set_running(self.btn_seq, running, "Auto")
        self._refresh_status()

    def set_sequence_status(self, text: str) -> None:
        self._seq_text = text
        self._refresh_status()

    def _refresh_status(self) -> None:
        if self._click_running:
            text = f"Clicking · {self._clicks:,} clicks"
        elif self._seq_running or self._seq_text:
            text = self._seq_text or "Automation running"
        else:
            text = "Idle"
        fm = self.status.fontMetrics()
        self.status.setText(fm.elidedText(text, Qt.ElideRight, max(220, self.status.width())))
        self.status.setToolTip(text)

    # ------------------------------------------------------------ placement
    def place_default(self) -> None:
        """Top-right of the primary screen, clear of the top-left failsafe corner."""
        self.adjustSize()
        g = QGuiApplication.primaryScreen().availableGeometry()
        self.move(g.right() - self.width() - 24, g.top() + 24)

    def place_at(self, x: int, y: int) -> None:
        self.adjustSize()
        # Fall back to the default spot if the saved one is now off-screen.
        for s in QGuiApplication.screens():
            if s.availableGeometry().contains(QPoint(x + 20, y + 10)):
                self.move(x, y)
                return
        self.place_default()

    # ---------------------------------------------------------- interaction
    def _user_hide(self) -> None:
        self.hide()
        self.hidden_by_user.emit()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            self._drag = None
            self.moved.emit(self.x(), self.y())

    def contextMenuEvent(self, e):
        m = QMenu(self)
        m.addAction("Open main window", self.show_main.emit)
        sub = m.addMenu("Opacity")
        grp = QActionGroup(sub)
        for pct in (100, 90, 75, 60, 45):
            a = QAction(f"{pct}%", sub, checkable=True)
            a.setChecked(abs(self.windowOpacity() * 100 - pct) < 3)
            a.triggered.connect(lambda _=False, p=pct: self._set_opacity(p / 100))
            grp.addAction(a)
            sub.addAction(a)
        m.addAction("Move to top-right", lambda: (self.place_default(), self.moved.emit(self.x(), self.y())))
        m.addSeparator()
        m.addAction("Hide mini controls", self._user_hide)
        m.exec(e.globalPos())

    def _set_opacity(self, v: float) -> None:
        self.setWindowOpacity(v)
        self.opacity_changed.emit(v)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 20, 20)
        p.fillPath(path, self._bg)
        p.setPen(self._border)
        p.drawPath(path)
        p.end()
