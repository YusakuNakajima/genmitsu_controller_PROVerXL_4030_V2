"""XYZ ステージとして使う例:ホーミングしてから、XY の格子点を順に回り、各点で止まる。

    python scripts/stage_demo.py [ポート]

座標は機械座標(ホーミング位置の角が 0、そこから - 方向)。
各点で measure() を呼ぶので、測定や撮影の処理に書き換えて使う。
"""

import sys
import time

from genmitsu import Grbl

port = sys.argv[1] if len(sys.argv) > 1 else None

# 回る範囲(機械座標、mm)
X_POINTS = [-50, -100, -150]
Y_POINTS = [-50, -100]
Z_HEIGHT = -10
FEED = 2000  # mm/分


def measure(cnc: Grbl, pos: list[float]) -> None:
    """各点で行う処理。ここを書き換える。"""
    print(f"  到着 MPos: {pos}")
    time.sleep(0.5)


if input("機械が動きます。周りの安全を確認したら yes と入力: ").strip() != "yes":
    sys.exit("中止")

with Grbl(port) as cnc:
    if cnc.status()["state"].startswith("Alarm"):
        print("ホーミング中...")
        cnc.home()

    cnc.move_to(z=Z_HEIGHT, feed=1000)
    for y in Y_POINTS:
        for x in X_POINTS:
            print(f"→ X{x} Y{y}")
            pos = cnc.move_to(x=x, y=y, feed=FEED)
            measure(cnc, pos)

    print("ホーミング位置の近くへ戻る")
    cnc.move_to(z=-3, feed=1000)
    cnc.move_to(x=-3, y=-3, feed=FEED)
    print("完了")
