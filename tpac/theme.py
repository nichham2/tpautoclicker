"""Dashboard look for the app: deep navy panels, soft rounded cards, a vivid
accent sidebar and bright status colours (green / yellow / red / teal).

The accent comes from one seed colour (Settings > Appearance). The neutrals are
fixed blue-greys so the dark mode keeps its navy feel whatever the accent is;
a light variant uses the same structure on pale grey. The colour roles drive
both a QPalette (for native dialogs) and the stylesheet.
"""
from __future__ import annotations

import colorsys
import os
import tempfile
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPalette, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QApplication

SEEDS = {
    "Violet": "#6C5DD3",
    "Purple": "#6750A4",
    "Blue": "#0B57D0",
    "Teal": "#006A6A",
    "Green": "#386A20",
    "Orange": "#8B5000",
    "Red": "#B3261E",
    "Pink": "#984061",
}


def _lstar(r: float, g: float, b: float) -> float:
    """CIE L* (0-100) of an sRGB colour: the 'tone' in Material's HCT."""
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    y = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    return 116 * (y ** (1 / 3) if y > 216 / 24389 else (24389 / 27 * y + 16) / 116) - 16


def _tone(hue: float, chroma: float, tone: float) -> str:
    """Approximate an HCT colour: keep the hue, find the HLS lightness whose
    perceptual lightness (L*) equals ``tone``.

    Saturation is eased off near black and white, the way HCT chroma collapses
    there, so very light/dark tones don't look neon.
    """
    tone = max(0.0, min(100.0, tone))
    lo, hi = 0.0, 1.0
    for _ in range(30):
        mid = (lo + hi) / 2
        edge = 1.0 - abs(2 * mid - 1) ** 3
        sat = max(0.0, min(1.0, chroma * (0.6 + 0.4 * edge)))
        if _lstar(*colorsys.hls_to_rgb(hue, mid, sat)) < tone:
            lo = mid
        else:
            hi = mid
    r, g, b = colorsys.hls_to_rgb(hue, (lo + hi) / 2, sat)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


# Status colours from the dashboard design
GREEN = "#3DD598"
YELLOW = "#FFC542"
RED = "#FF6B6B"
TEAL = "#4FD1C5"


@dataclass
class Scheme:
    dark: bool
    primary: str
    on_primary: str
    primary_container: str
    on_primary_container: str
    secondary: str
    on_secondary: str
    secondary_container: str
    on_secondary_container: str
    tertiary_container: str
    on_tertiary_container: str
    error: str
    on_error: str
    error_container: str
    on_error_container: str
    surface: str
    surface_dim: str
    surface_container_lowest: str
    surface_container_low: str
    surface_container: str
    surface_container_high: str
    surface_container_highest: str
    on_surface: str
    on_surface_variant: str
    outline: str
    outline_variant: str
    inverse_surface: str
    inverse_on_surface: str
    success_container: str
    on_success_container: str


def _accent(seed: str, tone: float) -> str:
    c = QColor(seed)
    h, _l, sat = colorsys.rgb_to_hls(c.redF(), c.greenF(), c.blueF())
    return _tone(h, max(0.45, min(sat, 0.75)), tone)


def make_scheme(seed: str, dark: bool) -> Scheme:
    # Vivid accent with white text in both modes, like the design's sidebar
    primary = _accent(seed, 48)
    if dark:
        return Scheme(
            True, primary, "#ffffff", _accent(seed, 30), _accent(seed, 92),
            "#c9c9dd", "#1f2029", "#3a3b4f", "#e8e8f2", _accent(seed, 30), _accent(seed, 92),
            RED, "#ffffff", "#e5566a", "#ffffff",
            surface="#1f2029", surface_dim="#1a1b23", surface_container_lowest="#1a1b23",
            surface_container_low="#2b2c3a", surface_container="#33344a",
            surface_container_high="#3a3b4f", surface_container_highest="#44455a",
            on_surface="#ffffff", on_surface_variant="#8d8ea3", outline="#55566c", outline_variant="#3a3b4e",
            inverse_surface="#e8e8f2", inverse_on_surface="#1f2029",
            success_container=GREEN, on_success_container="#0f2a20",
        )
    return Scheme(
        False, primary, "#ffffff", _accent(seed, 92), _accent(seed, 20),
        "#5d5e74", "#ffffff", "#ebeaf7", "#2e2a5c", _accent(seed, 92), _accent(seed, 20),
        "#e5484d", "#ffffff", "#e5566a", "#ffffff",
        surface="#f3f4f9", surface_dim="#e7e8f0", surface_container_lowest="#ffffff",
        surface_container_low="#ffffff", surface_container="#f1f2f7",
        surface_container_high="#e9eaf2", surface_container_highest="#dfe0ea",
        on_surface="#1f2029", on_surface_variant="#6e6f85", outline="#c9cad8", outline_variant="#e3e4ee",
        inverse_surface="#2b2c3a", inverse_on_surface="#ffffff",
        success_container=GREEN, on_success_container="#0f2a20",
    )


def system_is_dark() -> bool:
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        pal = QGuiApplication.palette().color(QPalette.Window)
        return pal.lightnessF() < 0.5


# ---------------------------------------------------------------- indicators
def _icon_dir() -> str:
    d = os.path.join(tempfile.gettempdir(), "tpautoclicker-theme")
    os.makedirs(d, exist_ok=True)
    return d


def _draw_icons(sc: Scheme) -> dict[str, str]:
    """Checkbox tick, radio dot and arrows as PNGs (no SVG plugin needed)."""
    out = {}
    tag = ("d" if sc.dark else "l") + sc.primary.lstrip("#")

    def save(name, size, paint):
        path = os.path.join(_icon_dir(), f"{name}-{tag}.png")
        pm = QPixmap(size * 2, size * 2)
        pm.setDevicePixelRatio(2)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        paint(p, size)
        p.end()
        pm.save(path, "PNG")
        out[name] = path.replace("\\", "/")

    def tick(p, n):
        p.setPen(QPen(QColor(sc.on_primary), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline(QPolygonF([QPointF(n * 0.22, n * 0.52), QPointF(n * 0.42, n * 0.72),
                                  QPointF(n * 0.78, n * 0.30)]))

    def dot(p, n):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(sc.primary))
        p.drawEllipse(QRectF(n * 0.28, n * 0.28, n * 0.44, n * 0.44))

    def arrow(color, up):
        def f(p, n):
            p.setPen(QPen(QColor(color), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            y0, y1 = (n * 0.62, n * 0.38) if up else (n * 0.38, n * 0.62)
            p.drawPolyline(QPolygonF([QPointF(n * 0.28, y0), QPointF(n * 0.5, y1), QPointF(n * 0.72, y0)]))
        return f

    save("check", 18, tick)
    save("radio", 18, dot)
    save("down", 14, arrow(sc.on_surface_variant, False))
    save("up", 14, arrow(sc.on_surface_variant, True))
    return out


# ---------------------------------------------------------------- stylesheet
def stylesheet(sc: Scheme) -> str:
    ic = _draw_icons(sc)
    field = sc.surface_container if sc.dark else sc.surface
    return f"""
* {{ font-family: "Poppins", "Segoe UI Variable Text", "Segoe UI", "Roboto", "Noto Sans", sans-serif; font-size: 10pt; }}
QMainWindow, QDialog, QWidget#page, QScrollArea, QStackedWidget {{ background: {sc.surface}; }}
QWidget {{ color: {sc.on_surface}; }}
QLabel {{ background: transparent; }}
QLabel[role="hint"] {{ color: {sc.on_surface_variant}; }}
QLabel[role="big"] {{ font-size: 13pt; font-weight: 700; }}
QLabel[role="title"] {{ font-size: 18pt; font-weight: 700; padding: 4px 0 2px 0; }}

/* ---- sidebar ---- */
QFrame#sidebar {{ background: {sc.primary}; border: none; }}
QToolButton#nav {{
    background: transparent; border: none; border-radius: 12px; padding: 0;
    min-width: 44px; max-width: 44px; min-height: 44px; max-height: 44px;
}}
QToolButton#nav:hover {{ background: rgba(255, 255, 255, 0.10); }}
QToolButton#nav:checked {{ background: rgba(255, 255, 255, 0.22); }}
QLabel#logo {{ background: transparent; }}

/* ---- stat cards ---- */
QFrame#stat {{ background: {sc.surface_container_low}; border-radius: 16px; }}
QLabel[role="stat"] {{ font-size: 22pt; font-weight: 700; }}
QLabel[role="statlabel"] {{ color: {sc.on_surface_variant}; font-size: 9pt; font-weight: 600; }}
QLabel[role="good"] {{ color: {GREEN if sc.dark else "#139a63"}; font-weight: 600; }}

/* ---- buttons: tonal by default, filled for main actions ---- */
QPushButton {{
    background: {sc.secondary_container}; color: {sc.on_secondary_container};
    border: none; border-radius: 10px; padding: 8px 18px; min-height: 20px; font-weight: 600;
}}
QPushButton:hover {{ background: {_mix(sc.secondary_container, sc.on_secondary_container, 0.08)}; }}
QPushButton:pressed {{ background: {_mix(sc.secondary_container, sc.on_secondary_container, 0.14)}; }}
QPushButton:disabled {{ background: {_mix(sc.surface, sc.on_surface, 0.08)}; color: {_mix(sc.surface, sc.on_surface, 0.38)}; }}
QPushButton[variant="filled"] {{ background: {sc.primary}; color: {sc.on_primary}; border-radius: 12px; padding: 10px 24px; min-height: 24px; font-size: 11pt; }}
QPushButton[variant="filled"]:hover {{ background: {_mix(sc.primary, "#ffffff", 0.10)}; }}
QPushButton[variant="filled"]:pressed {{ background: {_mix(sc.primary, "#000000", 0.12)}; }}
QPushButton[variant="running"] {{ background: {sc.error_container}; color: {sc.on_error_container}; border-radius: 12px; padding: 10px 24px; min-height: 24px; font-size: 11pt; }}
QPushButton[variant="running"]:hover {{ background: {_mix(sc.error_container, "#ffffff", 0.10)}; }}
QPushButton[variant="small"] {{ padding: 6px 12px; border-radius: 8px; min-height: 18px; }}
QPushButton[variant="text"] {{ background: transparent; color: {sc.primary}; padding: 8px 12px; }}
QPushButton[variant="text"]:hover {{ background: {_mix(sc.surface, sc.primary, 0.08)}; }}
QPushButton#menu {{ padding-right: 34px; }}
QPushButton::menu-indicator {{ image: url({ic['down']}); subcontrol-position: right center; right: 10px; }}

/* ---- cards: section name above, rounded card below ---- */
QGroupBox {{
    background: {sc.surface_container_low}; border: none; border-radius: 16px;
    margin-top: 30px; padding: 16px 14px 12px 14px;
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left; left: 2px; top: 4px;
    color: {sc.on_surface_variant}; font-weight: 700; padding: 0 2px;
}}

/* ---- filled text fields ---- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {{
    background: {field}; border: 1px solid transparent; border-radius: 8px; padding: 6px 10px;
    selection-background-color: {sc.primary}; selection-color: {sc.on_primary};
}}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{ border-color: {sc.outline}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{
    border: 1px solid {sc.primary};
}}
QLineEdit:read-only {{ background: {field}; color: {sc.on_surface_variant}; }}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{ color: {_mix(sc.surface, sc.on_surface, 0.38)}; background: {_mix(field, sc.surface, 0.5)}; }}
QComboBox {{ padding-right: 28px; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: url({ic['down']}); width: 14px; height: 14px; }}
QComboBox QAbstractItemView {{
    background: {sc.surface_container_high}; border: none; border-radius: 8px; padding: 4px;
    selection-background-color: {sc.primary}; selection-color: {sc.on_primary}; outline: 0;
}}
QSpinBox, QDoubleSpinBox {{ padding-right: 22px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-position: top right; width: 20px; border: none; background: transparent; margin: 2px 2px 0 0; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-position: bottom right; width: 20px; border: none; background: transparent; margin: 0 2px 2px 0; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({ic['up']}); width: 12px; height: 12px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({ic['down']}); width: 12px; height: 12px; }}

/* ---- checkboxes / radios ---- */
QCheckBox, QRadioButton {{ spacing: 10px; background: transparent; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 2px solid {sc.on_surface_variant}; background: transparent; }}
QCheckBox::indicator:hover {{ border-color: {sc.on_surface}; }}
QCheckBox::indicator:checked {{ background: {sc.primary}; border-color: {sc.primary}; image: url({ic['check']}); }}
QRadioButton::indicator {{ width: 18px; height: 18px; border-radius: 11px; border: 2px solid {sc.on_surface_variant}; background: transparent; }}
QRadioButton::indicator:checked {{ border-color: {sc.primary}; image: url({ic['radio']}); }}

/* ---- pages (the tab bar is replaced by the sidebar) ---- */
QTabWidget::pane {{ border: none; background: {sc.surface}; }}

/* ---- table / list ---- */
QTableWidget, QTableView {{
    background: {sc.surface_container_low}; alternate-background-color: {sc.surface_container};
    border: none; border-radius: 16px; gridline-color: transparent;
    selection-background-color: {_mix(sc.surface_container_low, sc.primary, 0.35)}; selection-color: {sc.on_surface};
    outline: 0;
}}
QTableView::item {{ padding: 6px 8px; border: none; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{
    background: {sc.surface_container_low}; color: {sc.on_surface_variant}; border: none;
    padding: 10px 8px; font-weight: 600; font-size: 9pt;
}}
QTableCornerButton::section {{ background: {sc.surface_container_low}; border: none; }}
QPlainTextEdit {{ background: {sc.surface_container_low}; border-radius: 16px; padding: 10px; }}

/* ---- menus, tooltips, status bar, scrollbars ---- */
QMenu {{ background: {sc.surface_container_high}; border: none; border-radius: 10px; padding: 6px 0; }}
QMenu::item {{ padding: 8px 24px 8px 16px; background: transparent; }}
QMenu::item:selected {{ background: {_mix(sc.surface_container_high, sc.on_surface, 0.08)}; }}
QMenu::separator {{ height: 1px; background: {sc.outline_variant}; margin: 4px 0; }}
QMenu::indicator:checked {{ image: url({ic['radio']}); width: 18px; height: 18px; left: 4px; }}
QToolTip {{ background: {sc.inverse_surface}; color: {sc.inverse_on_surface}; border: none; border-radius: 6px; padding: 4px 8px; }}
QStatusBar {{ background: {sc.surface}; color: {sc.on_surface_variant}; padding-left: 16px; }}
QStatusBar::item {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px 4px; }}
QScrollBar::handle {{ background: {sc.outline_variant}; border-radius: 3px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background: {sc.outline}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; border: none; width: 0; height: 0; }}
QMessageBox QPushButton {{ min-width: 72px; }}
"""


def minibar_stylesheet(sc: Scheme) -> str:
    return f"""
QWidget#mini {{ color: {sc.on_surface}; }}
QLabel {{ background: transparent; }}
QLabel#grip {{ color: {sc.on_surface_variant}; font-size: 15pt; padding: 0 2px; }}
QLabel#status {{ color: {sc.on_surface_variant}; font-size: 9pt; padding-left: 4px; }}
QPushButton {{
    background: {sc.secondary_container}; color: {sc.on_secondary_container};
    border: none; border-radius: 10px; padding: 6px 14px; font-weight: 600;
}}
QPushButton:hover {{ background: {_mix(sc.secondary_container, sc.on_secondary_container, 0.08)}; }}
QPushButton[running="true"] {{ background: {sc.primary}; color: {sc.on_primary}; }}
QPushButton[running="true"]:hover {{ background: {_mix(sc.primary, sc.on_primary, 0.10)}; }}
QPushButton#stop {{ background: {sc.error_container}; color: {sc.on_error_container}; padding: 6px 11px; }}
QPushButton#stop:hover {{ background: {_mix(sc.error_container, sc.on_error_container, 0.10)}; }}
QPushButton#icon {{ background: transparent; color: {sc.on_surface_variant}; padding: 4px 6px; border-radius: 8px; }}
QPushButton#icon:hover {{ background: {_mix(sc.surface_container_high, sc.on_surface, 0.08)}; color: {sc.on_surface}; }}
QMenu {{ background: {sc.surface_container}; color: {sc.on_surface}; border: none; border-radius: 8px; padding: 6px 0; }}
QMenu::item {{ padding: 8px 24px 8px 16px; }}
QMenu::item:selected {{ background: {_mix(sc.surface_container, sc.on_surface, 0.08)}; }}
QToolTip {{ background: {sc.inverse_surface}; color: {sc.inverse_on_surface}; border: none; border-radius: 4px; padding: 4px 8px; }}
"""


def _mix(base: str, over: str, a: float) -> str:
    """M3 state layer: ``over`` at opacity ``a`` on top of ``base``."""
    b, o = QColor(base), QColor(over)
    return QColor(round(b.red() + (o.red() - b.red()) * a), round(b.green() + (o.green() - b.green()) * a),
                  round(b.blue() + (o.blue() - b.blue()) * a)).name()


def palette(sc: Scheme) -> QPalette:
    p = QPalette()
    roles = {
        QPalette.Window: sc.surface, QPalette.WindowText: sc.on_surface,
        QPalette.Base: sc.surface_container_lowest if not sc.dark else sc.surface_container_low,
        QPalette.AlternateBase: sc.surface_container, QPalette.Text: sc.on_surface,
        QPalette.Button: sc.secondary_container, QPalette.ButtonText: sc.on_secondary_container,
        QPalette.Highlight: sc.primary, QPalette.HighlightedText: sc.on_primary,
        QPalette.ToolTipBase: sc.inverse_surface, QPalette.ToolTipText: sc.inverse_on_surface,
        QPalette.PlaceholderText: sc.on_surface_variant, QPalette.Link: sc.primary,
        QPalette.Mid: sc.outline_variant, QPalette.Dark: sc.outline, QPalette.Light: sc.surface_container_high,
    }
    for role, col in roles.items():
        p.setColor(role, QColor(col))
    dis = QColor(_mix(sc.surface, sc.on_surface, 0.38))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, dis)
    return p


def apply(app: QApplication, mode: str = "System", seed: str = SEEDS["Purple"]) -> Scheme:
    """mode: System / Light / Dark. Returns the scheme that was applied."""
    dark = system_is_dark() if mode == "System" else mode == "Dark"
    sc = make_scheme(seed, dark)
    app.setStyle("Fusion")
    app.setPalette(palette(sc))
    app.setStyleSheet(stylesheet(sc))
    return sc
