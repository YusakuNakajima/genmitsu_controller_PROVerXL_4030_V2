# Genmitsu PROVerXL 4030 V2 セットアップメモ

SainSmart の CNC ルーター **Genmitsu PROVerXL 4030 V2** を、Mac / Windows から **Universal Gcode Sender(UGS)** で動かすまでの手順と、実際にはまったトラブルの記録。

## ドキュメント

| ファイル | 内容 |
|---|---|
| [SETUP_MAC.md](SETUP_MAC.md) | Mac のセットアップ(ドライバ不要の理由、UGS のインストール、Gatekeeper の回避) |
| [SETUP_WINDOWS.md](SETUP_WINDOWS.md) | Windows のセットアップ(CH340 ドライバ、UGS のインストール) |
| [UGS_GUIDE.md](UGS_GUIDE.md) | UGS の使い方(接続 → ホーミング → ジョグ → 原点設定 → 加工)、GRBL の設定、トラブル事例 |
| [PYTHON_GUIDE.md](PYTHON_GUIDE.md) | Python(pyserial)から GRBL を直接制御する |

## 要点

- **ドライバ**:USB チップは CH340。macOS 11 以降は標準で入っているので不要。Windows 10/11 も多くは自動で入る
- **ソフト**:UGS Platform の最新版を公式サイト(https://winder.github.io/ugs_website/download/)から入れる。付属 USB メモリの UGS / Candle は古いので使わない
- **接続設定**:Firmware `GRBL`、Baud `115200`
- **接続したら、まずホーミング**(🏠 / `$H`)。ホーミングの後、Z は一番上にいる
- **ソフトリミット(`$20=1`)を有効にしてある**。ホーミングの後、動ける範囲(X 400 / Y 300 / Z 100mm)を超える動きは拒否される

## 確認した環境(2026-10-17)

| 項目 | 内容 |
|---|---|
| 機械 | Genmitsu PROVerXL 4030 V2(GRBL 1.1h) |
| Mac | Apple Silicon、macOS(Darwin 27) |
| UGS | Universal Gcode Sender Platform 2.1.26 |
| Windows | 実機では未確認(付属ファイルと公式の配布物から手順を作成) |

## このリポジトリに含めていないもの

次のファイルは機械の付属 USB メモリや SainSmart のサイトから入手できる。著作権とファイルサイズの都合で、このリポジトリには含めていない(`.gitignore` で除外)。手順書では、リポジトリの直下に付属 USB メモリと同じフォルダ構成で置いてある前提で書いている。

- `Genmitsu_PROVerXL_4030_V2_User_Manual_V1.0.pdf`(取扱説明書)
- `Make your first project.pdf`
- `Driver/`(Windows 用 CH340 ドライバ、ドライバのインストール手順 PDF)
- `Test Code/`(テスト用の G-code など)
- UGS のインストーラー(公式サイトから入手)

公式リソース:https://docs.sainsmart.com/article/bhhdcyg7hk-prover-xl-4030-v2

## 注意

個人のセットアップメモであり、SainSmart とは関係ない。CNC は危険を伴う機械なので、操作は取扱説明書の安全上の注意に従い、自己責任で行うこと。
