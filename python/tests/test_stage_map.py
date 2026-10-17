import tkinter as tk

import pytest

from genmitsu.stage_map import StageMap


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("画面がない環境")
    r.withdraw()
    yield r
    r.destroy()


def test_home_is_top_right_and_far_corner_is_bottom_left(root):
    m = StageMap(root, travel=(400, 300, 100), scale=1.0)
    left, top, _, _ = m.margin
    assert m.xy_to_px(0, 0) == (left + 400, top)
    assert m.xy_to_px(-400, -300) == (left, top + 300)


def test_px_to_xy_is_inverse(root):
    m = StageMap(root, scale=0.9)
    px, py = m.xy_to_px(-123.4, -56.7)
    x, y = m.px_to_xy(px, py)
    assert x == pytest.approx(-123.4)
    assert y == pytest.approx(-56.7)


def test_click_inside_area_reports_machine_xy(root):
    clicked = []
    m = StageMap(root, scale=1.0, on_click=lambda x, y: clicked.append((x, y)))
    px, py = m.xy_to_px(-100, -50)
    m._clicked(type("E", (), {"x": px, "y": py})())
    m._clicked(type("E", (), {"x": 0, "y": 0})())  # 範囲の外は無視
    assert clicked == [(-100, -50)]


def test_fit_keeps_aspect_ratio_and_centers(root):
    m = StageMap(root, travel=(400, 300, 100), scale=0.5)
    left, top, right, bottom = m.margin
    # 横長の枠:縦で縮尺が決まり、横は余るので中央に寄せる
    m.fit(left + right + m.zbar_w + 1000, top + bottom + 300)
    assert m.scale == pytest.approx(1.0)
    x0, y0 = m.xy_to_px(-400, 0)
    x1, y1 = m.xy_to_px(0, -300)
    assert (x1 - x0, y1 - y0) == (pytest.approx(400), pytest.approx(300))
    assert x0 - left == pytest.approx(300)  # (1000 - 400) / 2
    # 縮めても、クリック位置と機械座標の対応は保たれる
    m.fit(200, 150)
    x, y = m.px_to_xy(*m.xy_to_px(-123.4, -56.7))
    assert (x, y) == (pytest.approx(-123.4), pytest.approx(-56.7))
