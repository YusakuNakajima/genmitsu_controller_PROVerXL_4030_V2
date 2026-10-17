"""GRBL との通信を別スレッドで行う(GUI を固まらせないため)。

シリアルポートはワーカースレッドだけが読む。GUI は submit() で処理を頼み、
結果は events キューに (種類, 値) で届く:

    ("connected", (port, banner))  接続した
    ("disconnected", None)         切断した
    ("status", dict)               状態(動いている間も届く)
    ("line", str)                  GRBL から届いた行(ok とステータス以外)
    ("log", str)                   お知らせ
    ("error", str)                 エラー
    ("busy", str) / ("idle", None) 処理の開始 / 終了
    ("arrived", int)               巡回で i 番目の位置に着いた
    ("travel", [X, Y, Z])          各軸の可動範囲(接続したとき)
    ("homed", None)                ホーミングが終わった

停止系(stop / hold / resume)はリアルタイムコマンドなので、GUI のスレッドから直接送る。
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Callable

import serial

from .grbl import CYCLE_START, FEED_HOLD, JOG_CANCEL, SOFT_RESET, Grbl, GrblError
from .points import Point

Task = Callable[[Grbl], None]


def move_with_retract(cnc: Grbl, x: float | None, y: float | None, z: float | None,
                      feed: float, z_safe: float | None = None) -> list[float]:
    """機械座標へ移動する。z_safe を指定すると、Z を z_safe まで上げてから XY を動かし、最後に Z を下ろす。"""
    if z_safe is None:
        return cnc.move_to(x=x, y=y, z=z, feed=feed)
    if cnc.position()[2] < z_safe:
        cnc.move_to(z=z_safe, feed=feed)
    cnc.move_to(x=x, y=y, feed=feed)
    return cnc.move_to(z=z, feed=feed)


class StageWorker:
    def __init__(self, events: queue.Queue, poll: float = 0.2,
                 grbl_factory: Callable[[str | None], Grbl] = Grbl):
        self.events = events
        self.poll = poll
        self.grbl_factory = grbl_factory
        self.tasks: queue.Queue[tuple[str, Task]] = queue.Queue()
        self.cancel = threading.Event()
        self.cnc: Grbl | None = None
        self.busy = False
        self._running = False
        self._thread: threading.Thread | None = None

    # ---- 接続 ----

    @property
    def connected(self) -> bool:
        return self.cnc is not None

    @property
    def idle(self) -> bool:
        """処理中でも待ち行列があるわけでもない。"""
        return self.connected and not self.busy and self.tasks.empty()

    def connect(self, port: str | None) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, args=(port,), daemon=True)
        self._thread.start()

    def disconnect(self, timeout: float = 3.0) -> None:
        self._running = False
        self.cancel.set()
        if self._thread:
            self._thread.join(timeout)

    def _emit(self, kind: str, value=None) -> None:
        self.events.put((kind, value))

    def _run(self, port: str | None) -> None:
        try:
            cnc = self.grbl_factory(port)
            banner = cnc.connect()
        except Exception as e:  # ポートが見つからない、開けない、応答がない
            self._emit("error", f"接続できない: {e}")
            self._emit("disconnected")
            return
        cnc.on_status = lambda st: self._emit("status", st)
        cnc.on_line = self._on_line
        self.cnc = cnc
        self._emit("connected", (cnc.port, banner))
        try:
            self._emit("travel", cnc.travel())
        except (GrblError, TimeoutError, KeyError, ValueError) as e:
            self._emit("error", f"可動範囲($130〜$132)を読めない: {e}")
        try:
            while self._running:
                try:
                    label, task = self.tasks.get(timeout=self.poll)
                except queue.Empty:
                    self._poll_status(cnc)
                    continue
                self._run_task(cnc, label, task)
        except (serial.SerialException, OSError) as e:
            self._emit("error", f"通信が切れた: {e}")
        finally:
            self.cnc = None
            cnc.close()
            self._emit("disconnected")

    def _on_line(self, line: str) -> None:
        if line != "ok" and not line.startswith("<"):
            self._emit("line", line)

    def _poll_status(self, cnc: Grbl) -> None:
        try:
            cnc.status()
        except TimeoutError:
            pass  # リセット直後などは応答がないことがある

    def _run_task(self, cnc: Grbl, label: str, task: Task) -> None:
        self.busy = True
        self._emit("busy", label)
        try:
            task(cnc)
        except (GrblError, ValueError, TimeoutError) as e:
            self._emit("error", f"{label}: {e}")
        finally:
            self.busy = False
            self._emit("idle")

    # ---- 処理を頼む ----

    def submit(self, label: str, task: Task) -> bool:
        if not self.connected:
            self._emit("error", "接続していない")
            return False
        self.cancel.clear()
        self.tasks.put((label, task))
        return True

    def home(self) -> bool:
        def task(cnc: Grbl) -> None:
            cnc.home()
            self._emit("homed")
        return self.submit("ホーミング", task)

    def unlock(self) -> bool:
        return self.submit("アンロック", lambda cnc: cnc.unlock())

    def jog(self, x: float = 0, y: float = 0, z: float = 0, feed: float = 1000) -> bool:
        return self.submit("ジョグ", lambda cnc: cnc.jog(x=x or None, y=y or None, z=z or None, feed=feed))

    def move(self, x: float | None, y: float | None, z: float | None, feed: float,
             z_safe: float | None = None) -> bool:
        def task(cnc: Grbl) -> None:
            pos = move_with_retract(cnc, x, y, z, feed, z_safe)
            self._emit("log", f"到着 MPos: {fmt_pos(pos)}")
        return self.submit("移動", task)

    def tour(self, points: list[Point], feed: float, dwell: float, z_safe: float | None = None,
             on_arrive: Callable[[Grbl, int, Point], None] | None = None) -> bool:
        """登録した位置を順に回る。on_arrive は各点に着いたときに呼ぶ。

        点ごとに feed / dwell が指定されていればそれを使い、なければ引数の feed / dwell を使う。
        """
        points = list(points)

        def task(cnc: Grbl) -> None:
            for i, p in enumerate(points):
                if self.cancel.is_set():
                    self._emit("log", "巡回を中止した")
                    return
                p_feed = p.feed if p.feed is not None else feed
                p_dwell = p.dwell if p.dwell is not None else dwell
                move_with_retract(cnc, p.x, p.y, p.z, p_feed, z_safe)
                self._emit("arrived", i)
                self._emit("log", f"[{i + 1}/{len(points)}] {p.name} に到着(速度 {p_feed:g} mm/分、{p_dwell:g} 秒止まる)")
                if on_arrive:
                    on_arrive(cnc, i, p)
                end = time.time() + p_dwell
                while time.time() < end and not self.cancel.is_set():
                    time.sleep(0.05)
            self._emit("log", "巡回が終わった")
        return self.submit("巡回", task)

    # ---- 停止系(GUI のスレッドから直接呼ぶ) ----

    def stop(self) -> None:
        """待ち行列を捨てて、フィードホールド → ソフトリセット。動作中だった場合は Alarm になり、ホーミングが必要。"""
        self.cancel.set()
        while not self.tasks.empty():
            try:
                self.tasks.get_nowait()
            except queue.Empty:
                break
        cnc = self.cnc
        if not cnc:
            return
        cnc.realtime(JOG_CANCEL)
        cnc.realtime(FEED_HOLD)
        threading.Timer(0.3, lambda: cnc.realtime(SOFT_RESET)).start()
        self._emit("log", "停止した(位置が失われた場合は Alarm になるので、ホーミングし直すこと)")

    def hold(self) -> None:
        if self.cnc:
            self.cnc.realtime(FEED_HOLD)

    def resume(self) -> None:
        if self.cnc:
            self.cnc.realtime(CYCLE_START)


def fmt_pos(pos: list[float]) -> str:
    return " ".join(f"{a}{v:.3f}" for a, v in zip("XYZ", pos))
