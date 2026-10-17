"""対話ターミナル。入力した G-code / $ コマンドを送って応答を表示する。

    python scripts/terminal.py [ポート]

特殊な入力:
    ?        ステータス
    !        フィードホールド
    ~        再開
    reset    ソフトリセット(Ctrl-X)
    quit     終了
"""

import sys

from genmitsu import CYCLE_START, FEED_HOLD, SOFT_RESET, Grbl, GrblError

port = sys.argv[1] if len(sys.argv) > 1 else None

with Grbl(port) as cnc:
    print(f"{cnc.port} に接続。quit で終了")
    while True:
        try:
            line = input("grbl> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        try:
            if line == "quit":
                break
            elif line == "?":
                print(cnc.status())
            elif line == "!":
                cnc.realtime(FEED_HOLD)
            elif line == "~":
                cnc.realtime(CYCLE_START)
            elif line == "reset":
                cnc.realtime(SOFT_RESET)
            else:
                for reply in cnc.send(line, timeout=120):
                    print(reply)
                print("ok")
        except (GrblError, TimeoutError) as e:
            print(f"!! {e}")
