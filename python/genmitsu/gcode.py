"""G-code の解析(機械とは通信しない)。"""

from __future__ import annotations

import re
from typing import Iterable


def strip_comment(line: str) -> str:
    """'; コメント' と '( コメント )' を取り除く。"""
    line = re.sub(r"\(.*?\)", "", line)
    line = line.split(";", 1)[0]
    return line.strip()


def strip_spindle(line: str) -> str:
    """M3 / M4(スピンドル回転)を取り除く。M30 などは残す。"""
    return re.sub(r"M0*[34](?!\d)", "", line, flags=re.I).strip()


def gcode_bounds(lines: Iterable[str]) -> dict[str, tuple[float, float]]:
    """G-code が動く範囲(ワーク座標)を {'X': (最小, 最大), ...} で返す。

    G90(絶対座標)・mm 単位・直線移動の終点だけを見る簡易版。G91 / G20 / 円弧の膨らみは考えない。
    """
    pos: dict[str, float] = {}
    bounds: dict[str, list[float]] = {}
    for raw in lines:
        line = strip_comment(raw).upper()
        if re.search(r"G91(?!\.)|G20", line):
            raise ValueError(f"G91 / G20 を含む G-code は範囲を計算できない: {raw.strip()}")
        for axis, value in re.findall(r"([XYZ])\s*(-?\d*\.?\d+)", line):
            pos[axis] = float(value)
        for axis, value in pos.items():
            b = bounds.setdefault(axis, [value, value])
            b[0], b[1] = min(b[0], value), max(b[1], value)
    return {a: (b[0], b[1]) for a, b in sorted(bounds.items())}
