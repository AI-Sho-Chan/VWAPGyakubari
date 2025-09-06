# Asagake Signal Generator

寄り付き逆張りスキャルピング・シグナルジェネレーター（半自動シグナル通知ツール）

## 概要

東京証券取引所の寄り付き前（8:55–8:59:50）の板寄せ不均衡（AOI）を監視し、寄り付き後（9:02–9:15）にアンカードVWAP（09:00基準）への回帰を狙う逆張りシグナルを生成・通知します。実行・発注は行いません（通知のみ）。

## 要件

- Python 3.10+
- Windows 10/11（通知対応）
- J-Quants API アカウント（無料プランで開発可、実運用は有料推奨）

## インストール

```bash
pip install -r requirements.txt
```

### 設定

`.env`（推奨）または `config.py` で認証情報・戦略パラメータを設定します。

```env
JQUANTS_EMAIL=you@example.com
JQUANTS_PASSWORD=your_password
AOI_THRESHOLD=0.4
AOI_STABILITY_THRESHOLD=0.1
AVWAP_DEVIATION_MULTIPLIER=0.6
ATR_PERIOD=5
STOP_LOSS_ATR_MULTIPLIER=1.3
PRE_MARKET_START_TIME=08:55:00
SIGNAL_ENGINE_START_TIME=09:02:00
SIGNAL_ENGINE_END_TIME=09:15:00
DATA_FETCH_INTERVAL=10
```

`config.py` は環境変数を自動読み込み（python-dotenv）し、未設定時はデフォルト値を使用します。APIキーなどの秘匿情報は環境変数で管理してください。

## 使い方

通常モード（スケジューラー実行）:

```bash
python main.py
```

テストモード（即時実行）:

```bash
python main.py --test
```

### オフライン・バックテスト

CSVからシミュレーションを行い、監視リストとシグナルを再現します。

準備:
- AOIサンプルCSV `aoi_samples.csv`（列: `code,timestamp,aoi`。時刻はJST、08:55–08:59:50の10秒刻み）
- 1分足CSVディレクトリ `data/minute/`（銘柄ごとにCSV。列: `datetime,open,high,low,close,volume`。JSTで当日分を含む）

実行例:
```bash
python backtest/offline_backtest.py \
  --aoi data/aoi_samples.csv \
  --minute-dir data/minute \
  --date 2025-09-02 \
  --output backtest/signals_20250902.json
```

## 構成

```
VWAPGyakubari/
├── main.py                 # メインアプリ（スケジューラー）
├── config.py               # 設定（env優先）
├── requirements.txt
├── modules/
│   ├── __init__.py
│   ├── data_fetcher.py     # J-Quants API I/O
│   ├── pre_market_scanner.py  # AOI監視・選定
│   └── signal_engine.py    # AVWAP/ATR計算・トリガー検知
└── README.md
```

## 仕様対応（抜粋）

- 認証: J-Quants API リフレッシュ→IDトークン取得
- Pre-Market Scanner:
  - 8:55–8:59:50 の間、10秒間隔で AOI を記録
  - 終了時点の |AOI| ≥ 0.4 かつ AOI標準偏差 ≤ 閾値 を監視対象に選定
- Signal Engine:
  - 09:00 アンカーの AVWAP、ATR(5) を算出
  - |価格−AVWAP| ≥ 0.6×ATR(5) をセットアップ条件に採用
  - 反転トリガー（前足陽線→現在足がその始値割れ等）を検知
- Notifier:
  - 銘柄コード、時刻、方向、トリガー価格、AVWAP（利確目標）、損切り（足極値±1.3×ATR）を通知

## 注意

- J-Quants のエンドポイントはプランにより minute 足の提供が異なる可能性があります。本実装の minute 取得エンドポイントは確認のうえ適宜修正してください。
- タイムゾーンは APScheduler の CronTrigger に Asia/Tokyo を設定（zoneinfo 利用）。Windows では `tzdata` パッケージを利用します。

## ライセンス / 免責

本ツールは教育・研究目的で提供されます。投資判断は自己責任でお願いします。
