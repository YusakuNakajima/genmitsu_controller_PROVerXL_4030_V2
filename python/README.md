# genmitsu(開発者向け)

Genmitsu PROVerXL 4030 V2(GRBL 1.1h)を XYZ ステージとして制御する Python パッケージ。GUI の使い方は [../PYTHON_GUIDE.md](../PYTHON_GUIDE.md) を参照。

## フォルダ構成

```text
python/
  pyproject.toml          パッケージの定義
  genmitsu/               ライブラリ(import して使う)
    grbl.py                 GRBL との通信・移動(Grbl クラス)
    gcode.py                G-code の解析(範囲計算、コメント・スピンドル指令の除去)
    points.py               登録位置(Point)の読み書き
    worker.py               通信を別スレッドで行う(StageWorker)
    stage_map.py            機械全体での位置の図(tkinter の Canvas)
    gui.py                  GUI(StageApp)
  scripts/                実行用(PYTHON_GUIDE.md の「その他のスクリプト」)
  tests/                  自動テスト(pytest、機械不要)
    hardware/               実機テスト(手で実行する。pytest は集めない)
```

## セットアップ

```sh
uv venv --python 3.12 .venv      # tkinter が入った Python を使う
source .venv/bin/activate
uv pip install -e ".[dev]"
```

## ライブラリとして使う

```python
from genmitsu import Grbl

with Grbl() as cnc:                                # ポートは自動検出(CH340)
    cnc.home()                                     # $H
    pos = cnc.move_to(x=-100, y=-50, feed=2000)    # 機械座標で絶対移動して、止まるまで待つ
    pos = cnc.move_to(z=-10)                       # feed を省略すると早送り(G0)
    print(cnc.position())                          # [X, Y, Z]
```

### Grbl の主なメソッド([genmitsu/grbl.py](genmitsu/grbl.py))

| メソッド | 内容 |
|---|---|
| `move_to(x, y, z, feed)` | 機械座標で絶対移動(`G53`)して、止まるまで待つ。範囲外なら送る前に `ValueError` |
| `position()` | 現在の機械座標 |
| `home()` / `unlock()` | `$H` / `$X` |
| `jog(x, y, z, feed)` | `$J=` で相対ジョグ。ソフトリミットを超えると `error:15` |
| `send(line)` | 1 行送って `ok` まで待つ。`error:N` / `ALARM:N` なら `GrblError` |
| `status()` | `?` で状態を取得して辞書で返す |
| `wait_idle()` | `Idle` になるまで待つ。Alarm になったら `GrblError` |
| `settings()` / `travel()` / `work_offset()` | `$$` の設定 / 各軸の可動範囲 / G54 のオフセット |
| `stream_file(path)` | G-code ファイルを 1 行ずつ送る(send-response 方式)。既定で `M3` / `M4` を取り除く |
| `stop()` | フィードホールドしてからソフトリセット |
| `on_line` / `on_status` | 受信した行 / 状態を受け取るフック(GUI が使う) |

### 巡回して、各点で測定する

GUI で登録した位置(`~/.genmitsu/stage_points.json`)を、スクリプトから回って測定する例。点ごとの速度・秒数が「既定」(`None`)なら、ここで決めた値を使う。

```python
import time
from genmitsu import Grbl
from genmitsu.points import DEFAULT_POINTS_PATH, load_points

with Grbl() as cnc:
    cnc.home()
    for p in load_points(DEFAULT_POINTS_PATH):
        cnc.move_to(p.x, p.y, p.z, feed=p.feed or 2000)
        print(p.name, cnc.position())   # ここで測定・撮影する
        time.sleep(p.dwell if p.dwell is not None else 1.0)
```

格子点を回る例は [scripts/stage_demo.py](scripts/stage_demo.py) にある。GUI の巡回は `StageWorker.tour()` が行っていて、各点に着いたときの処理を `on_arrive` で渡せる。ただし `StageWorker` は GUI 用で、接続や処理が非同期に進み、結果は `events` キューに届く。スクリプトなら上のように `Grbl` を直接使うほうが簡単。

## 設計

- **シリアルポートを読むのはワーカースレッドだけ**。GUI は `StageWorker.submit()` で処理を頼み、結果は `events` キューで受け取る(`root.after` で 50ms ごとに取り出す)。GUI が固まらない
- 処理していない間、ワーカーは 0.2 秒ごとに状態を問い合わせる。`move_to()` が止まるのを待っている間も、`on_status` フックで位置が GUI に届く
- 停止・一時停止・再開はリアルタイムコマンド(1 バイト)なので、GUI のスレッドから直接送る。停止は、待ち行列を捨てる → ジョグ取り消し → フィードホールド → 0.3 秒後にソフトリセット、の順
- ホーミング(`$H`)の間はワーカーが応答待ちで止まるので、状態が届かない。GUI は「ホーミング中…」と出す
- GUI は、ホーミングが終わるまで現在位置を描かない。Alarm になったらまた「ホーミングしてください」に戻る
- ウィンドウは伸縮できる。起動時は画面に収まる大きさで開く。左側は縦が足りないときだけスクロールバーを出す(`ScrollableFrame`)。右側は `ttk.PanedWindow` で図・登録位置・ログを分け、図(`StageMap.fit()`)は枠に合わせて縦横比を保ったまま拡大・縮小する

## テスト

```sh
pytest                                # 自動テスト(機械は不要)
python tests/hardware/jog_test.py     # 実機テスト。ホーミングして X / Y を 10mm、Z を 5mm 往復させる
```

| ファイル | 内容 |
|---|---|
| test_grbl.py | 偽のシリアルポートで、送受信・エラー・範囲チェック・スピンドル指令の除去 |
| test_gcode.py | G-code の範囲計算とコメント・スピンドル指令の除去 |
| test_points.py | 登録位置の保存・読み込み、入力欄の検証 |
| test_worker.py | 偽の Grbl で、処理の順番・エラーの報告・巡回(点ごとの速度と秒数)・停止 |
| test_stage_map.py | 図の座標変換、クリック、枠の大きさに合わせた拡大・縮小 |
| test_gui.py | ホーミング前後の表示の切り替え(画面がない環境ではスキップ) |

ライブラリを変えたら `pytest` を通す。動きに関わる変更なら、実機テストも実行する。

## 実機での確認記録

確認した環境(2026-10-17):

| PC | Python | 結果 |
|---|---|---|
| macOS(Apple Silicon) | 3.12.13(uv) | 下の記録のとおり。`pytest` は 47 件すべて通った |
| Windows 11 Pro(ASUS ExpertBook B1403CVA) | 3.11 | ポート(`COM3`)は自動で見つかった。GUI の操作を一通り試して動いた |

どちらも pyserial 3.5、GRBL 1.1h。

### tests/hardware/jog_test.py

ホーミングの後は MPos (−3, −3, −3) にいて、そこから − 方向に往復して元の位置に戻った。

```text
状態: Alarm
ホーミング中...
MPos: [-13.0, -3.0, -3.0]
MPos: [-3.0, -3.0, -3.0]
MPos: [-3.0, -13.0, -3.0]
MPos: [-3.0, -3.0, -3.0]
MPos: [-3.0, -3.0, -8.0]
MPos: [-3.0, -3.0, -3.0]
完了
```

### scripts/stage_demo.py

6 点すべてで、指定した座標に着いた。

```text
→ X-50 Y-50
  到着 MPos: [-50.0, -50.0, -10.0]
→ X-100 Y-50
  到着 MPos: [-100.0, -50.0, -10.0]
→ X-150 Y-50
  到着 MPos: [-150.0, -50.0, -10.0]
→ X-50 Y-100
  到着 MPos: [-50.0, -100.0, -10.0]
→ X-100 Y-100
  到着 MPos: [-100.0, -100.0, -10.0]
→ X-150 Y-100
  到着 MPos: [-150.0, -100.0, -10.0]
```

### GUI

登録した 5 点の巡回が最後まで終わり、図の現在位置が実際の位置(P5)と一致した。点ごとに指定した速度(P5 だけ 100 mm/分)も効いた([PYTHON_GUIDE.md](../PYTHON_GUIDE.md) のスクリーンショット)。

### Windows

- ポートは `COM3` として自動で見つかった
- GUI の操作(接続、ホーミング、ジョグ、移動、登録、巡回)を一通り試して動いた
- 最初の版では画面の縦が足りずに見切れていた。ウィンドウを伸縮できるようにして直した(縦が足りないときは左側がスクロールし、図は枠の大きさに合わせて拡大・縮小する)。直した版は Windows ではまだ試していない

### 未確認

- `scripts/run_gcode.py` での G-code の送信
