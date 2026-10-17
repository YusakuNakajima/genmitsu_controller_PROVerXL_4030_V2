"""登録した位置(機械座標)の読み書き。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

# GUI が自動で保存する場所
DEFAULT_POINTS_PATH = Path.home() / ".genmitsu" / "stage_points.json"


@dataclass
class Point:
    name: str
    x: float
    y: float
    z: float
    feed: float | None = None   # この点へ向かう速度(mm/分)。None なら巡回の既定値
    dwell: float | None = None  # この点で止まる秒数。None なら巡回の既定値


def load_points(path: str | Path) -> list[Point]:
    """JSON から読む。ファイルがなければ空のリスト。"""
    path = Path(path)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Point(str(p["name"]), float(p["x"]), float(p["y"]), float(p["z"]),
                  _optional(p.get("feed")), _optional(p.get("dwell"))) for p in data["points"]]


def _optional(value) -> float | None:
    return None if value is None else float(value)


def point_from_fields(name: str, x: str, y: str, z: str, feed: str = "", dwell: str = "") -> Point:
    """入力欄の文字列から Point を作る。速度・秒数は空欄なら None(既定値を使う)。不正なら ValueError。"""
    name = name.strip()
    if not name:
        raise ValueError("名前が空")
    coords = []
    for axis, text in zip("XYZ", (x, y, z)):
        try:
            coords.append(float(text))
        except ValueError:
            raise ValueError(f"{axis} が数値ではない: {text!r}") from None
    opts = []
    for label, text, allow_zero in (("速度", feed, False), ("秒数", dwell, True)):
        text = text.strip()
        if not text:
            opts.append(None)
            continue
        try:
            v = float(text)
        except ValueError:
            raise ValueError(f"{label} が数値ではない: {text!r}") from None
        if v < 0 or (v == 0 and not allow_zero):
            raise ValueError(f"{label} は {'0 以上' if allow_zero else '0 より大きい値'}にすること: {text}")
        opts.append(v)
    return Point(name, *coords, *opts)


def save_points(path: str | Path, points: list[Point]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"coordinates": "machine", "points": [asdict(p) for p in points]}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
