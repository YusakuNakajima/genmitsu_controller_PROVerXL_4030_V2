import pytest

from genmitsu.points import Point, load_points, point_from_fields, save_points


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "sub" / "points.json"
    points = [Point("試料A", -100, -50, -10), Point("B", -150.5, -100, -20.25)]
    save_points(path, points)
    assert load_points(path) == points


def test_load_missing_file_is_empty(tmp_path):
    assert load_points(tmp_path / "none.json") == []


def test_feed_and_dwell_roundtrip_and_old_files_still_load(tmp_path):
    path = tmp_path / "points.json"
    save_points(path, [Point("A", -1, -2, -3, feed=1500, dwell=2.5), Point("B", -4, -5, -6)])
    assert load_points(path) == [Point("A", -1, -2, -3, 1500, 2.5), Point("B", -4, -5, -6, None, None)]
    # 速度・秒数のない古い形式
    path.write_text('{"points": [{"name": "C", "x": -1, "y": -1, "z": -1}]}', encoding="utf-8")
    assert load_points(path) == [Point("C", -1, -1, -1)]


def test_point_from_fields():
    assert point_from_fields(" A ", "-1", "-2.5", "-3", "", " ") == Point("A", -1, -2.5, -3)
    assert point_from_fields("B", "-1", "-2", "-3", "800", "0") == Point("B", -1, -2, -3, 800, 0)


@pytest.mark.parametrize("fields, message", [
    (("", "-1", "-1", "-1"), "名前"),
    (("A", "abc", "-1", "-1"), "X"),
    (("A", "-1", "-1", "-1", "0"), "速度"),
    (("A", "-1", "-1", "-1", "fast"), "速度"),
    (("A", "-1", "-1", "-1", "", "-1"), "秒数"),
])
def test_point_from_fields_rejects_bad_input(fields, message):
    with pytest.raises(ValueError, match=message):
        point_from_fields(*fields)
