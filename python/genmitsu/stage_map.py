"""機械全体のどこにいるかを描く図(XY を上から見た図 + Z のバー)。

機械座標で描く。ホーミング位置(0, 0)が右上の角で、X は左へ、Y は下へ - 方向に進む
($23=0 なので、ホーミングは X+ / Y+ / Z+ の端で終わる)。
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable

from .points import Point

BG = "#fafafa"
AREA = "#ffffff"
GRID = "#e0e0e0"
TEXT = "#616161"
POINT = "#1565c0"
SELECTED = "#ef6c00"
CURRENT = "#c62828"
TARGET = "#2e7d32"


class StageMap(tk.Canvas):
    def __init__(self, parent: tk.Widget, travel: tuple[float, float, float] = (400, 300, 100),
                 scale: float = 0.9, on_click: Callable[[float, float], None] | None = None):
        self.scale = scale
        self.margin = (34, 14, 14, 24)  # 左, 上, 右, 下
        self.offset = (0.0, 0.0)  # 図を中央に寄せるためのずらし量(px)
        self.zbar_w = 56
        self.on_click = on_click
        self.travel = travel
        self.points: list[Point] = []
        self.selected: int | None = None
        self.current: list[float] | None = None
        self.target: tuple[float | None, float | None, float | None] = (None, None, None)
        self.message: str | None = None
        w, h = self._size()
        super().__init__(parent, width=w, height=h, bg=BG, highlightthickness=0)
        self.bind("<Button-1>", self._clicked)
        self.bind("<Configure>", lambda e: self.fit(e.width, e.height))
        self.redraw()

    # ---- 座標の変換 ----

    def _size(self) -> tuple[int, int]:
        left, top, right, bottom = self.margin
        return (int(left + self.travel[0] * self.scale + right + self.zbar_w),
                int(top + self.travel[1] * self.scale + bottom))

    def fit(self, width: int, height: int) -> None:
        """キャンバスの大きさに合わせて縮尺を決める(縦横比は保ち、余白は左右・上下に均等に振る)。"""
        left, top, right, bottom = self.margin
        avail_w = width - left - right - self.zbar_w
        avail_h = height - top - bottom
        if avail_w < 20 or avail_h < 20:
            return
        tx, ty, _ = self.travel
        self.scale = min(avail_w / tx, avail_h / ty)
        self.offset = ((avail_w - tx * self.scale) / 2, (avail_h - ty * self.scale) / 2)
        self.redraw()

    def _origin(self) -> tuple[float, float]:
        """可動範囲の左上の角の位置(px)。"""
        return self.margin[0] + self.offset[0], self.margin[1] + self.offset[1]

    def xy_to_px(self, x: float, y: float) -> tuple[float, float]:
        ox, oy = self._origin()
        return ox + (x + self.travel[0]) * self.scale, oy + (-y) * self.scale

    def px_to_xy(self, px: float, py: float) -> tuple[float, float]:
        ox, oy = self._origin()
        return (px - ox) / self.scale - self.travel[0], -(py - oy) / self.scale

    def _z_to_py(self, z: float) -> float:
        _, oy = self._origin()
        h = self.travel[1] * self.scale
        return oy + (-z) / self.travel[2] * h

    def _zbar_x(self) -> float:
        ox, _ = self._origin()
        return ox + self.travel[0] * self.scale + self.margin[2] + 14

    # ---- 状態を変える ----

    def set_travel(self, travel: tuple[float, float, float]) -> None:
        self.travel = tuple(travel)
        if self.winfo_width() > 1:
            self.fit(self.winfo_width(), self.winfo_height())
        else:
            self.redraw()

    def set_points(self, points: list[Point], selected: int | None = None) -> None:
        self.points = list(points)
        self.selected = selected
        self.redraw()

    def set_current(self, mpos: list[float] | None) -> None:
        self.current = mpos
        self._draw_dynamic()

    def set_target(self, x: float | None, y: float | None, z: float | None) -> None:
        self.target = (x, y, z)
        self._draw_dynamic()

    def set_message(self, message: str | None) -> None:
        """図の上に大きく出すお知らせ(「ホーミングしてください」など)。None で消す。"""
        if message != self.message:
            self.message = message
            self._draw_dynamic()

    # ---- 描画 ----

    def redraw(self) -> None:
        self.delete("all")
        tx, ty, tz = self.travel
        x0, y0 = self.xy_to_px(-tx, 0)
        x1, y1 = self.xy_to_px(0, -ty)
        self.create_rectangle(x0, y0, x1, y1, fill=AREA, outline=TEXT)

        # 50mm ごとの格子、100mm ごとに目盛り
        for x in range(0, int(tx) + 1, 50):
            px, _ = self.xy_to_px(-x, 0)
            if 0 < x < tx:
                self.create_line(px, y0, px, y1, fill=GRID)
            if x % 100 == 0:
                self.create_text(px, y1 + 4, text=f"{-x}", anchor="n", fill=TEXT, font=("Helvetica", 9))
        for y in range(0, int(ty) + 1, 50):
            _, py = self.xy_to_px(0, -y)
            if 0 < y < ty:
                self.create_line(x0, py, x1, py, fill=GRID)
            if y % 100 == 0:
                self.create_text(x0 - 4, py, text=f"{-y}", anchor="e", fill=TEXT, font=("Helvetica", 9))
        self.create_text(x1 - 4, y0 + 4, text="ホーム", anchor="ne", fill=TEXT, font=("Helvetica", 9))
        self.create_text(x0 + 4, y0 + 4, text="X+ →  Y+ ↑", anchor="nw", fill=TEXT, font=("Helvetica", 9))

        # Z のバー
        zx = self._zbar_x()
        self.create_rectangle(zx, self._z_to_py(0), zx + 14, self._z_to_py(-tz), fill=AREA, outline=TEXT)
        for z in range(0, int(tz) + 1, 25):
            py = self._z_to_py(-z)
            self.create_line(zx + 14, py, zx + 18, py, fill=TEXT)
            self.create_text(zx + 20, py, text=f"{-z}", anchor="w", fill=TEXT, font=("Helvetica", 8))
        self.create_text(zx + 7, self._z_to_py(0) - 2, text="Z", anchor="s", fill=TEXT, font=("Helvetica", 9))

        # 登録位置
        for i, p in enumerate(self.points):
            px, py = self.xy_to_px(p.x, p.y)
            color = SELECTED if i == self.selected else POINT
            r = 4
            self.create_oval(px - r, py - r, px + r, py + r, fill=color, outline="")
            self.create_text(px + 6, py - 6, text=p.name, anchor="sw", fill=color, font=("Helvetica", 9))

        self._draw_dynamic()

    def _draw_dynamic(self) -> None:
        self.delete("dynamic")
        tx, ty, _ = self.travel
        zx = self._zbar_x()

        # 移動先(入力欄の値)
        x, y, z = self.target
        if x is not None or y is not None:
            cx = x if x is not None else (self.current[0] if self.current else None)
            cy = y if y is not None else (self.current[1] if self.current else None)
            if cx is not None and cy is not None:
                px, py = self.xy_to_px(cx, cy)
                self.create_oval(px - 7, py - 7, px + 7, py + 7, outline=TARGET, width=2, dash=(3, 2),
                                 tags="dynamic")
        if z is not None:
            py = self._z_to_py(z)
            self.create_line(zx - 4, py, zx + 18, py, fill=TARGET, width=2, dash=(3, 2), tags="dynamic")

        # 現在位置
        if self.current:
            cx, cy, cz = self.current
            px, py = self.xy_to_px(cx, cy)
            x0, y0 = self.xy_to_px(-tx, 0)
            x1, y1 = self.xy_to_px(0, -ty)
            self.create_line(px, y0, px, y1, fill=CURRENT, dash=(2, 3), tags="dynamic")
            self.create_line(x0, py, x1, py, fill=CURRENT, dash=(2, 3), tags="dynamic")
            self.create_oval(px - 6, py - 6, px + 6, py + 6, fill=CURRENT, outline="white", width=2,
                             tags="dynamic")
            zpy = self._z_to_py(cz)
            self.create_rectangle(zx, zpy - 3, zx + 14, zpy + 3, fill=CURRENT, outline="", tags="dynamic")

        # お知らせ(図全体を薄く覆って、中央に出す)
        if self.message:
            x0, y0 = self.xy_to_px(-tx, 0)
            x1, y1 = self.xy_to_px(0, -ty)
            self.create_rectangle(x0, y0, x1, y1, fill="white", stipple="gray50", outline="", tags="dynamic")
            self.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=self.message, justify="center",
                             fill=CURRENT, font=("Helvetica", 22, "bold"), tags="dynamic")

    def _clicked(self, event: tk.Event) -> None:
        x, y = self.px_to_xy(event.x, event.y)
        tx, ty, _ = self.travel
        if -tx <= x <= 0 and -ty <= y <= 0 and self.on_click:
            self.on_click(round(x, 1), round(y, 1))
