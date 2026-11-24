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


FRAMES = {k: frame(k) for k in ("in_game", "popup_level_cleared", "popup_base_drowned", "transition",
                                 "setup_screen", "start_fading")}

# The 2X button in its "on" look (teal text), cut from the recording, and the
# same frames with it pasted in, for a game that remembers the speed.
SPEED_ON = load_image(os.path.join(TPL, "double_speed_on.png"))
SPEED_AT = (1860, 124)


def with_speed_on(img):
    out = img.copy()
    x, y = SPEED_AT
    h, w = SPEED_ON.shape[:2]
    out[y:y + h, x:x + w] = SPEED_ON
    return out


FRAMES_ON = {k: with_speed_on(FRAMES[k]) for k in ("in_game", "setup_screen", "start_fading")}

# Button boxes measured from the recording (x0, y0, x1, y1)
RETRY = (683, 708, 958, 764)
RETRY_DROWNED = (688, 694, 948, 742)  # the failure popup sits a little higher
DOUBLE = (1855, 120, 1910, 165)
START = (1640, 1005, 1910, 1075)


def inside(box, x, y):
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


class FakeGame:
    """Minimal state machine of the game shown in the video."""

    def __init__(self, play_frames=3, outcomes=("popup_level_cleared",)):
        self.outcomes = list(outcomes)
        self.popup = self.outcomes[0]
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
            self.popup = self.outcomes[self.levels_started % len(self.outcomes)]
        elif self.state == "transition" and self.ticks >= 2:
            self.state, self.ticks = "setup", 0
        elif self.state == "starting" and self.ticks >= 1:
            self.state, self.ticks = "playing", 0
        frames = FRAMES_ON if self.speed_on else FRAMES
        return {
            "playing": frames["in_game"],
            "popup": FRAMES[self.popup],
            "transition": FRAMES["transition"],
            "setup": frames["setup_screen"],
            "starting": frames["start_fading"],
        }[self.state]

    # input backend interface
    def position(self):
        return self.pos

    def move(self, x, y):
        self.pos = (x, y)

    def click(self, button="left", clicks=1, hold_s=0.0, gap_s=0.03):
        x, y = self.pos
        self.events.append(("click", self.state, x, y))
        if self.state == "popup" and inside(self.retry_box(), x, y):
            self.state, self.ticks = "transition", 0
        elif self.state == "setup" and inside(DOUBLE, x, y):
            self.speed_on = not self.speed_on  # it's a toggle, and the game remembers it
        elif self.state == "setup" and inside(START, x, y):
            self.state, self.ticks = "starting", 0
            self.levels_started += 1

    def retry_box(self):
        return RETRY_DROWNED if self.popup == "popup_base_drowned" else RETRY

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
            assert (state == "popup" and (inside(RETRY, x, y) or inside(RETRY_DROWNED, x, y))) or (
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


def test_loop_handles_win_and_loss_popups():
    """The end popup's title changes (LEVEL CLEARED, THE BASE DROWNED, ...);
    the loop keys off the RETRY button so every outcome is handled."""
    game = FakeGame(outcomes=("popup_level_cleared", "popup_base_drowned"))
    logs = []
    runner, seq = make_runner(game, logs)
    seq.repeat = 4
    runner.start(seq)
    runner.join(timeout=60)
    assert runner.loops_done == 4, "\n".join(logs)
    assert game.levels_started == 4


def speed_clicks(game):
    return [ev for ev in game.events if ev[0] == "click" and ev[1] == "setup" and inside(DOUBLE, ev[2], ev[3])]


def test_double_speed_is_turned_on_once_and_left_on():
    """The game remembers 2X between levels, so clicking it every loop would
    switch it off every other level. It must only be clicked while it's off."""
    game = FakeGame()
    logs = []
    runner, seq = make_runner(game, logs)
    seq.repeat = 4
    runner.start(seq)
    runner.join(timeout=60)
    assert runner.loops_done == 4, "\n".join(logs)
    assert game.speed_on
    assert len(speed_clicks(game)) == 1
    assert sum("not clicking" in line for line in logs) == 3


def test_double_speed_already_on_is_not_clicked():
    game = FakeGame()
    game.speed_on = True
    logs = []
    runner, seq = make_runner(game, logs)
    seq.repeat = 2
    runner.start(seq)
    runner.join(timeout=60)
    assert runner.loops_done == 2
    assert game.speed_on and not speed_clicks(game)


@pytest.mark.parametrize("img, expect_on", [
    (FRAMES["setup_screen"], False),          # recording, before 2X was clicked
    (FRAMES_ON["setup_screen"], True),
    (FRAMES["start_fading"], True),           # recording, after 2X was clicked
    (FRAMES["in_game"], True),
], ids=["setup-off", "setup-on", "start-on", "in-game-on"])
def test_on_and_off_looks_are_told_apart(img, expect_on):
    """Both looks clear the 0.8 threshold on each other; the runner compares
    the two scores instead, which must favour the right one on every frame."""
    m = Matcher(TPL, reference_height=1080, threshold=0.8)
    off_s = m.find(img, "double_speed.png", threshold=-1.0).score
    on_s = m.find(img, "double_speed_on.png", threshold=-1.0).score
    assert (on_s > off_s) == expect_on, (off_s, on_s)
