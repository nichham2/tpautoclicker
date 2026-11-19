"""Small line icons for the sidebar, painted with QPainter (no SVG plugin needed)."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF


def _canvas(size: int):
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    return pm, p


def _pen(color, w=1.8):
    return QPen(QColor(color), w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)


def _cursor(p: QPainter, n: float, color):
    path = QPainterPath()
    pts = [(0.30, 0.18), (0.30, 0.80), (0.45, 0.65), (0.56, 0.86), (0.66, 0.81), (0.55, 0.60), (0.75, 0.60)]
    path.moveTo(pts[0][0] * n, pts[0][1] * n)
    for x, y in pts[1:]:
        path.lineTo(x * n, y * n)
    path.closeSubpath()
    p.setPen(_pen(color))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)


def _auto(p: QPainter, n: float, color):
    # circular arrow around a play triangle
    p.setPen(_pen(color))
    r = QRectF(n * 0.16, n * 0.16, n * 0.68, n * 0.68)
    p.drawArc(r, 60 * 16, 300 * 16)
    a = math.radians(60)
    cx, cy, rad = n * 0.5, n * 0.5, n * 0.34
    tip = QPointF(cx + rad * math.cos(a), cy - rad * math.sin(a))
    p.drawPolyline(QPolygonF([tip + QPointF(-n * 0.13, -n * 0.02), tip, tip + QPointF(-n * 0.01, n * 0.13)]))
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    p.drawPolygon(QPolygonF([QPointF(n * 0.43, n * 0.37), QPointF(n * 0.43, n * 0.63), QPointF(n * 0.63, n * 0.5)]))


def _log(p: QPainter, n: float, color):
    p.setPen(_pen(color))
    for i, w in enumerate((0.56, 0.42, 0.56, 0.34)):
        y = n * (0.27 + i * 0.155)
        p.drawLine(QPointF(n * 0.22, y), QPointF(n * (0.22 + w), y))


def _gear(p: QPainter, n: float, color):
    p.setPen(_pen(color))
    cx = cy = n * 0.5
    path = QPainterPath()
    teeth = 8
    for i in range(teeth * 2):
        ang = math.pi * i / teeth
        rad = n * (0.34 if i % 2 == 0 else 0.26)
        for d in (-0.16, 0.16):
            x = cx + rad * math.cos(ang + d)
            y = cy + rad * math.sin(ang + d)
            if i == 0 and d < 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
    path.closeSubpath()
    p.drawPath(path)
    p.drawEllipse(QPointF(cx, cy), n * 0.10, n * 0.10)


def _mini(p: QPainter, n: float, color):
    p.setPen(_pen(color))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(n * 0.16, n * 0.24, n * 0.68, n * 0.52), n * 0.08, n * 0.08)
    p.setBrush(QColor(color))
    p.drawRoundedRect(QRectF(n * 0.48, n * 0.46, n * 0.26, n * 0.20), n * 0.04, n * 0.04)


_DRAW = {"clicker": _cursor, "automation": _auto, "log": _log, "settings": _gear, "mini": _mini}


def icon(name: str, color: str = "#ffffff", size: int = 24, dim: float = 0.62) -> QIcon:
    """Icon with a dimmed normal state and a full-colour checked/active state."""
    ic = QIcon()
    for state, alpha in ((QIcon.Off, dim), (QIcon.On, 1.0)):
        pm, p = _canvas(size)
        c = QColor(color)
        c.setAlphaF(alpha)
        _DRAW[name](p, size, c)
        p.end()
        ic.addPixmap(pm, QIcon.Normal, state)
        ic.addPixmap(pm, QIcon.Active, state)
    return ic


def logo(primary: str, size: int = 40) -> QPixmap:
    """App mark: a white rounded square with the accent-coloured cursor."""
    pm, p = _canvas(size)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#ffffff"))
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.3, size * 0.3)
    _cursor(p, size, primary)
    p.end()
    return pm
