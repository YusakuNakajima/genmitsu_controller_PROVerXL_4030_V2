# Genmitsu PROVerXL 4030 V2 — Mac セットアップ手順

## 機種情報

- 機種:Genmitsu PROVerXL 4030 V2(作業範囲 400 × 300 × 110 mm)
- 制御ボード:GRBL 1.1h、通信速度 115200bps
- X/Y/Z 全軸にリミットスイッチあり(ホーミング `$H` が使える)
- コントローラに非常停止ボタン(赤)あり
- 公式リソース:https://docs.sainsmart.com/article/bhhdcyg7hk-prover-xl-4030-v2
- 詳細は `Genmitsu_PROVerXL_4030_V2_User_Manual_V1.0.pdf`(日本語は p.63〜92)

## ドライバについて

コントローラの USB チップは **CH340**(VID `0x1A86` / PID `0x7523`)。
macOS 11 (Big Sur) 以降は Apple 純正ドライバ `AppleUSBCHCOM` が標準で入っているため、**ドライバのインストールは不要**。

> ⚠️ 付属 USB メモリや SainSmart のサイトにある Mac 用ドライバ(`CH34x_Install_V1.4.pkg` など)はインストールしないこと。
> 古い kext 形式のドライバで、最近の macOS では動作しないうえ、純正ドライバと競合してポートが消える原因になる。

動作確認済み(2026-10-17, macOS Darwin 27):
`/dev/cu.usbserial-1130` で接続、115200bps で `Grbl 1.1h` の応答を確認。

## 手順

### 1. 接続
1. **電源を入れる前に**、コントローラ底面の「AC 入力電圧切替スイッチ」が地域の電圧に合っているか確認する(日本は 100V なので、100〜120V 側)。マニュアルで警告されている項目
2. 電源ケーブルは延長コードや電源タップを使わず、壁のコンセントに直接挿す(マニュアルの推奨)
3. USB ケーブルで Mac とコントローラを接続し、コントローラの電源を入れる

### 2. ポートの確認
```bash
ls /dev/cu.usbserial-*
```
`cu.usbserial-XXXX` が表示されれば OK。

表示されない場合:
- 別のケーブルを試す(充電専用ケーブルではデータ通信できない)
- USB ハブを使わず Mac に直接挿す
- コントローラの電源が入っているか確認する
- 以前に WCH 製ドライバを入れたことがあれば削除する
  (システム設定 → 一般 → ログイン項目と機能拡張 → ドライバ機能拡張)

### 3. 送信ソフト(UGS)のインストール
**公式サイトから最新版をダウンロードする。**

1. https://winder.github.io/ugs_website/download/ を開き、Mac の種類に合った dmg をダウンロードする
   - Apple Silicon(M1 以降):`macosx-aarch64-ugs-platform-app-<バージョン>.dmg`
   - Intel:`macosx-x64-ugs-platform-app-<バージョン>.dmg`
   - どちらか分からないときは、アップルメニュー →「この Mac について」の「チップ」欄を見る
   - Java は同梱されているので、別途インストールする必要はない
2. ダウンロードした dmg をダブルクリックすると、Finder に「Universal Gcode Sender」が開く(開かないときは、Finder のサイドバーの「場所」欄にあるので、そこから開く)
3. 中の `Universal Gcode Sender.app` を「Applications」フォルダへドラッグする
4. 「アプリケーション」フォルダから起動する。初回は**署名がないため**「開けません」などの警告が出て起動しないので、次のどちらかで許可する
   - 警告を閉じてから、システム設定 → プライバシーとセキュリティを開き、下の方にある「"Universal Gcode Sender" はブロックされました」の横の **「このまま開く」** を押す。パスワードを入れると起動する
   - 上の方法で出てこない場合は、ターミナルで次を実行してから起動する(このアプリだけ、ダウンロード時に付いた隔離の目印を外す)
     ```bash
     xattr -dr com.apple.quarantine "/Applications/Universal Gcode Sender.app"
     ```
5. 2 回目以降は普通に起動できる。dmg は Finder のサイドバーで取り出してよい

補足(2026-10-17 に確認):
- 公式の Mac 版 dmg は、中身が ISO(CD-ROM 形式)イメージになっている。ダブルクリックで開けるが、アプリ本体には Apple の署名がない
- 公式サイトに載っていない `ugs-<バージョン>-aarch64.dmg` もあるが、こちらは UGS Classic(機能の少ない旧来版)。使うのは Platform 版(`macosx-aarch64-ugs-platform-app-...`)

※ 付属 USB メモリにあった古い UGS(2.0.14)は、Intel 専用で署名もなく更新も止まっているため使わない。Candle については下の「Candle は必要?」を参照。

### 4. 接続設定(UGS)
| 項目 | 値 |
|---|---|
| Firmware | GRBL |
| Port | `/dev/cu.usbserial-XXXX`(`tty.` ではなく `cu.` の方) |
| Baud | 115200 |

「Connect」を押す。

### 5. アラームの解除
起動直後は `Alarm` 状態になるが、これは正常。
この機種は全軸にリミットスイッチがあるので、**ホーミング `$H`** で原点に戻すとアラームが解除される。

- ホーミングを実行すると機械が動くので、周りに物や手がないことを確認してから行う
- ホーミングせずに一時的にロックだけ解除したい場合は `$X`
- 非常停止ボタンが押されたままだと動かない。ボタンを回して解除する

## Candle は必要?

**不要。UGS だけで十分。**
Candle(Grblcontrol)と UGS は、どちらも G-code を機械に送るソフトで、役割は同じ。接続、ホーミング、ジョグ、原点の設定、加工まで UGS でできるので、両方入れる必要はない。

- **マニュアルとの違い:** マニュアルと「Make your first project.pdf」は Candle の画面で説明している。UGS での同じ操作は [UGS_GUIDE.md](UGS_GUIDE.md) にまとめてある
- **Z プローブ:** マニュアルの設定手順は Candle 用。UGS にもプローブ機能(Probe Module)があるが、この機種での設定はまだ確認していない
- **Mac 版:** Intel 専用で署名もなく、2019〜2020 年から更新が止まっている
- **Windows 版:** 2016 年のビルドで更新が止まっている

付属 USB メモリに入っている Candle は、Mac 版も Windows 版も使わない。

## 次に
接続から加工までの UGS の操作は [UGS_GUIDE.md](UGS_GUIDE.md) を参照。
