"""Compact pro-tool look for the app (dense dark panels, small square corners).

Colours come from one seed colour: tonal palettes for primary / secondary /
tertiary / neutral are generated from the seed's hue and mapped to colour
roles for light or dark mode, or the fixed navy "Dashboard" scheme is used.
The roles drive both a QPalette (for native dialogs) and a compact stylesheet:
4px corners, tight padding, flat inset fields, 9pt type.
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


def make_scheme(seed: str, dark: bool) -> Scheme:
    c = QColor(seed)
    h, l, s = colorsys.rgb_to_hls(c.redF(), c.greenF(), c.blueF())
    s = max(0.5, min(s, 0.8))  # M3 keeps primary chroma in a usable band
    P = lambda t: _tone(h, s, t)                     # primary
    S = lambda t: _tone(h, s * 0.30, t)              # secondary: same hue, muted
    T = lambda t: _tone((h + 1 / 6) % 1.0, s * 0.55, t)  # tertiary: hue + 60°
    N = lambda t: _tone(h, 0.06, t)                  # neutral
    NV = lambda t: _tone(h, 0.12, t)                 # neutral variant
    G = lambda t: _tone(0.36, 0.45, t)               # green, for "running"
    if not dark:
        return Scheme(
            False, P(40), P(100), P(90), P(10), S(40), S(100), S(90), S(10), T(90), T(10),
            "#b3261e", "#ffffff", "#f9dedc", "#410e0b",
            N(98), N(87), N(100), N(96), N(94), N(92), N(90), N(10), NV(30), NV(50), NV(80),
            N(20), N(95), G(88), G(12),
        )
    return Scheme(
        True, P(80), P(20), P(30), P(90), S(80), S(20), S(30), S(90), T(30), T(90),
        "#f2b8b5", "#601410", "#8c1d18", "#f9dedc",
        N(6), N(6), N(4), N(10), N(12), N(17), N(22), N(90), NV(80), NV(60), NV(30),
        N(90), N(20), G(28), G(88),
    )


def dashboard_scheme(seed: str) -> Scheme:
    """Flat navy dashboard look: fixed slate surfaces, vivid accent, coral/green status."""
    c = QColor(seed)
    h, _, s = colorsys.rgb_to_hls(c.redF(), c.greenF(), c.blueF())
    primary = _tone(h, max(0.55, min(s, 0.8)), 48)  # vivid enough to read on navy
    return Scheme(
        True, primary, "#ffffff", _mix("#2a2b3a", primary, 0.35), "#ffffff",
        "#a3a4bd", "#1e1f2b", "#353648", "#e8e8f2", "#4a3f22", "#f5c44e",
        "#f0675a", "#ffffff", "#f0675a", "#ffffff",
        "#1e1f2b", "#191a24", "#16171f", "#2a2b3a", "#313243", "#3a3b4d", "#43445a",
        "#ffffff", "#8f90a6", "#4a4b60", "#3a3b4d", "#e8e8f2", "#1e1f2b",
        "#1f4a3c", "#5fd3a5",
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
    return f"""
* {{ font-family: "Segoe UI Variable Text", "Segoe UI", "Roboto", "Noto Sans", sans-serif; font-size: 9pt; }}
QMainWindow, QDialog, QWidget#page, QScrollArea {{ background: {sc.surface}; }}
QWidget {{ color: {sc.on_surface}; }}
QLabel {{ background: transparent; }}
QLabel[role="hint"] {{ color: {sc.on_surface_variant}; }}
QLabel[role="big"] {{ font-size: 11pt; font-weight: 600; }}

/* ---- buttons: tonal by default, filled for main actions ---- */
QPushButton {{
    background: {sc.secondary_container}; color: {sc.on_secondary_container};
    border: none; border-radius: 4px; padding: 4px 10px; min-height: 16px; font-weight: 600;
}}
QPushButton:hover {{ background: {_mix(sc.secondary_container, sc.on_secondary_container, 0.08)}; }}
QPushButton:pressed {{ background: {_mix(sc.secondary_container, sc.on_secondary_container, 0.14)}; }}
QPushButton:disabled {{ background: {_mix(sc.surface, sc.on_surface, 0.10)}; color: {_mix(sc.surface, sc.on_surface, 0.38)}; }}
QPushButton[variant="filled"] {{ background: {sc.primary}; color: {sc.on_primary}; border-radius: 4px; padding: 6px 14px; min-height: 18px; font-size: 10pt; }}
QPushButton[variant="filled"]:hover {{ background: {_mix(sc.primary, sc.on_primary, 0.10)}; }}
QPushButton[variant="filled"]:pressed {{ background: {_mix(sc.primary, sc.on_primary, 0.18)}; }}
QPushButton[variant="running"] {{ background: {sc.error_container}; color: {sc.on_error_container}; border-radius: 4px; padding: 6px 14px; min-height: 18px; font-size: 10pt; }}
QPushButton[variant="running"]:hover {{ background: {_mix(sc.error_container, sc.on_error_container, 0.10)}; }}
QPushButton[variant="small"] {{ padding: 3px 8px; border-radius: 3px; min-height: 14px; }}
QPushButton[variant="text"] {{ background: transparent; color: {sc.primary}; padding: 4px 8px; }}
QPushButton[variant="text"]:hover {{ background: {_mix(sc.surface, sc.primary, 0.08)}; }}
QPushButton#menu {{ padding-right: 26px; }}
QPushButton::menu-indicator {{ image: url({ic['down']}); subcontrol-position: right center; right: 6px; width: 10px; height: 10px; }}

/* ---- sidebar navigation (replaces the tab bar) ---- */
QFrame#sidebar {{ background: {sc.primary}; }}
QLabel#brand {{ color: {sc.on_primary}; font-size: 11pt; font-weight: 700; padding: 2px 6px 10px 6px; }}
QPushButton[nav="true"] {{
    background: transparent; color: {_mix(sc.primary, sc.on_primary, 0.72)};
    border-radius: 4px; padding: 6px 10px; text-align: left; font-weight: 600;
}}
QPushButton[nav="true"]:hover {{ background: {_mix(sc.primary, sc.on_primary, 0.12)}; color: {sc.on_primary}; }}
QPushButton[nav="true"]:checked {{ background: {sc.surface}; color: {sc.on_surface}; }}

/* ---- cards ---- */
QGroupBox {{
    background: {sc.surface_container_low}; border: none; border-radius: 6px;
    margin-top: 20px; padding: 8px 8px 6px 8px;
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left; left: 2px; top: 2px;
    color: {sc.on_surface_variant}; font-weight: 600; padding: 0 4px;
}}

/* ---- flat inset fields ---- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {{
    background: {sc.surface_container_lowest if not sc.dark else sc.surface_dim};
    border: 1px solid {sc.outline_variant}; border-radius: 3px; padding: 3px 6px;
    selection-background-color: {sc.primary}; selection-color: {sc.on_primary};
}}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{ border-color: {sc.outline}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{
    border: 1px solid {sc.primary};
}}
QLineEdit:read-only {{ background: {sc.surface_container}; }}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{ color: {_mix(sc.surface, sc.on_surface, 0.38)}; border-color: {_mix(sc.surface, sc.on_surface, 0.12)}; }}
QComboBox {{ padding-right: 22px; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox::down-arrow {{ image: url({ic['down']}); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{
    background: {sc.surface_container}; border: 1px solid {sc.outline_variant}; border-radius: 4px; padding: 2px;
    selection-background-color: {sc.secondary_container}; selection-color: {sc.on_secondary_container}; outline: 0;
}}
QSpinBox, QDoubleSpinBox {{ padding-right: 18px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-position: top right; width: 16px; border: none; background: transparent; margin: 1px 1px 0 0; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-position: bottom right; width: 16px; border: none; background: transparent; margin: 0 1px 1px 0; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({ic['up']}); width: 10px; height: 10px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({ic['down']}); width: 10px; height: 10px; }}

/* ---- checkboxes / radios ---- */
QCheckBox, QRadioButton {{ spacing: 6px; background: transparent; }}
QCheckBox::indicator {{ width: 13px; height: 13px; border-radius: 3px; border: 1px solid {sc.on_surface_variant}; background: transparent; }}
QCheckBox::indicator:hover {{ border-color: {sc.on_surface}; }}
QCheckBox::indicator:checked {{ background: {sc.primary}; border-color: {sc.primary}; image: url({ic['check']}); }}
QRadioButton::indicator {{ width: 13px; height: 13px; border-radius: 7px; border: 1px solid {sc.on_surface_variant}; background: transparent; }}
QRadioButton::indicator:checked {{ border-color: {sc.primary}; image: url({ic['radio']}); }}

/* ---- tabs: text tabs with a primary indicator ---- */
QTabWidget::pane {{ border: none; background: {sc.surface}; top: -1px; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{
    background: transparent; color: {sc.on_surface_variant}; padding: 10px 20px; margin: 0 2px;
    border: none; border-bottom: 3px solid transparent; font-weight: 600;
}}
QTabBar::tab:hover {{ color: {sc.on_surface}; background: {_mix(sc.surface, sc.on_surface, 0.06)}; border-top-left-radius: 8px; border-top-right-radius: 8px; }}
QTabBar::tab:selected {{ color: {sc.primary}; border-bottom: 3px solid {sc.primary}; }}

/* ---- table / list ---- */
QTableWidget, QTableView {{
    background: {sc.surface_container_low}; alternate-background-color: {sc.surface_container};
    border: none; border-radius: 4px; gridline-color: transparent;
    selection-background-color: {sc.secondary_container}; selection-color: {sc.on_secondary_container};
    outline: 0;
}}
QTableView::item {{ padding: 2px 6px; border: none; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{
    background: {sc.surface_container_low}; color: {sc.on_surface_variant}; border: none;
    border-bottom: 1px solid {sc.outline_variant}; padding: 4px 6px; font-weight: 600;
}}
QTableCornerButton::section {{ background: {sc.surface_container_low}; border: none; }}

/* ---- menus, tooltips, status bar, scrollbars ---- */
QMenu {{ background: {sc.surface_container}; border: 1px solid {sc.outline_variant}; border-radius: 4px; padding: 3px 0; }}
QMenu::item {{ padding: 4px 18px 4px 12px; background: transparent; }}
QMenu::item:selected {{ background: {_mix(sc.surface_container, sc.on_surface, 0.08)}; }}
QMenu::separator {{ height: 1px; background: {sc.outline_variant}; margin: 4px 0; }}
QMenu::indicator:checked {{ image: url({ic['radio']}); width: 18px; height: 18px; left: 4px; }}
QToolTip {{ background: {sc.inverse_surface}; color: {sc.inverse_on_surface}; border: none; border-radius: 4px; padding: 4px 8px; }}
QStatusBar {{ background: {sc.surface_container}; color: {sc.on_surface_variant}; }}
QStatusBar::item {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 2px 4px; }}
QScrollBar::handle {{ background: {sc.outline_variant}; border-radius: 3px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background: {sc.outline}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; border: none; width: 0; height: 0; }}
QMessageBox QPushButton {{ min-width: 64px; }}
"""


def minibar_stylesheet(sc: Scheme) -> str:
    return f"""
QWidget#mini {{ color: {sc.on_surface}; }}
QLabel {{ background: transparent; }}
QLabel#grip {{ color: {sc.on_surface_variant}; font-size: 12pt; padding: 0 2px; }}
QLabel#status {{ color: {sc.on_surface_variant}; font-size: 8pt; padding-left: 4px; }}
QPushButton {{
    background: {sc.secondary_container}; color: {sc.on_secondary_container};
    border: none; border-radius: 4px; padding: 3px 10px; font-weight: 600; font-size: 9pt;
}}
QPushButton:hover {{ background: {_mix(sc.secondary_container, sc.on_secondary_container, 0.08)}; }}
QPushButton[running="true"] {{ background: {sc.primary}; color: {sc.on_primary}; }}
QPushButton[running="true"]:hover {{ background: {_mix(sc.primary, sc.on_primary, 0.10)}; }}
QPushButton#stop {{ background: {sc.error_container}; color: {sc.on_error_container}; padding: 3px 8px; }}
QPushButton#stop:hover {{ background: {_mix(sc.error_container, sc.on_error_container, 0.10)}; }}
QPushButton#icon {{ background: transparent; color: {sc.on_surface_variant}; padding: 2px 5px; border-radius: 4px; }}
QPushButton#icon:hover {{ background: {_mix(sc.surface_container_high, sc.on_surface, 0.08)}; color: {sc.on_surface}; }}
QMenu {{ background: {sc.surface_container}; color: {sc.on_surface}; border: 1px solid {sc.outline_variant}; border-radius: 4px; padding: 3px 0; }}
QMenu::item {{ padding: 4px 18px 4px 12px; }}
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
    """mode: Dashboard / System / Light / Dark. Returns the scheme that was applied."""
    if mode == "Dashboard":
        sc = dashboard_scheme(seed)
    else:
        sc = make_scheme(seed, system_is_dark() if mode == "System" else mode == "Dark")
    app.setStyle("Fusion")
    app.setPalette(palette(sc))
    app.setStyleSheet(stylesheet(sc))
    return sc
