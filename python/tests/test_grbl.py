"""Grbl クラスのテスト。シリアルポートを偽物に差し替えるので、機械は不要。"""

import pytest

from genmitsu import Grbl, GrblError, parse_status


class FakeSerial:
    """送った行に対して、決めておいた応答を返す偽のシリアルポート。"""

    def __init__(self, replies: dict[str, list[str]]):
        self.replies = replies
        self.written: list[str] = []
        self.pending: list[str] = []

    def write(self, data: bytes) -> None:
        text = data.decode().strip()
        self.written.append(text)
        self.pending += self.replies.get(text, ["ok"])

    def readline(self) -> bytes:
        return (self.pending.pop(0) + "\r\n").encode() if self.pending else b""


IDLE = "<Idle|MPos:-100.000,-50.000,-10.000|FS:0,0>"


def make_grbl(replies: dict[str, list[str]] | None = None) -> tuple[Grbl, FakeSerial]:
    fake = FakeSerial({"?": [IDLE], **(replies or {})})
    cnc = Grbl(port="fake")
    cnc.ser = fake
    cnc._travel = [400.0, 300.0, 100.0]
    return cnc, fake


def test_parse_status():
    st = parse_status("<Alarm|MPos:0.000,0.000,0.000|Bf:15,128|FS:0,0|WCO:-3.000,-3.000,-3.000>")
    assert st["state"] == "Alarm"
    assert st["MPos"] == [0, 0, 0]
    assert st["WCO"] == [-3, -3, -3]


def test_status_computes_wpos_from_last_wco():
    cnc, _ = make_grbl()
    cnc.wco = [-3.0, -3.0, -3.0]
    assert cnc.status()["WPos"] == [-97, -47, -7]


def test_send_returns_lines_before_ok():
    cnc, _ = make_grbl({"$I": ["[VER:1.1h.20190825:]", "[OPT:V,15,128]", "ok"]})
    assert cnc.send("$I") == ["[VER:1.1h.20190825:]", "[OPT:V,15,128]"]


def test_send_raises_on_error():
    cnc, _ = make_grbl({"$J=G91 G21 Z10.000 F1000": ["error:15"]})
    with pytest.raises(GrblError, match="error:15"):
        cnc.jog(z=10)


def test_settings_and_work_offset():
    cnc, _ = make_grbl({
        "$$": ["$20=1", "$130=400.000", "ok"],
        "$#": ["[G54:-3.000,-3.000,-3.000]", "[G55:0.000,0.000,0.000]", "ok"],
    })
    assert cnc.settings() == {"$20": "1", "$130": "400.000"}
    assert cnc.work_offset() == [-3, -3, -3]


def test_move_to_sends_machine_coordinates_and_waits():
    cnc, fake = make_grbl()
    assert cnc.move_to(x=-100, y=-50, feed=2000) == [-100, -50, -10]
    assert fake.written[0] == "G53 G1 F2000 X-100.000Y-50.000"
    assert cnc.move_to(z=-10) == [-100, -50, -10]
    assert "G53 G0 Z-10.000" in fake.written


@pytest.mark.parametrize("target", [{"x": 1}, {"x": -399.5}, {"y": -300}, {"z": -0.5}])
def test_move_to_rejects_out_of_range_before_sending(target):
    cnc, fake = make_grbl()
    with pytest.raises(ValueError):
        cnc.move_to(**target)
    assert fake.written == []


def test_stream_strips_spindle_by_default():
    cnc, fake = make_grbl()
    cnc.stream(["G0 X0 S15000 M3 ; start", "G1 X-1 F100", "M5", "M30"], progress=False)
    assert fake.written[:4] == ["G0 X0 S15000", "G1 X-1 F100", "M5", "M30"]
