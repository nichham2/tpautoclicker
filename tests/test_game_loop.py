"""End-to-end test of the bundled retry-loop sequence against real frames
from the screen recording, with a fake 'game' that reacts to clicks."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

cv2 = pytest.importorskip("cv2")

from tpac.sequence import Sequence, SequenceRunner  # noqa: E402
from tpac.vision import Matcher, load_image  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")
TPL = os.path.join(ROOT, "templates")


def frame(name):
    return load_image(os.path.join(FIX, name + ".jpg"))


FRAMES = {k: frame(k) for k in ("in_game", "popup_level_cleared", "transition", "setup_screen", "start_fading")}

# Button boxes measured from the recording (x0, y0, x1, y1)
RETRY = (683, 708, 958, 764)
DOUBLE = (1855, 120, 1910, 165)
START = (1640, 1005, 1910, 1075)


def inside(box, x, y):
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


class FakeGame:
    """Minimal state machine of the game shown in the video."""

    def __init__(self, play_frames=3):
        self.state = "playing"
        self.ticks = 0
        self.play_frames = play_frames
        self.pos = (500, 500)
        self.events = []
        self.levels_started = 0
        self.speed_on = False

    # screen interface
    def size(self):
        return 1918, 1078

    def offset(self):
        return 0, 0

    def grab(self):
        self.ticks += 1
        if self.state == "playing" and self.ticks >= self.play_frames:
            self.state, self.ticks = "popup", 0
        elif self.state == "transition" and self.ticks >= 2:
            self.state, self.ticks = "setup", 0
        elif self.state == "starting" and self.ticks >= 1:
            self.state, self.ticks = "playing", 0
        return {
            "playing": FRAMES["in_game"],
            "popup": FRAMES["popup_level_cleared"],
            "transition": FRAMES["transition"],
            "setup": FRAMES["setup_screen"],
            "starting": FRAMES["start_fading"],
        }[self.state]

    # input backend interface
    def position(self):
        return self.pos

    def move(self, x, y):
        self.pos = (x, y)

    def click(self, button="left", clicks=1, hold_s=0.0, gap_s=0.03):
        x, y = self.pos
        self.events.append(("click", self.state, x, y))
        if self.state == "popup" and inside(RETRY, x, y):
            self.state, self.ticks = "transition", 0
        elif self.state == "setup" and inside(DOUBLE, x, y):
            self.speed_on = True
        elif self.state == "setup" and inside(START, x, y):
            self.state, self.ticks = "starting", 0
            self.levels_started += 1

    def tap(self, key, hold_s=0.03):
        self.events.append(("tap", self.state, key))
        if key == "space" and self.state == "setup":
            self.state, self.ticks = "starting", 0
            self.levels_started += 1

    def key_down(self, key):
        pass

    def key_up(self, key):
        pass


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def make_runner(game, logs):
    clock = FakeClock()
    seq = Sequence.load(os.path.join(ROOT, "sequences", "tower_defense_retry_loop.json"))
    matcher = Matcher(TPL, reference_height=seq.reference_resolution[1], threshold=0.8)
    runner = SequenceRunner(game, game, matcher, scan_interval=0.5, log=logs.append,
                            sleep=clock.sleep, clock=clock)
    return runner, seq


def test_retry_loop_runs_three_levels():
    game = FakeGame()
    logs = []
    runner, seq = make_runner(game, logs)
    seq.repeat = 3
    runner.start(seq)
    runner.join(timeout=60)
    assert not runner.running
    assert runner.loops_done == 3, "\n".join(logs)
    assert game.levels_started == 3
    assert game.speed_on
    # Every click landed on a real button in the right state
    for ev in game.events:
        if ev[0] == "click":
            _, state, x, y = ev
            assert (state == "popup" and inside(RETRY, x, y)) or (
                state == "setup" and (inside(DOUBLE, x, y) or inside(START, x, y))
            ), ev


def test_double_speed_step_can_be_disabled():
    game = FakeGame()
    logs = []
    runner, seq = make_runner(game, logs)
    seq.repeat = 1
    seq.steps[3]["enabled"] = False
    runner.start(seq)
    runner.join(timeout=60)
    assert runner.loops_done == 1
    assert not game.speed_on


def test_corner_failsafe_stops():
    game = FakeGame(play_frames=10**9)  # never ends
    game.pos = (0, 0)
    logs = []
    runner, seq = make_runner(game, logs)
    runner.start(seq)
    runner.join(timeout=10)
    assert not runner.running
    assert any("failsafe" in line for line in logs)


def test_start_from_setup_screen():
    game = FakeGame()
    game.state = "setup"
    logs = []
    runner, seq = make_runner(game, logs)
    seq.repeat = 1
    runner.start(seq, start_at=2)
    runner.join(timeout=60)
    assert game.levels_started == 1
