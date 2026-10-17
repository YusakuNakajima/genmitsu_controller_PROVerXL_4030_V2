"""接続確認。機械は動かさない(状態・ビルド情報・設定を読むだけ)。

    python scripts/info.py [ポート]
"""

import sys

from genmitsu import Grbl

port = sys.argv[1] if len(sys.argv) > 1 else None

with Grbl(port) as cnc:
    print(f"ポート: {cnc.port}")
    print(f"状態: {cnc.status()}")
    print("ビルド情報:", *cnc.send("$I"), sep="\n  ")
    s = cnc.settings()
    print(f"ソフトリミット $20={s.get('$20')} / ハードリミット $21={s.get('$21')} / ホーミング $22={s.get('$22')}")
    print(f"動ける範囲 X{s.get('$130')} Y{s.get('$131')} Z{s.get('$132')} mm")
