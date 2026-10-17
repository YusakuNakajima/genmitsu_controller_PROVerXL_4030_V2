"""Genmitsu PROVerXL 4030 V2 (GRBL 1.1h) を Python から制御する最小限のモジュール。

使い方:
    from genmitsu import Grbl

    with Grbl() as cnc:          # ポートは自動検出(CH340)
        cnc.home()
        cnc.move_to(x=-100, y=-50, feed=2000)
        print(cnc.position())

UGS など他のソフトがポートを開いていると接続できないので、先に切断しておくこと。
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Callable, Iterable

import serial
from serial.tools import list_ports

from .gcode import strip_comment, strip_spindle

# CH340 の USB ベンダー ID
CH340_VID = 0x1A86

# リアルタイムコマンド(改行なしの 1 バイトで送ると即座に効く)
STATUS_QUERY = b"?"
FEED_HOLD = b"!"
CYCLE_START = b"~"
SOFT_RESET = b"\x18"
JOG_CANCEL = b"\x85"


class GrblError(Exception):
    """GRBL が error:N / ALARM:N を返したとき。"""

    def __init__(self, message: str, line: str | None = None):
        super().__init__(f"{message} (送信: {line})" if line else message)
        self.message = message
        self.line = line


def find_port() -> str:
    """CH340 のシリアルポートを探す。見つからなければ usbserial を返す。"""
    ports = list(list_ports.comports())
    for p in ports:
        if p.vid == CH340_VID:
            return p.device
    for p in ports:
        if "usbserial" in p.device or "COM" in p.device:
            return p.device
    raise RuntimeError("CNC のシリアルポートが見つからない。USB ケーブルと電源を確認すること")


def parse_status(line: str) -> dict:
    """'<Idle|MPos:0.000,0.000,0.000|FS:0,0>' を辞書にする。"""
    body = line.strip().lstrip("<").rstrip(">")
    fields = body.split("|")
    result: dict = {"state": fields[0]}
    for field in fields[1:]:
        key, _, value = field.partition(":")
        parts = value.split(",")
        try:
            result[key] = [float(v) for v in parts]
        except ValueError:
            result[key] = value
    return result


class Grbl:
    def __init__(self, port: str | None = None, baud: int = 115200, verbose: bool = False):
        self.port = port or find_port()
        self.baud = baud
        self.verbose = verbose
        self.ser: serial.Serial | None = None
        self.wco = [0.0, 0.0, 0.0]  # ワーク座標オフセット(WPos = MPos - WCO)
        self._travel: list[float] | None = None  # $130〜$132(動ける範囲)
        # GUI などに知らせるためのフック。on_line は受信した全行、on_status は status() の結果を受け取る
        self.on_line: Callable[[str], None] | None = None
        self.on_status: Callable[[dict], None] | None = None

    # ---- 接続 ----

    def connect(self) -> str:
        """ポートを開いて GRBL の起動メッセージを返す。開くと GRBL はリセットされる。"""
        self.ser = serial.Serial(self.port, self.baud, timeout=0.1)
        self.ser.write(b"\r\n\r\n")
        deadline = time.time() + 3
        banner = ""
        while time.time() < deadline:
            line = self._readline()
            if line.startswith("Grbl"):
                banner = line
                break
        time.sleep(0.2)
        self.ser.reset_input_buffer()
        if not banner:
            raise RuntimeError(f"{self.port} から GRBL の応答がない")
        return banner

    def close(self) -> None:
        if self.ser and self.ser.is_open:
            self.ser.close()

    def __enter__(self) -> "Grbl":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- 低レベル送受信 ----

    def _readline(self) -> str:
        raw = self.ser.readline()
        line = raw.decode("ascii", errors="replace").strip()
        if line and self.verbose:
            print(f"<< {line}")
        if line and self.on_line:
            self.on_line(line)
        return line

    def send(self, line: str, timeout: float = 10.0) -> list[str]:
        """1 行送って ok まで待つ。途中の応答行(ok 以外)をリストで返す。"""
        line = line.strip()
        if self.verbose:
            print(f">> {line}")
        self.ser.write((line + "\n").encode("ascii"))
        replies: list[str] = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            reply = self._readline()
            if not reply:
                continue
            if reply == "ok":
                return replies
            if reply.startswith("error:") or reply.startswith("ALARM:"):
                raise GrblError(reply, line)
            replies.append(reply)
        raise TimeoutError(f"応答がタイムアウトした: {line}")

    def realtime(self, cmd: bytes) -> None:
        """リアルタイムコマンドを送る(FEED_HOLD, CYCLE_START, SOFT_RESET, JOG_CANCEL)。"""
        self.ser.write(cmd)

    # ---- 状態 ----

    def status(self, timeout: float = 1.0) -> dict:
        """現在の状態を返す。例: {'state': 'Idle', 'MPos': [...], 'WPos': [...], 'FS': [...]}"""
        self.ser.write(STATUS_QUERY)
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = self._readline()
            if line.startswith("<"):
                st = parse_status(line)
                if "WCO" in st:
                    self.wco = st["WCO"]
                if "MPos" in st and "WPos" not in st:
                    st["WPos"] = [m - o for m, o in zip(st["MPos"], self.wco)]
                if self.on_status:
                    self.on_status(st)
                return st
        raise TimeoutError("ステータスの応答がない")

    def wait_idle(self, timeout: float = 300.0, poll: float = 0.2) -> dict:
        """状態が Idle になるまで待つ。Alarm になったら例外。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            st = self.status()
            if st["state"] == "Idle":
                return st
            if st["state"].startswith("Alarm"):
                raise GrblError(f"Alarm 状態になった: {st}")
            time.sleep(poll)
        raise TimeoutError("Idle にならなかった")

    def settings(self) -> dict[str, str]:
        """$$ の内容を {'$20': '1', ...} で返す。"""
        result = {}
        for line in self.send("$$"):
            m = re.match(r"(\$\d+)=(\S+)", line)
            if m:
                result[m.group(1)] = m.group(2)
        return result

    # ---- よく使う操作 ----

    def home(self, timeout: float = 120.0) -> None:
        """ホーミング($H)。終わると Z は一番上にいる。"""
        self.send("$H", timeout=timeout)

    def unlock(self) -> None:
        """アラームの一時解除($X)。原点が不明なので注意して動かすこと。"""
        self.send("$X")

    def jog(self, x: float | None = None, y: float | None = None, z: float | None = None,
            feed: float = 1000, relative: bool = True) -> None:
        """ジョグ移動($J=)。ソフトリミットを超える指令は error:15 で拒否される。"""
        axes = "".join(f"{name}{val:.3f}" for name, val in (("X", x), ("Y", y), ("Z", z)) if val is not None)
        if not axes:
            return
        mode = "G91" if relative else "G90"
        self.send(f"$J={mode} G21 {axes} F{feed:g}")

    def travel(self) -> list[float]:
        """各軸の動ける範囲 [X, Y, Z](mm)。機械座標では -travel 〜 0 の範囲を動ける。"""
        if self._travel is None:
            s = self.settings()
            self._travel = [float(s[k]) for k in ("$130", "$131", "$132")]
        return self._travel

    def position(self) -> list[float]:
        """現在の機械座標 [X, Y, Z]。"""
        return self.status()["MPos"]

    def move_to(self, x: float | None = None, y: float | None = None, z: float | None = None,
                feed: float | None = None, wait: bool = True, margin: float = 1.0) -> list[float]:
        """機械座標で絶対位置へ動かす(G53)。feed を省略すると早送り(G0)。

        G0/G1 がソフトリミットにかかると ALARM:2 でホーミングからやり直しになるので、
        動く前に範囲(-travel + margin 〜 -margin)を確かめて、外なら ValueError にする。
        wait=True なら止まるまで待って、到着後の機械座標を返す。
        """
        target = {"X": x, "Y": y, "Z": z}
        for (axis, val), limit in zip(target.items(), self.travel()):
            if val is not None and not (-limit + margin <= val <= -margin):
                raise ValueError(f"{axis}{val} は範囲外(動ける範囲 {-limit + margin:g} 〜 {-margin:g})")
        axes = "".join(f"{a}{v:.3f}" for a, v in target.items() if v is not None)
        if not axes:
            return self.position()
        motion = f"G1 F{feed:g}" if feed else "G0"
        self.send(f"G53 {motion} {axes}")
        if wait:
            return self.wait_idle()["MPos"]
        return self.position()

    def work_offset(self, name: str = "G54") -> list[float]:
        """$# からワーク座標のオフセット(機械座標でのワーク原点)を返す。EEPROM に保存されている。"""
        for line in self.send("$#"):
            m = re.match(rf"\[{name}:([-\d.,]+)\]", line)
            if m:
                return [float(v) for v in m.group(1).split(",")]
        raise GrblError(f"{name} のオフセットが取得できない")

    def set_work_zero(self, x: bool = True, y: bool = True, z: bool = True) -> None:
        """現在位置をワーク座標(G54)の原点にする。"""
        axes = " ".join(f"{a}0" for a, use in (("X", x), ("Y", y), ("Z", z)) if use)
        self.send(f"G10 L20 P1 {axes}")

    def stop(self) -> None:
        """フィードホールドしてからソフトリセット。リセット後は Alarm になることがある。"""
        self.realtime(FEED_HOLD)
        time.sleep(0.5)
        self.realtime(SOFT_RESET)

    # ---- G-code の送信 ----

    def stream(self, lines: Iterable[str], progress: bool = True, spindle: bool = False) -> None:
        """G-code を 1 行ずつ送る(send-response 方式。遅いが確実)。

        spindle=False(既定)なら M3 / M4(スピンドル回転)を取り除いて送る。
        """
        cleaned = [strip_comment(l) for l in lines]
        if not spindle:
            cleaned = [strip_spindle(c) for c in cleaned]
        cleaned = [c for c in cleaned if c]
        total = len(cleaned)
        for i, line in enumerate(cleaned, 1):
            self.send(line, timeout=600)
            if progress:
                print(f"\r[{i}/{total}] {line[:40]:<40}", end="", flush=True)
        if progress:
            print()
        self.wait_idle(timeout=3600)

    def stream_file(self, path: str | Path, progress: bool = True, spindle: bool = False) -> None:
        with open(path, encoding="utf-8", errors="replace") as f:
            self.stream(f.readlines(), progress=progress, spindle=spindle)
