"""XYZ ステージ操作用の GUI(tkinter)。

    python scripts/gui.py

座標はすべて機械座標(ホーミング位置の角が 0、そこから - 方向)。
キー操作:← → で X、↑ ↓ で Y、PageUp / PageDown で Z をジョグ。Esc で停止。
"""

from __future__ import annotations

import queue
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from serial.tools import list_ports

from .grbl import find_port
from .points import DEFAULT_POINTS_PATH, Point, load_points, point_from_fields, save_points
from .stage_map import StageMap
from .worker import StageWorker, fmt_pos

STEPS = [0.1, 1, 10, 50]
STATE_COLORS = {"Idle": "#2e7d32", "Run": "#1565c0", "Jog": "#1565c0", "Home": "#6a1b9a",
                "Hold": "#ef6c00", "Alarm": "#c62828", "Door": "#ef6c00", "未接続": "#616161"}
MONO = ("Menlo", 20)


class StageApp:
    def __init__(self, root: tk.Tk, points_path: Path = DEFAULT_POINTS_PATH):
        self.root = root
        self.points_path = Path(points_path)
        self.events: queue.Queue = queue.Queue()
        self.worker = StageWorker(self.events)
        self.state = "未接続"
        self.homed = False  # ホーミングが終わって、機械座標が正しい
        self.busy_label = ""  # ワーカーが実行中の処理
        self.mpos: list[float] | None = None
        try:
            self.points = load_points(self.points_path)
        except (OSError, ValueError, KeyError) as e:
            self.points = []
            messagebox.showwarning("登録位置", f"{self.points_path} を読めなかった: {e}")
        self.motion_widgets: list[tk.Widget] = []

        root.title("Genmitsu ステージ")
        root.minsize(980, 760)
        self._build()
        self._refresh_ports()
        self._refresh_points()
        self._set_connected(False)

        root.bind_all("<Escape>", lambda e: self.stop())
        for key, (dx, dy, dz) in {"<Left>": (-1, 0, 0), "<Right>": (1, 0, 0), "<Up>": (0, 1, 0),
                                  "<Down>": (0, -1, 0), "<Prior>": (0, 0, 1), "<Next>": (0, 0, -1)}.items():
            root.bind_all(key, lambda e, d=(dx, dy, dz): self._on_jog_key(e, *d))
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.after(50, self._poll_events)

    # ---- 画面 ----

    def _build(self) -> None:
        pad = {"padx": 6, "pady": 4}
        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad)
        ttk.Label(top, text="ポート").pack(side="left")
        self.port_var = tk.StringVar()
        self.port_box = ttk.Combobox(top, textvariable=self.port_var, width=28)
        self.port_box.pack(side="left", padx=4)
        ttk.Button(top, text="更新", command=self._refresh_ports).pack(side="left")
        self.connect_btn = ttk.Button(top, text="接続", command=self._toggle_connect)
        self.connect_btn.pack(side="left", padx=8)
        self.busy_var = tk.StringVar()
        ttk.Label(top, textvariable=self.busy_var, foreground="#1565c0").pack(side="left", padx=8)

        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True, **pad)
        left = ttk.Frame(body)
        left.pack(side="left", fill="y")
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))

        self._build_status(left)
        self._build_controls(left)
        self._build_jog(left)
        self._build_goto(left)
        self._build_map(right)
        self._build_points(right)
        self._build_log(right)

    def _build_status(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text="状態(機械座標 mm)")
        box.pack(fill="x", pady=4)
        self.state_label = tk.Label(box, text="未接続", font=("Helvetica", 18, "bold"),
                                    fg="white", bg=STATE_COLORS["未接続"], width=14)
        self.state_label.grid(row=0, column=0, rowspan=3, padx=8, pady=6, sticky="ns")
        self.pos_vars = []
        for i, axis in enumerate("XYZ"):
            ttk.Label(box, text=axis, font=MONO).grid(row=i, column=1, padx=(8, 2))
            var = tk.StringVar(value="—")
            ttk.Label(box, textvariable=var, font=MONO, width=10, anchor="e").grid(row=i, column=2, padx=(0, 8))
            self.pos_vars.append(var)
        self.hint_var = tk.StringVar()
        ttk.Label(box, textvariable=self.hint_var, foreground="#c62828",
                  font=("Helvetica", 13, "bold")).grid(row=3, column=0, columnspan=3, pady=(0, 6))

    def _build_controls(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text="操作")
        box.pack(fill="x", pady=4)
        for i, (text, cmd) in enumerate([("ホーミング", self.worker.home), ("アンロック", self.worker.unlock),
                                         ("一時停止", self.worker.hold), ("再開", self.worker.resume)]):
            b = ttk.Button(box, text=text, command=cmd)
            b.grid(row=0, column=i, padx=3, pady=4)
            self.motion_widgets.append(b)
        # macOS ではボタンの背景色が変えられないので、ラベルをボタンとして使う
        stop = tk.Label(box, text="停止 (Esc)", font=("Helvetica", 16, "bold"), fg="white", bg="#c62828",
                        padx=10, pady=8, cursor="hand2")
        stop.grid(row=1, column=0, columnspan=4, sticky="ew", padx=3, pady=(2, 6))
        stop.bind("<Button-1>", lambda e: self.stop())

    def _build_jog(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text="ジョグ(← → X / ↑ ↓ Y / PageUp PageDown Z)")
        box.pack(fill="x", pady=4)
        pad = ttk.Frame(box)
        pad.grid(row=0, column=0, rowspan=2, padx=6, pady=4)
        for text, r, c, d in [("Y+", 0, 1, (0, 1, 0)), ("X−", 1, 0, (-1, 0, 0)), ("X+", 1, 2, (1, 0, 0)),
                              ("Y−", 2, 1, (0, -1, 0)), ("Z+", 0, 4, (0, 0, 1)), ("Z−", 2, 4, (0, 0, -1))]:
            b = ttk.Button(pad, text=text, width=4, command=lambda d=d: self.jog(*d))
            b.grid(row=r, column=c, padx=2, pady=2)
            self.motion_widgets.append(b)
        ttk.Frame(pad, width=16).grid(row=1, column=3)

        opts = ttk.Frame(box)
        opts.grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(opts, text="移動量 mm").grid(row=0, column=0, sticky="w")
        self.step_var = tk.DoubleVar(value=1)
        for i, s in enumerate(STEPS):
            ttk.Radiobutton(opts, text=f"{s:g}", value=s, variable=self.step_var).grid(row=1, column=i, sticky="w")
        ttk.Label(opts, text="速度 mm/分").grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.jog_feed_var = tk.StringVar(value="1000")
        ttk.Spinbox(opts, from_=10, to=5000, increment=100, textvariable=self.jog_feed_var,
                    width=7).grid(row=2, column=2, columnspan=2, sticky="w", pady=(6, 0))

    def _build_goto(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text="座標を指定して移動(機械座標)")
        box.pack(fill="x", pady=4)
        self.goto_vars = []
        for i, axis in enumerate("XYZ"):
            ttk.Label(box, text=axis).grid(row=0, column=i * 2, padx=(6, 2), pady=4)
            var = tk.StringVar()
            ttk.Entry(box, textvariable=var, width=9).grid(row=0, column=i * 2 + 1, pady=4)
            self.goto_vars.append(var)
        ttk.Label(box, text="速度 mm/分").grid(row=1, column=0, columnspan=2, sticky="w", padx=6)
        self.feed_var = tk.StringVar(value="2000")
        ttk.Entry(box, textvariable=self.feed_var, width=9).grid(row=1, column=2, columnspan=2, sticky="w")
        self.retract_var = tk.BooleanVar(value=False)  # 既定は XYZ を同時に動かす
        ttk.Checkbutton(box, text="移動前に Z を上げる", variable=self.retract_var).grid(
            row=2, column=0, columnspan=3, sticky="w", padx=6)
        self.z_safe_var = tk.StringVar(value="-5")
        ttk.Label(box, text="Z 退避高さ").grid(row=2, column=3, columnspan=2, sticky="e")
        ttk.Entry(box, textvariable=self.z_safe_var, width=9).grid(row=2, column=5)
        b1 = ttk.Button(box, text="現在位置を入れる", command=self._fill_current)
        b1.grid(row=3, column=0, columnspan=3, sticky="w", padx=6, pady=6)
        b2 = ttk.Button(box, text="移動", command=self.goto)
        b2.grid(row=3, column=3, columnspan=3, sticky="e", padx=6, pady=6)
        self.motion_widgets += [b1, b2]

    def _build_map(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text="機械全体での位置(上から見た図。クリックで移動欄に XY を入れる)")
        box.pack(fill="x", pady=4)
        self.map = StageMap(box, on_click=self._map_clicked)
        self.map.pack(padx=4, pady=4)
        legend = ttk.Frame(box)
        legend.pack(fill="x", padx=6, pady=(0, 4))
        for text, color in [("● 現在位置", "#c62828"), ("◌ 移動先", "#2e7d32"), ("● 登録位置", "#1565c0"),
                            ("● 選択中", "#ef6c00")]:
            tk.Label(legend, text=text, fg=color).pack(side="left", padx=4)
        for var in self.goto_vars:
            var.trace_add("write", lambda *a: self._update_map_target())

    def _map_clicked(self, x: float, y: float) -> None:
        self.goto_vars[0].set(f"{x:.1f}")
        self.goto_vars[1].set(f"{y:.1f}")

    def _update_map_target(self) -> None:
        values = []
        for var in self.goto_vars:
            try:
                values.append(float(var.get()))
            except ValueError:
                values.append(None)
        self.map.set_target(*values)

    def _build_points(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text="登録位置(ダブルクリックで移動欄に入れる)")
        box.pack(fill="both", expand=True, pady=4)
        cols = ("name", "x", "y", "z", "feed", "dwell")
        self.tree = ttk.Treeview(box, columns=cols, show="headings", height=6, selectmode="browse")
        for c, text, w in zip(cols, ("名前", "X", "Y", "Z", "速度", "秒数"), (120, 72, 72, 72, 64, 48)):
            self.tree.heading(c, text=text)
            self.tree.column(c, width=w, anchor="w" if c == "name" else "e")
        self.tree.grid(row=0, column=0, columnspan=4, sticky="nsew", padx=4, pady=4)
        sb = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        sb.grid(row=0, column=4, sticky="ns", pady=4)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<Double-1>", lambda e: self._fill_from_selected())
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.map.set_points(self.points, self._selected_index()))
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)

        buttons = [("現在位置を登録", self._add_current, True), ("この位置へ移動", self._goto_selected, True),
                   ("編集…", self._edit_selected, False), ("削除", self._delete_selected, False),
                   ("↑", lambda: self._move_selected(-1), False), ("↓", lambda: self._move_selected(1), False),
                   ("読み込み", self._import_points, False), ("書き出し", self._export_points, False)]
        for i, (text, cmd, motion) in enumerate(buttons):
            b = ttk.Button(box, text=text, command=cmd)
            b.grid(row=1 + i // 4, column=i % 4, sticky="ew", padx=2, pady=2)
            if motion:
                self.motion_widgets.append(b)

        tour = ttk.Frame(box)
        tour.grid(row=3, column=0, columnspan=4, sticky="w", padx=4, pady=6)
        ttk.Label(tour, text="既定の速度 mm/分").pack(side="left")
        self.tour_feed_var = tk.StringVar(value="2000")
        ttk.Entry(tour, textvariable=self.tour_feed_var, width=6).pack(side="left", padx=4)
        ttk.Label(tour, text="既定の秒数").pack(side="left", padx=(8, 0))
        self.dwell_var = tk.StringVar(value="1.0")
        ttk.Entry(tour, textvariable=self.dwell_var, width=5).pack(side="left", padx=4)
        b = ttk.Button(tour, text="上から順に巡回", command=self.tour)
        b.pack(side="left", padx=8)
        self.motion_widgets.append(b)

    def _build_log(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text="ログ")
        box.pack(fill="both", expand=True, pady=4)
        self.log_text = tk.Text(box, height=6, wrap="word", state="disabled", font=("Menlo", 11))
        self.log_text.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        sb = ttk.Scrollbar(box, orient="vertical", command=self.log_text.yview)
        sb.pack(side="left", fill="y", pady=4)
        self.log_text.configure(yscrollcommand=sb.set)
        self.log_text.tag_configure("error", foreground="#c62828")
        self.log_text.tag_configure("grbl", foreground="#6a1b9a")

    # ---- 表示の更新 ----

    def log(self, text: str, tag: str | None = None) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n", tag or ())
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_connected(self, connected: bool) -> None:
        self.connect_btn.configure(text="切断" if connected else "接続")
        for w in self.motion_widgets:
            w.state(["!disabled"] if connected else ["disabled"])
        self.homed = False  # 接続するとリセットされるので、どちらにしてもホーミングが要る
        if not connected:
            self._set_state("未接続")
            for var in self.pos_vars:
                var.set("—")
            self.mpos = None
            self.busy_label = ""
            self.busy_var.set("")
        self._update_homing_hint()

    def _update_homing_hint(self) -> None:
        """ホーミングが終わるまでは、図に現在位置を出さずに「ホーミングしてください」と出す。"""
        if not self.worker.connected:
            message, hint = "接続してください", ""
        elif self.homed:
            message, hint = None, ""
        elif self.busy_label == "ホーミング" or self.state.startswith("Home"):
            # ホーミング中はワーカーが $H の応答を待っていて、状態が届かない
            message, hint = "ホーミング中…", "ホーミング中…"
        elif self.state.split(":")[0] in ("Idle", "Jog", "Run", "Hold"):
            # アンロック($X)で動けるが、原点は分かっていない
            message, hint = "原点が未確認です\nホーミングしてください", "原点が未確認(ホーミングしてください)"
        else:  # Alarm、接続した直後
            message, hint = "ホーミングしてください", "ホーミングしてください"
        self.map.set_message(message)
        self.map.set_current(self.mpos if self.homed else None)
        self.hint_var.set(hint)

    def _set_state(self, state: str) -> None:
        self.state = state
        color = STATE_COLORS.get(state.split(":")[0], "#616161")
        self.state_label.configure(text=state, bg=color)

    def _poll_events(self) -> None:
        try:
            while True:
                kind, value = self.events.get_nowait()
                self._handle_event(kind, value)
        except queue.Empty:
            pass
        self.root.after(50, self._poll_events)

    def _handle_event(self, kind: str, value) -> None:
        if kind == "status":
            self._set_state(value["state"])
            if self.state.startswith("Alarm"):
                self.homed = False  # 停止やリミットで位置が失われた
            if "MPos" in value:
                self.mpos = value["MPos"]
                for var, v in zip(self.pos_vars, self.mpos):
                    var.set(f"{v:.3f}")
            self._update_homing_hint()
        elif kind == "homed":
            self.homed = True
            self.log("ホーミングが終わった")
            self._update_homing_hint()
        elif kind == "connected":
            port, banner = value
            self._set_connected(True)
            self.log(f"{port} に接続した: {banner}")
        elif kind == "disconnected":
            self._set_connected(False)
            self.log("切断した")
        elif kind == "line":
            self.log(f"GRBL: {value}", "error" if value.startswith(("ALARM", "error")) else "grbl")
        elif kind == "log":
            self.log(value)
        elif kind == "error":
            self.log(value, "error")
        elif kind == "busy":
            self.busy_label = value
            self.busy_var.set(f"{value}中…")
            self._update_homing_hint()
        elif kind == "idle":
            self.busy_label = ""
            self.busy_var.set("")
            self._update_homing_hint()
        elif kind == "travel":
            self.map.set_travel(value)
            self.log("可動範囲: " + " / ".join(f"{a} {v:g}mm" for a, v in zip("XYZ", value)))
        elif kind == "arrived":
            items = self.tree.get_children()
            if value < len(items):
                self.tree.selection_set(items[value])
                self.tree.see(items[value])

    # ---- 接続 ----

    def _refresh_ports(self) -> None:
        ports = [p.device for p in list_ports.comports()]
        self.port_box["values"] = ports
        if not self.port_var.get():
            try:
                self.port_var.set(find_port())
            except RuntimeError:
                pass

    def _toggle_connect(self) -> None:
        if self.worker.connected:
            self.worker.disconnect()
        else:
            self.log(f"{self.port_var.get() or '(自動検出)'} に接続中…")
            self.worker.connect(self.port_var.get() or None)

    def _on_close(self) -> None:
        self.worker.disconnect()
        self.root.destroy()

    # ---- 動かす ----

    def _ready_to_move(self, quiet: bool = False) -> bool:
        if not self.worker.connected:
            return False
        if self.state.startswith("Alarm"):
            if not quiet:
                self.log("Alarm 状態。先にホーミングすること", "error")
            return False
        return True

    def jog(self, dx: int, dy: int, dz: int) -> None:
        # 前の動きが終わるまで次を受け付けない(キーの押しっぱなしで動きが溜まらないように)
        if not self._ready_to_move() or not self.worker.idle or self.state != "Idle":
            return
        feed = self._float(self.jog_feed_var, "ジョグ速度")
        if feed is None:
            return
        step = self.step_var.get()
        self.worker.jog(x=dx * step, y=dy * step, z=dz * step, feed=feed)

    def _on_jog_key(self, event: tk.Event, dx: int, dy: int, dz: int) -> None:
        # 入力欄や一覧でのキー操作は邪魔しない
        if isinstance(event.widget, (tk.Entry, ttk.Entry, ttk.Spinbox, ttk.Combobox, ttk.Treeview, tk.Text)):
            return
        self.jog(dx, dy, dz)

    def goto(self) -> None:
        if not self._ready_to_move():
            return
        target = []
        for axis, var in zip("XYZ", self.goto_vars):
            text = var.get().strip()
            if not text:
                target.append(None)
                continue
            v = self._float(var, axis)
            if v is None:
                return
            target.append(v)
        if target == [None, None, None]:
            self.log("移動先が入っていない", "error")
            return
        feed = self._float(self.feed_var, "速度")
        z_safe = self._z_safe()
        if feed is None or z_safe is False:
            return
        self.worker.move(*target, feed=feed, z_safe=z_safe)

    def tour(self) -> None:
        if not self._ready_to_move():
            return
        if not self.points:
            self.log("登録位置がない", "error")
            return
        feed = self._float(self.tour_feed_var, "既定の速度")
        dwell = self._float(self.dwell_var, "既定の秒数")
        z_safe = self._z_safe()
        if feed is None or dwell is None or z_safe is False:
            return
        self.log(f"巡回を始める({len(self.points)} 点)。止めるときは Esc")
        self.worker.tour(self.points, feed=feed, dwell=dwell, z_safe=z_safe)

    def stop(self) -> None:
        if self.worker.connected:
            self.worker.stop()

    def _z_safe(self) -> float | None | bool:
        """Z 退避高さ。使わなければ None、入力が不正なら False。"""
        if not self.retract_var.get():
            return None
        v = self._float(self.z_safe_var, "Z 退避高さ")
        return False if v is None else v

    def _float(self, var: tk.Variable, name: str) -> float | None:
        try:
            return float(var.get())
        except (ValueError, tk.TclError):
            self.log(f"{name} が数値ではない: {var.get()!r}", "error")
            return None

    def _fill_current(self) -> None:
        if self.mpos:
            for var, v in zip(self.goto_vars, self.mpos):
                var.set(f"{v:.3f}")

    # ---- 登録位置 ----

    def _refresh_points(self, select: int | None = None) -> None:
        self.tree.delete(*self.tree.get_children())
        for p in self.points:
            self.tree.insert("", "end", values=(
                p.name, f"{p.x:.3f}", f"{p.y:.3f}", f"{p.z:.3f}",
                "既定" if p.feed is None else f"{p.feed:g}", "既定" if p.dwell is None else f"{p.dwell:g}"))
        items = self.tree.get_children()
        if select is not None and 0 <= select < len(items):
            self.tree.selection_set(items[select])
            self.tree.see(items[select])
        self.map.set_points(self.points, self._selected_index())

    def _save(self) -> None:
        try:
            save_points(self.points_path, self.points)
        except OSError as e:
            self.log(f"登録位置を保存できない: {e}", "error")

    def _selected_index(self) -> int | None:
        sel = self.tree.selection()
        return self.tree.index(sel[0]) if sel else None

    def _add_current(self) -> None:
        if not self.mpos:
            return
        name = simpledialog.askstring("位置を登録", "名前", initialvalue=f"P{len(self.points) + 1}",
                                      parent=self.root)
        if not name:
            return
        self.points.append(Point(name, *self.mpos))
        self._save()
        self._refresh_points(select=len(self.points) - 1)
        self.log(f"登録: {name} {fmt_pos(self.mpos)}")

    def _fill_from_selected(self) -> None:
        i = self._selected_index()
        if i is not None:
            p = self.points[i]
            for var, v in zip(self.goto_vars, (p.x, p.y, p.z)):
                var.set(f"{v:.3f}")

    def _goto_selected(self) -> None:
        i = self._selected_index()
        if i is None or not self._ready_to_move():
            return
        p = self.points[i]
        feed = p.feed if p.feed is not None else self._float(self.feed_var, "速度")
        z_safe = self._z_safe()
        if feed is None or z_safe is False:
            return
        self.log(f"{p.name} へ移動")
        self.worker.move(p.x, p.y, p.z, feed=feed, z_safe=z_safe)

    def _edit_selected(self) -> None:
        i = self._selected_index()
        if i is None:
            return
        edited = PointDialog(self.root, self.points[i]).result
        if edited:
            self.points[i] = edited
            self._save()
            self._refresh_points(select=i)

    def _delete_selected(self) -> None:
        i = self._selected_index()
        if i is None:
            return
        if messagebox.askyesno("削除", f"{self.points[i].name} を削除する?", parent=self.root):
            del self.points[i]
            self._save()
            self._refresh_points(select=min(i, len(self.points) - 1))

    def _move_selected(self, delta: int) -> None:
        i = self._selected_index()
        if i is None or not 0 <= i + delta < len(self.points):
            return
        self.points[i], self.points[i + delta] = self.points[i + delta], self.points[i]
        self._save()
        self._refresh_points(select=i + delta)

    def _import_points(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")], parent=self.root)
        if not path:
            return
        try:
            self.points = load_points(path)
        except (OSError, ValueError, KeyError) as e:
            self.log(f"読み込めない: {e}", "error")
            return
        self._save()
        self._refresh_points()
        self.log(f"{path} から {len(self.points)} 点を読み込んだ")

    def _export_points(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")],
                                            parent=self.root)
        if path:
            save_points(path, self.points)
            self.log(f"{path} に書き出した")


class PointDialog(tk.Toplevel):
    """登録位置の名前・座標・速度・秒数を編集するダイアログ。OK なら result に新しい Point が入る。"""

    def __init__(self, parent: tk.Tk, point: Point):
        super().__init__(parent)
        self.title("登録位置を編集")
        self.transient(parent)
        self.resizable(False, False)
        self.result: Point | None = None
        fields = [("名前", "name", point.name), ("X", "x", f"{point.x:.3f}"), ("Y", "y", f"{point.y:.3f}"),
                  ("Z", "z", f"{point.z:.3f}"),
                  ("速度 mm/分", "feed", "" if point.feed is None else f"{point.feed:g}"),
                  ("止まる秒数", "dwell", "" if point.dwell is None else f"{point.dwell:g}")]
        self.vars: dict[str, tk.StringVar] = {}
        for r, (label, key, value) in enumerate(fields):
            ttk.Label(self, text=label).grid(row=r, column=0, sticky="w", padx=8, pady=3)
            var = tk.StringVar(value=value)
            entry = ttk.Entry(self, textvariable=var, width=14)
            entry.grid(row=r, column=1, padx=8, pady=3)
            if r == 0:
                entry.focus_set()
            self.vars[key] = var
        ttk.Label(self, text="速度・秒数は空欄なら、巡回の既定値を使う", foreground="#616161").grid(
            row=len(fields), column=0, columnspan=2, padx=8, pady=(4, 0))
        self.error_var = tk.StringVar()
        ttk.Label(self, textvariable=self.error_var, foreground="#c62828").grid(
            row=len(fields) + 1, column=0, columnspan=2, padx=8)
        buttons = ttk.Frame(self)
        buttons.grid(row=len(fields) + 2, column=0, columnspan=2, pady=8)
        ttk.Button(buttons, text="キャンセル", command=self.destroy).pack(side="left", padx=4)
        ttk.Button(buttons, text="OK", command=self._ok).pack(side="left", padx=4)
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())
        self.wait_visibility()
        self.grab_set()
        self.wait_window()

    def _ok(self) -> None:
        try:
            self.result = point_from_fields(**{k: v.get() for k, v in self.vars.items()})
        except ValueError as e:
            self.error_var.set(str(e))
            return
        self.destroy()


def main() -> None:
    root = tk.Tk()
    StageApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
