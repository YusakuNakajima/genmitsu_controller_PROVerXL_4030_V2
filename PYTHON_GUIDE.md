# Python から制御する

UGS を使わずに、Python(pyserial)から USB シリアル経由で GRBL にコマンドを送る。コードは [python/](python/) にある。

この機械は **XYZ ステージ** として使う(スピンドルは回さない)。

## フォルダ構成

| 場所 | 役割 | 機械が動くか |
|---|---|---|
| [python/genmitsu/](python/genmitsu/) | **ライブラリ**。`from genmitsu import Grbl` で使う | — |
| [python/scripts/](python/scripts/) | **実行用**。普段使うスクリプト | 動くものがある(下の表) |
| [python/tests/](python/tests/) | **自動テスト**(pytest)。シリアルポートを偽物に差し替えるので機械は不要 | 動かない |
| [python/tests/hardware/](python/tests/hardware/) | **実機テスト**。手で実行する。pytest は集めない | 動く |

## 準備

```sh
cd python
python3 -m venv .venv
source .venv/bin/activate        # Windows は .venv\Scripts\activate
pip install -e ".[dev]"          # genmitsu パッケージと pytest を入れる
```

以降のコマンドは、`python/` で venv を有効にした状態で実行する。

- **UGS は切断しておく**(ポートを使えるのは 1 つのソフトだけ)
- ポートは CH340(USB ベンダー ID `0x1A86`)を自動で探す。手動で指定するときは `/dev/cu.usbserial-XXXX`(Mac)や `COM3`(Windows)を引数に渡す
- **ポートを開くと GRBL はリセットされる**。ホーミングはやり直しになる。ワーク原点(G54)は EEPROM に保存されているので消えない

## 実行用スクリプト(scripts/)

| ファイル | 内容 | 機械が動くか |
|---|---|---|
| [info.py](python/scripts/info.py) | 接続確認(状態・バージョン・主な設定を表示) | 動かない |
| [terminal.py](python/scripts/terminal.py) | 対話ターミナル。G-code や `$` コマンドを 1 行ずつ送る | 送ったコマンドしだい |
| [stage_demo.py](python/scripts/stage_demo.py) | ステージとして使う例。XY の格子点を順に回り、各点で止まる | 動く |
| [run_gcode.py](python/scripts/run_gcode.py) | G-code ファイルを送る(スピンドルの指令は取り除く)。Ctrl-C で停止 | 動く |

```sh
python scripts/info.py
python scripts/stage_demo.py
```

## テスト(tests/)

```sh
pytest                                # 自動テスト。機械は不要(つながっていなくてよい)
python tests/hardware/jog_test.py     # 実機テスト。ホーミングして X / Y を 10mm、Z を 5mm 往復させる
```

ライブラリを変えたら `pytest` を通す。動きに関わる変更なら、実機テストも実行する。

## 自分のコードから使う

```python
from genmitsu import Grbl

with Grbl() as cnc:
    cnc.home()                                     # $H
    pos = cnc.move_to(x=-100, y=-50, feed=2000)    # 機械座標で絶対移動して、止まるまで待つ
    pos = cnc.move_to(z=-10)                       # feed を省略すると早送り(G0)
    print(cnc.position())                          # [X, Y, Z]
```

主なメソッド([python/genmitsu/grbl.py](python/genmitsu/grbl.py)):

| メソッド | 内容 |
|---|---|
| `send(line)` | 1 行送って `ok` まで待つ。`error:N` / `ALARM:N` なら `GrblError` |
| `status()` | `?` で状態を取得して辞書で返す |
| `wait_idle()` | `Idle` になるまで待つ |
| `home()` / `unlock()` | `$H` / `$X` |
| `move_to(x, y, z, feed)` | 機械座標で絶対移動(`G53`)して、止まるまで待つ。範囲外なら送る前に `ValueError` |
| `position()` | 現在の機械座標 |
| `jog(x, y, z, feed)` | `$J=` でジョグ。ソフトリミットを超えると `error:15` |
| `set_work_zero()` | `G10 L20 P1` で現在位置をワーク原点にする |
| `stream_file(path)` | G-code ファイルを 1 行ずつ送る。既定で `M3` / `M4`(スピンドル回転)を取り除く |
| `stop()` | フィードホールドしてからソフトリセット |

## この機械の座標について

- `$23=0` なので、ホーミングは **全軸とも + 側の端** で終わる(Z は一番上)。その後、`$27` の 3mm だけ戻る
- 機械座標(MPos)は 0 から − 方向に増えていく。動ける範囲は X −400〜0 / Y −300〜0 / Z −100〜0 くらい
- だから、ホーミングの後は **− 方向** に動かす。+ 方向に動かすとソフトリミットで `error:15` になる

## ステージとして使うときの注意

- **ジョグと通常の移動で、ソフトリミットにかかったときの動きが違う**
  - ジョグ(`$J=`)なら `error:15` で拒否されるだけ
  - G0 / G1 だと `ALARM:2` になり、ホーミングからやり直しになる
  - `move_to()` は、動く前に Python 側で範囲(端から 1mm 内側まで)を確かめる
- 座標は機械座標をそのまま使う。ホーミングすれば毎回同じ位置になるので、ワーク原点(G54)を設定しなくてよい
- `run_gcode.py` も使える。送る前に、G-code の範囲に G54 を足した値が動ける範囲に収まるかを確かめる。機械付属の `Test Code/*.tap` は木材を彫るための加工データで、ステージの確認には不要

## 補足

- `stream` は 1 行送って `ok` を待つ方式(send-response)。確実だが、短い線分が多い G-code では UGS より遅い
- 確認した環境(2026-10-17):Python 3.11.7、pyserial 3.5、GRBL 1.1h

## 実機での確認結果(2026-10-17)

`tests/hardware/jog_test.py` を実行した結果。ホーミングの後は MPos (−3, −3, −3) にいて、そこから − 方向に往復して元の位置に戻った。

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

`scripts/stage_demo.py`(`move_to()` で格子点を回る)も実行した。6 点すべてで、指定した座標に着いた。

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

`pytest` の自動テストは 19 件すべて通った。
