import pytest

from genmitsu import gcode_bounds, strip_comment, strip_spindle


def test_strip_comment():
    assert strip_comment("G0 X1 ; 早送り") == "G0 X1"
    assert strip_comment("(header) G1 Y2 (mid) Z3") == "G1 Y2  Z3"
    assert strip_comment("; only comment") == ""


@pytest.mark.parametrize("line, expected", [
    ("G0X0.000Y0.000S15000M3", "G0X0.000Y0.000S15000"),
    ("M03 S1000", "S1000"),
    ("G1 X1 m4", "G1 X1"),
    ("M30", "M30"),   # プログラム終了は残す
    ("M5", "M5"),     # スピンドル停止は残す
])
def test_strip_spindle(line, expected):
    assert strip_spindle(line) == expected


def test_gcode_bounds_tracks_modal_position():
    lines = ["G90", "G0 Z5", "G0 X0 Y0", "G1 Z-1 F360", "X100", "Y36.5 ; comment", "G0 Z5"]
    assert gcode_bounds(lines) == {"X": (0, 100), "Y": (0, 36.5), "Z": (-1, 5)}


def test_gcode_bounds_rejects_relative_and_inch():
    with pytest.raises(ValueError):
        gcode_bounds(["G91", "G0 X10"])
    with pytest.raises(ValueError):
        gcode_bounds(["G20", "G0 X1"])
