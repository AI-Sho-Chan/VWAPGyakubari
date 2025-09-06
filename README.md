# Asagake Hybrid (Python Screener + Excel Cockpit)

ハイブリッド構成: Pythonスクリーナー（寄り前AOIの重い走査） + Excelコックピット（寄り後の視覚的監視）

## 概要
- 08:55–08:59:50 JST: Pythonが東証プライム銘柄の板からAOIを10秒間隔で記録し、安定性と振れ幅で候補を抽出
- 09:00–09:15 JST: トレーダーがExcelで候補銘柄を監視（RSSでリアルタイム更新・条件付き書式で可視化）

## 要件（概略）
- Python 3.10+
- Windows 10/11（通知は不要）
- auカブコム証券 kabuステーション® API（ローカルAPI・APIキー）
- 楽天証券 マーケットスピード II RSS（Excelアドイン）

## インストール
`ash
pip install -r requirements.txt
`

### 設定（.env 推奨）
`env
KABU_API_KEY=your_kabu_api_key
KABU_API_BASE_URL=http://localhost:18080/kabusapi
PRIME_LIST_CSV=data/prime_list.csv

AOI_THRESHOLD=0.4
AOI_STABILITY_THRESHOLD=0.1
AVWAP_DEVIATION_MULTIPLIER=0.6
ATR_PERIOD=5
STOP_LOSS_ATR_MULTIPLIER=1.3
PRE_MARKET_START_TIME=08:55:00
DATA_FETCH_INTERVAL=10
`

## 使い方（Component A: Pythonスクリーナー）
- スケジュール実行（平日8:55に自動起動）
`ash
python main.py
`
- 即時実行
`ash
python main.py --run-now [watchlist出力パス任意]
`
- 出力: watchlist.txt（コピーしやすいPythonリストと、1行1コード表記を併記）

## Excel コックピット（Component B）
- excel/COCKPIT_README.md を参照（RSS関数の例、AVWAP/ATR計算、乖離率の条件付き書式を解説）

## オフライン・バックテスト（任意）
- CSVから監視リストとシグナルを再現
`ash
python backtest/offline_backtest.py \
  --aoi data/aoi_samples.csv \
  --minute-dir data/minute \
  --date 2025-09-02 \
  --output backtest/signals_20250902.json
`
- 入力CSV要件
  - AOI: code,timestamp,aoi（JST、08:55–08:59:50）
  - 1分足: datetime,open,high,low,close,volume（JST）

## 構成
`
VWAPGyakubari/
├── main.py                      # スクリーナー実行（APScheduler）
├── config.py                    # 設定（.env優先）
├── modules/
│   ├── kabu_data_fetcher.py    # kabu API認証・板情報取得
│   └── kabu_screener.py        # AOI記録・候補抽出・出力
├── excel/COCKPIT_README.md     # Excel側の手順書
├── backtest/offline_backtest.py# CSVでの再現シミュレータ
├── data/prime_list_example.csv # プライム銘柄CSVのサンプル（Code列）
└──（旧実装はGit履歴のみで保管）
`

## 注意
- kabu APIはローカルAPIです。kabuステーションを起動しAPIキーを設定のうえご利用ください。
- Excel RSS関数の記法は環境により異なります。実環境のヘルプに従ってください。

## ライセンス / 免責
本ツールは教育・研究目的で提供されます。投資判断は自己責任でお願いします。
