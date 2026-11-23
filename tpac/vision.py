"""Screen capture and image matching.

Templates are small screenshots of a button or popup. ``Matcher.find`` looks
for one on the screen and returns where it is and how confident the match is.

Templates are captured at a *reference resolution* (the one in the sequence
file). On a screen with a different resolution the template is scaled by the
height ratio first, which is how most games scale their UI. If that misses and
``multi_scale`` is on, a small range of nearby scales is tried, and the winner
is remembered for next time.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Optional

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover - surfaced in the UI
    cv2 = None


@dataclass
class Match:
    x: int            # top-left, in screen-local pixels of the captured monitor
    y: int
    w: int
    h: int
    score: float
    scale: float

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2


class Screen:
    """Grabs a monitor as a BGR numpy array. Safe to use from any thread."""

    def __init__(self, monitor: int = 1) -> None:
        self.monitor_index = monitor
        self._local = threading.local()

    def _sct(self):
        sct = getattr(self._local, "sct", None)
        if sct is None:
            import mss

            sct = getattr(mss, "MSS", mss.mss)()
            self._local.sct = sct
        return sct

    def close_thread(self) -> None:
        """Release this thread's capture handle (each automation run uses a
        new worker thread, so without this every run leaks one)."""
        sct = getattr(self._local, "sct", None)
        if sct is not None:
            self._local.sct = None
            try:
                sct.close()
            except Exception:
                pass

    def monitor(self) -> dict:
        mons = self._sct().monitors
        idx = self.monitor_index if 0 <= self.monitor_index < len(mons) else 1
        return mons[idx]

    def size(self) -> tuple[int, int]:
        m = self.monitor()
        return m["width"], m["height"]

    def offset(self) -> tuple[int, int]:
        m = self.monitor()
        return m["left"], m["top"]

    def grab(self) -> np.ndarray:
        shot = self._sct().grab(self.monitor())
        img = np.asarray(shot)  # BGRA
        return img[:, :, :3].copy()


class StaticScreen:
    """A 'screen' that is just an image; used by tests and the template tester."""

    def __init__(self, image: np.ndarray) -> None:
        self.image = image

    def size(self):
        return self.image.shape[1], self.image.shape[0]

    def offset(self):
        return 0, 0

    def grab(self):
        return self.image


def load_image(path: str) -> np.ndarray:
    if cv2 is None:
        raise RuntimeError("opencv-python is not installed: pip install opencv-python-headless")
    data = np.fromfile(path, dtype=np.uint8)  # handles non-ASCII Windows paths
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"Could not read image: {path}")
    return img


def save_image(path: str, img: np.ndarray) -> None:
    ok, buf = cv2.imencode(os.path.splitext(path)[1] or ".png", img)
    if not ok:
        raise IOError(f"Could not encode image for {path}")
    buf.tofile(path)


def template_path(templates_dir: str, name: str) -> str:
    """Full path of a template, which must stay inside ``templates_dir``.

    Sequence files can be shared, so a template name like ``../../x.png`` or an
    absolute path must not make the app read files from elsewhere on disk.
    """
    root = os.path.realpath(templates_dir)
    path = os.path.realpath(os.path.join(root, str(name)))
    try:
        inside = os.path.commonpath([path, root]) == root
    except ValueError:  # different drives on Windows
        inside = False
    if not name or not inside or path == root:
        raise ValueError(f"Template {name!r} must be an image inside the templates folder")
    return path


class Matcher:
    def __init__(self, templates_dir: str, reference_height: int = 1080,
                 threshold: float = 0.8, multi_scale: bool = True) -> None:
        if cv2 is None:
            raise RuntimeError("opencv-python is not installed: pip install opencv-python-headless")
        self.templates_dir = templates_dir
        self.reference_height = reference_height
        self.threshold = threshold
        self.multi_scale = multi_scale
        self._cache: dict[str, np.ndarray] = {}
        self._scaled: dict[tuple[str, float], np.ndarray] = {}
        self._best_scale: dict[str, float] = {}

    def template(self, name: str) -> np.ndarray:
        if name not in self._cache:
            self._cache[name] = load_image(template_path(self.templates_dir, name))
        return self._cache[name]

    def _scaled_template(self, name: str, scale: float) -> np.ndarray:
        key = (name, round(scale, 3))
        if key not in self._scaled:
            t = self.template(name)
            if abs(scale - 1.0) < 1e-3:
                self._scaled[key] = t
            else:
                interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
                w = max(4, int(round(t.shape[1] * scale)))
                h = max(4, int(round(t.shape[0] * scale)))
                self._scaled[key] = cv2.resize(t, (w, h), interpolation=interp)
        return self._scaled[key]

    @staticmethod
    def _match_once(hay: np.ndarray, tpl: np.ndarray) -> tuple[float, tuple[int, int]]:
        if tpl.shape[0] > hay.shape[0] or tpl.shape[1] > hay.shape[1]:
            return -1.0, (0, 0)
        res = cv2.matchTemplate(hay, tpl, cv2.TM_CCOEFF_NORMED)
        _, mx, _, loc = cv2.minMaxLoc(res)
        if not np.isfinite(mx):  # flat template/region
            return -1.0, (0, 0)
        return float(mx), loc

    def find(self, screen_img: np.ndarray, name: str, threshold: float | None = None,
             region: Optional[tuple[int, int, int, int]] = None) -> Optional[Match]:
        """Best match for template ``name`` or None if below threshold.

        ``region`` is (x, y, w, h) in screen pixels and limits the search,
        which is faster and avoids false hits elsewhere on screen.
        """
        thr = self.threshold if threshold is None else threshold
        ox = oy = 0
        hay = screen_img
        if region:
            x, y, w, h = (int(v) for v in region)
            x, y = max(0, x), max(0, y)
            hay = screen_img[y:y + h, x:x + w]
            ox, oy = x, y
            if hay.size == 0:
                return None

        base = screen_img.shape[0] / float(self.reference_height)
        candidates = [self._best_scale.get(name, base)]
        if abs(candidates[0] - base) > 1e-3:
            candidates.append(base)
        if self.multi_scale and name not in self._best_scale:
            # Only search other scales until this template has been found once;
            # after that the remembered scale is used, which keeps scans cheap.
            candidates += [base * f for f in (0.9, 1.1, 0.8, 1.25, 0.67, 1.5)]

        best: Optional[Match] = None
        for s in candidates:
            tpl = self._scaled_template(name, s)
            score, (mx, my) = self._match_once(hay, tpl)
            if best is None or score > best.score:
                best = Match(mx + ox, my + oy, tpl.shape[1], tpl.shape[0], score, s)
            if score >= thr:
                break  # good enough at the expected scale; skip the rest
        if best is not None and best.score >= thr:
            self._best_scale[name] = best.scale
            return best
        return None

    def score(self, screen_img: np.ndarray, name: str,
              region: Optional[tuple[int, int, int, int]] = None) -> float:
        """Best score regardless of threshold (used by the 'Test' button)."""
        m = self.find(screen_img, name, threshold=-1.0, region=region)
        return m.score if m else 0.0
