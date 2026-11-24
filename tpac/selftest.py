"""`TPAutoClicker.exe --self-test`: checks the packaged build has everything it
needs (Qt widgets, OpenCV matching, bundled templates/sequence, screen capture)
and exits 0 on success. Used by the build workflow."""
from __future__ import annotations

import os
import sys


def run() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import numpy as np

    from .config import SEQUENCES_DIR, TEMPLATES_DIR, install_bundled_files
    from .sequence import Sequence
    from .vision import Matcher, load_image

    install_bundled_files()
    seq = Sequence.load(os.path.join(SEQUENCES_DIR, "tower_defense_retry_loop.json"))
    m = Matcher(TEMPLATES_DIR, reference_height=1080)
    for step in seq.steps:
        name = step.get("template")
        if not name:
            continue
        tpl = load_image(os.path.join(TEMPLATES_DIR, name))
        canvas = np.zeros((1080, 1920, 3), np.uint8)
        canvas[500:500 + tpl.shape[0], 700:700 + tpl.shape[1]] = tpl
        hit = m.find(canvas, name)
        if hit is None or (hit.x, hit.y) != (700, 500):
            print(f"FAIL: template {name} not matched", file=sys.stderr)
            return 1
        if step.get("skip_if"):
            load_image(os.path.join(TEMPLATES_DIR, step["skip_if"]))  # raises if missing

    from PySide6.QtWidgets import QApplication

    from .app import MainWindow

    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    ok = w.table.rowCount() == len(seq.steps) and not w._validate_sequence(w.seq)
    try:
        w._get_screen().grab()
    except Exception as e:  # no display on some CI runners is fine
        print(f"note: screen capture unavailable here: {e}")
    w.seq_dirty = False
    w.clicker.stop()
    del app
    print("self-test OK" if ok else "FAIL: main window did not load the sequence")
    return 0 if ok else 1
