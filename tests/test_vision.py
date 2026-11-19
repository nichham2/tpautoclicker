import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
cv2 = pytest.importorskip("cv2")

from tpac.vision import Matcher, load_image  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")
TPL = os.path.join(ROOT, "templates")


def frame(name):
    return load_image(os.path.join(FIX, name + ".jpg"))


@pytest.fixture(scope="module")
def m():
    return Matcher(TPL, reference_height=1080, threshold=0.8, multi_scale=True)


@pytest.mark.parametrize("tpl,present,absent", [
    ("level_cleared.png", ["popup_level_cleared"], ["in_game", "setup_screen", "transition"]),
    ("retry.png", ["popup_level_cleared"], ["in_game", "setup_screen", "transition"]),
    ("skill_tree.png", ["popup_level_cleared"], ["in_game", "setup_screen"]),
    ("start.png", ["setup_screen"], ["in_game", "popup_level_cleared", "transition"]),
])
def test_templates_detect_only_their_screen(m, tpl, present, absent):
    for f in present:
        assert m.find(frame(f), tpl) is not None, f"{tpl} should be on {f}"
    for f in absent:
        assert m.find(frame(f), tpl) is None, f"{tpl} should NOT be on {f}"


def test_retry_center_is_on_button(m):
    hit = m.find(frame("popup_level_cleared"), "retry.png")
    cx, cy = hit.center
    assert 700 < cx < 940 and 712 < cy < 760


@pytest.mark.parametrize("w,h", [(2560, 1440), (1280, 720), (3840, 2160)])
def test_other_resolutions(w, h):
    m = Matcher(TPL, reference_height=1080, threshold=0.8)
    img = cv2.resize(frame("setup_screen"), (w, h), interpolation=cv2.INTER_AREA)
    hit = m.find(img, "start.png")
    assert hit is not None
    cx, cy = hit.center
    assert abs(cx / w - 1775 / 1918) < 0.01 and abs(cy / h - 1040 / 1078) < 0.01


def test_region_limits_search(m):
    img = frame("setup_screen")
    assert m.find(img, "start.png", region=(0, 0, 900, 500)) is None
    assert m.find(img, "start.png", region=(1500, 900, 418, 178)) is not None
