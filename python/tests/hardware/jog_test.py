"""動作テスト:ホーミングしてから、X / Y を 10mm ずつ往復し、Z を 5mm 下げて戻す。

    python tests/hardware/jog_test.py [ポート]

機械が動くので、ビットとワークが当たらないことを確認してから実行すること。
"""

import sys

from genmitsu import Grbl

port = sys.argv[1] if len(sys.argv) > 1 else None

if input("機械が動きます。周りの安全を確認したら yes と入力: ").strip() != "yes":
    sys.exit("中止")

with Grbl(port) as cnc:
    st = cnc.status()
    print(f"状態: {st['state']}")
    if st["state"].startswith("Alarm"):
        print("ホーミング中...")
        cnc.home()

    # $23=0 なのでホーミング直後は各軸とも + 側の端にいる。内側(- 方向)へ動かしてから戻す
    for dx, dy, dz in [(-10, 0, 0), (10, 0, 0), (0, -10, 0), (0, 10, 0), (0, 0, -5), (0, 0, 5)]:
        cnc.jog(x=dx or None, y=dy or None, z=dz or None, feed=1000)
        st = cnc.wait_idle()
        print(f"MPos: {st['MPos']}")
    print("完了")
