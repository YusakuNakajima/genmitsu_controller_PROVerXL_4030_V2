"""G-code ファイルを送って加工する。Ctrl-C で停止(フィードホールド → リセット)。

    python scripts/run_gcode.py ファイル.nc [ポート]

- ワーク原点(G54)は先に terminal.py などで設定しておく。EEPROM に保存されるので接続し直しても残る
- ポートを開くと GRBL がリセットされてホーミングの状態が消えるので、接続した後にホーミングする
- 送る前に、G-code の範囲 + G54 が機械の動ける範囲に収まるかを確かめる
"""

import sys

from genmitsu import Grbl, gcode_bounds

if len(sys.argv) < 2:
    sys.exit(__doc__)
path = sys.argv[1]
port = sys.argv[2] if len(sys.argv) > 2 else None

with open(path, encoding="utf-8", errors="replace") as f:
    lines = f.readlines()
bounds = gcode_bounds(lines)

with Grbl(port) as cnc:
    st = cnc.status()
    print(f"状態: {st['state']}")
    if st["state"].startswith("Alarm"):
        if input("ホーミングします(機械が動きます)。yes で開始: ").strip() != "yes":
            sys.exit("中止")
        cnc.home()
        st = cnc.wait_idle()
    if st["state"] != "Idle":
        sys.exit(f"Idle ではないので中止: {st['state']}")

    # 機械座標で動ける範囲は -$130..0(X)/ -$131..0(Y)/ -$132..0(Z)
    settings = cnc.settings()
    limits = {a: float(settings[k]) for a, k in (("X", "$130"), ("Y", "$131"), ("Z", "$132"))}
    g54 = dict(zip("XYZ", cnc.work_offset("G54")))

    print(f"G54(ワーク原点の機械座標): X{g54['X']:.3f} Y{g54['Y']:.3f} Z{g54['Z']:.3f}")
    ok = True
    for axis, (lo, hi) in bounds.items():
        m_lo, m_hi = lo + g54[axis], hi + g54[axis]
        inside = -limits[axis] <= m_lo and m_hi <= 0
        ok &= inside
        print(f"  {axis}: ワーク {lo:8.3f} 〜 {hi:8.3f} → 機械 {m_lo:8.3f} 〜 {m_hi:8.3f}  "
              f"{'OK' if inside else f'範囲外(動ける範囲 {-limits[axis]:.0f} 〜 0)'}")
    if not ok:
        sys.exit("動ける範囲を超えるので中止。ワーク原点(G54)を設定し直すこと")

    if input(f"{path} を送ります。yes で開始: ").strip() != "yes":
        sys.exit("中止")
    try:
        cnc.stream(lines)
        print("完了")
    except KeyboardInterrupt:
        print("\n停止します")
        cnc.stop()
