"""GUI の表示の切り替え。機械にはつながず、ワーカーからのイベントを直接渡す。"""

import tkinter as tk

import pytest

from genmitsu.gui import StageApp


@pytest.fixture
def app(tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("画面がない環境")
    root.withdraw()
    a = StageApp(root, points_path=tmp_path / "points.json")
    yield a
    root.destroy()


def connect(app):
    app.worker.cnc = object()  # 接続している扱いにする
    app._handle_event("connected", ("fake", "Grbl 1.1h"))


def test_asks_to_connect_first(app):
    assert app.map.message == "接続してください"


def test_asks_for_homing_until_homed_and_hides_position(app):
    connect(app)
    app._handle_event("status", {"state": "Alarm", "MPos": [0.0, 0.0, 0.0]})
    assert app.map.message == "ホーミングしてください"
    assert app.hint_var.get() == "ホーミングしてください"
    assert app.map.current is None  # ホーミング前の (0, 0, 0) は意味がないので描かない

    app._handle_event("busy", "ホーミング")
    assert app.map.message == "ホーミング中…"

    app._handle_event("homed", None)
    app._handle_event("idle", None)
    app._handle_event("status", {"state": "Idle", "MPos": [-3.0, -3.0, -3.0]})
    assert app.map.message is None
    assert app.hint_var.get() == ""
    assert app.map.current == [-3.0, -3.0, -3.0]


def test_alarm_after_homing_asks_again(app):
    connect(app)
    app._handle_event("homed", None)
    app._handle_event("status", {"state": "Alarm:1", "MPos": [-50.0, -50.0, -3.0]})
    assert app.map.message == "ホーミングしてください"


def test_unlock_without_homing_warns_origin_unknown(app):
    connect(app)
    app._handle_event("status", {"state": "Idle", "MPos": [0.0, 0.0, 0.0]})
    assert "原点が未確認" in app.map.message
