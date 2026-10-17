"""StageWorker のテスト。Grbl を偽物に差し替えるので、機械は不要。"""

import queue
import threading
import time

import pytest

from genmitsu import GrblError
from genmitsu.points import Point
from genmitsu.worker import StageWorker, move_with_retract


class FakeGrbl:
    """呼ばれた操作を記録し、移動先をそのまま現在位置にする偽の Grbl。"""

    def __init__(self, port=None):
        self.port = port or "fake"
        self.pos = [-3.0, -3.0, -3.0]
        self.calls: list[tuple] = []
        self.on_status = None
        self.on_line = None
        self.realtime_sent: list[bytes] = []
        self.move_delay = 0.0
        self.feeds: list[float] = []

    def connect(self):
        return "Grbl 1.1h ['$' for help]"

    def close(self):
        self.calls.append(("close",))

    def status(self):
        st = {"state": "Idle", "MPos": list(self.pos)}
        if self.on_status:
            self.on_status(st)
        return st

    def position(self):
        return list(self.pos)

    def travel(self):
        return [400.0, 300.0, 100.0]

    def move_to(self, x=None, y=None, z=None, feed=None):
        if x is not None and x > -1:
            raise ValueError(f"X{x} は範囲外")
        time.sleep(self.move_delay)
        self.calls.append(("move_to", x, y, z))
        self.feeds.append(feed)
        for i, v in enumerate((x, y, z)):
            if v is not None:
                self.pos[i] = v
        return list(self.pos)

    def home(self):
        self.calls.append(("home",))

    def jog(self, x=None, y=None, z=None, feed=None):
        if z is not None and z > 0:
            raise GrblError("error:15", "$J=...")
        self.calls.append(("jog", x, y, z))

    def realtime(self, cmd):
        self.realtime_sent.append(cmd)


def drain(events: queue.Queue, until: str, timeout: float = 2.0) -> list[tuple]:
    """until の種類のイベントが届くまで集める。"""
    got = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            kind, value = events.get(timeout=0.05)
        except queue.Empty:
            continue
        got.append((kind, value))
        if kind == until:
            return got
    raise AssertionError(f"{until} が届かない: {got}")


@pytest.fixture
def worker():
    events = queue.Queue()
    fake = FakeGrbl()
    w = StageWorker(events, poll=0.02, grbl_factory=lambda port: fake)
    w.connect(None)
    drain(events, "connected")
    yield w, fake, events
    w.disconnect()


def test_move_with_retract_raises_z_first_then_lowers():
    cnc = FakeGrbl()
    cnc.pos = [-50.0, -50.0, -20.0]
    move_with_retract(cnc, -100, -80, -30, feed=1000, z_safe=-5)
    assert cnc.calls == [("move_to", None, None, -5), ("move_to", -100, -80, None), ("move_to", None, None, -30)]


def test_move_with_retract_skips_raise_when_already_high():
    cnc = FakeGrbl()
    move_with_retract(cnc, -100, -80, -30, feed=1000, z_safe=-5)
    assert cnc.calls[0] == ("move_to", -100, -80, None)


def test_reports_travel_after_connect():
    events = queue.Queue()
    w = StageWorker(events, poll=0.02, grbl_factory=FakeGrbl)
    w.connect(None)
    got = drain(events, "travel")
    w.disconnect()
    assert got[-1] == ("travel", [400.0, 300.0, 100.0])


def test_polls_status_while_idle(worker):
    _, _, events = worker
    kinds = [k for k, _ in drain(events, "status")]
    assert "status" in kinds


def test_tasks_run_in_order(worker):
    w, fake, events = worker
    w.home()
    w.jog(x=-1)
    w.move(-100, -50, -10, feed=2000)
    drain(events, "log")  # move の到着ログ
    assert [c[0] for c in fake.calls] == ["home", "jog", "move_to"]


def test_errors_are_reported_not_raised(worker):
    w, _, events = worker
    w.jog(z=10)
    got = drain(events, "error")
    assert "error:15" in got[-1][1]
    w.move(5, None, None, feed=1000)
    got = drain(events, "error")
    assert "範囲外" in got[-1][1]


def test_tour_visits_points_and_reports_arrival(worker):
    w, fake, events = worker
    points = [Point("A", -10, -10, -10), Point("B", -20, -20, -10)]
    arrived = []
    w.tour(points, feed=1000, dwell=0, on_arrive=lambda cnc, i, p: arrived.append(p.name))
    got = drain(events, "idle")
    assert [v for k, v in got if k == "arrived"] == [0, 1]
    assert arrived == ["A", "B"]
    assert fake.pos == [-20, -20, -10]


def test_stop_cancels_tour_and_sends_reset(worker):
    w, fake, events = worker
    fake.move_delay = 0.1
    points = [Point(f"P{i}", -10 - i, -10, -10) for i in range(10)]
    w.tour(points, feed=1000, dwell=0)
    drain(events, "arrived")
    w.stop()
    got = drain(events, "idle")
    assert len([1 for k, _ in got if k == "arrived"]) < 9
    time.sleep(0.4)  # ソフトリセットはフィードホールドの 0.3 秒後
    assert fake.realtime_sent == [b"\x85", b"!", b"\x18"]


def test_submit_without_connection_is_rejected():
    events = queue.Queue()
    w = StageWorker(events)
    assert w.home() is False
    assert events.get_nowait()[0] == "error"


def test_home_reports_homed(worker):
    w, fake, events = worker
    w.home()
    kinds = [k for k, _ in drain(events, "idle")]
    assert kinds.index("homed") < kinds.index("idle")


def test_tour_uses_per_point_feed_and_dwell_or_defaults(worker):
    w, fake, events = worker
    points = [Point("速い", -10, -10, -10, feed=3000), Point("既定", -20, -20, -10),
              Point("長く止まる", -30, -30, -10, dwell=0.3)]
    start = time.time()
    w.tour(points, feed=1000, dwell=0)
    got = drain(events, "idle")
    assert fake.feeds == [3000, 1000, 1000]
    assert time.time() - start >= 0.3
    logs = [v for k, v in got if k == "log"]
    assert any("速度 3000" in line for line in logs)
