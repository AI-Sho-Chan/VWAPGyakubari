"""
Offline Backtest Script (Simplified)

Inputs:
- AOI samples CSV: columns [code, timestamp, aoi]
- Minute OHLCV CSV directory: one CSV per code with columns
  [datetime, open, high, low, close, volume] (JST)

Procedure:
1) Build monitoring list using AOI series (08:55–08:59:50).
2) For selected codes, simulate 09:02–09:15 by computing AVWAP(09:00 anchor) and ATR(5),
   detect entry triggers, and output signals.

Usage:
  python backtest/offline_backtest.py \
    --aoi data/aoi_samples.csv \
    --minute-dir data/minute \
    --date 2025-09-02 \
    --output backtest/signals_20250902.json
"""

import argparse
import json
import logging
from pathlib import Path
from datetime import datetime, time
from typing import Dict, List

import pandas as pd
import numpy as np

import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))

import config
def calc_avwap(df: pd.DataFrame, anchor_time: pd.Timestamp) -> float | None:
    d = df[df["datetime"] >= anchor_time].copy()
    if d.empty:
        return None
    if d["volume"].sum() == 0:
        return None
    return float((d["close"] * d["volume"]).sum() / d["volume"].sum())


def calc_atr(df: pd.DataFrame, period: int = 5) -> float | None:
    if len(df) < period + 1:
        return None
    d = df.copy()
    d["prev_close"] = d["close"].shift(1)
    tr1 = d["high"] - d["low"]
    tr2 = (d["high"] - d["prev_close"]).abs()
    tr3 = (d["low"] - d["prev_close"]).abs()
    d["tr"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = d["tr"].rolling(window=period).mean().iloc[-1]
    return float(atr) if pd.notna(atr) else None


def check_trigger(df: pd.DataFrame, direction: str, avwap: float) -> tuple[str, float] | None:
    if len(df) < 2:
        return None
    cur = df.iloc[-1]
    prev = df.iloc[-2]
    cp = float(cur["close"])
    if direction == "short":
        if cp > avwap and prev["close"] > prev["open"] and cp < float(prev["open"]):
            return ("逆張りショート", float(prev["open"]))
    else:
        if cp < avwap and prev["close"] < prev["open"] and cp > float(prev["open"]):
            return ("逆張りロング", float(prev["open"]))
    return None


def build_monitoring_list(aoi_csv: Path, trading_date: str) -> List[Dict]:
    df = pd.read_csv(aoi_csv)
    # Normalize
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])  # JST assumed
    else:
        raise ValueError("AOI CSV must contain 'timestamp' column")
    if "code" not in df.columns or "aoi" not in df.columns:
        raise ValueError("AOI CSV must contain 'code' and 'aoi' columns")

    # Filter by date and time window 08:55:00–08:59:50
    d0 = pd.to_datetime(trading_date)
    start_dt = d0.replace(hour=8, minute=55, second=0)
    end_dt = d0.replace(hour=8, minute=59, second=50)
    df = df[(df["timestamp"] >= start_dt) & (df["timestamp"] <= end_dt)].copy()

    monitoring: List[Dict] = []
    for code, g in df.groupby("code"):
        aoi_values = g.sort_values("timestamp")["aoi"].astype(float).tolist()
        if len(aoi_values) < 3:
            continue
        final_aoi = aoi_values[-1]
        aoi_std = float(np.std(aoi_values))
        if abs(final_aoi) >= config.AOI_THRESHOLD and aoi_std <= config.AOI_STABILITY_THRESHOLD:
            direction = "short" if final_aoi > 0 else "long"
            monitoring.append({
                "code": str(code),
                "aoi": float(final_aoi),
                "aoi_std": float(aoi_std),
                "direction": direction,
                "aoi_history": aoi_values,
            })

    monitoring.sort(key=lambda x: abs(x["aoi"]), reverse=True)
    return monitoring


def load_minute_csv(minute_dir: Path, code: str, trading_date: str) -> pd.DataFrame:
    # Try multiple naming schemes
    candidates = [
        minute_dir / f"{code}.csv",
        minute_dir / f"{code}_{trading_date}.csv",
        minute_dir / f"{trading_date}_{code}.csv",
    ]
    for p in candidates:
        if p.exists():
            df = pd.read_csv(p)
            # Normalize columns
            if "datetime" in df.columns:
                df["datetime"] = pd.to_datetime(df["datetime"])  # JST assumed
            elif "DateTime" in df.columns:
                df["datetime"] = pd.to_datetime(df["DateTime"])  # copy
            else:
                raise ValueError(f"Minute CSV {p} must contain 'datetime' or 'DateTime'")
            req = ["open", "high", "low", "close", "volume"]
            mapping = {"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
            for k, v in mapping.items():
                if v not in df.columns and k in df.columns:
                    df[v] = df[k]
            if not all(c in df.columns for c in req):
                raise ValueError(f"Minute CSV {p} missing columns {req}")
            df = df[ ["datetime", "open", "high", "low", "close", "volume"] ].copy()
            df = df.sort_values("datetime").reset_index(drop=True)
            # Filter target date rows only
            date_only = pd.to_datetime(trading_date).date()
            df = df[df["datetime"].dt.date == date_only]
            return df
    raise FileNotFoundError(f"Minute CSV for {code} not found in {minute_dir}")


def run_offline_backtest(aoi_csv: Path, minute_dir: Path, trading_date: str, output_json: Path) -> Dict:
    logging.info("AOIから監視対象銘柄を選定中...")
    monitoring_list = build_monitoring_list(aoi_csv, trading_date)
    logging.info(f"監視対象銘柄: {len(monitoring_list)} 件")

    # Load data
    d0 = pd.to_datetime(trading_date)
    price_data: Dict[str, pd.DataFrame] = {}
    for stock in monitoring_list:
        code = stock["code"]
        price_data[code] = load_minute_csv(minute_dir, code, trading_date)

    # Simulate minute-by-minute from 09:02 to 09:15
    start_t = d0.replace(hour=9, minute=2, second=0)
    end_t = d0.replace(hour=9, minute=15, second=0)

    signals: List[Dict] = []
    current_t = start_t
    while current_t <= end_t:
        for stock in monitoring_list:
            code = stock["code"]
            direction = stock["direction"]
            df_full = price_data[code]
            # Use data up to current_t
            df = df_full[df_full["datetime"] <= current_t].copy()
            if len(df) < 2:
                continue
            avwap = calc_avwap(df, d0.replace(hour=9, minute=0, second=0))
            atr = calc_atr(df, config.ATR_PERIOD)
            if avwap is None or atr is None:
                current_t = current_t + pd.Timedelta(minutes=1)
                continue
            cp = float(df["close"].iloc[-1])
            if abs(cp - avwap) < config.AVWAP_DEVIATION_MULTIPLIER * atr:
                current_t = current_t + pd.Timedelta(minutes=1)
                continue
            trig = check_trigger(df, direction, avwap)
            if trig:
                stype, entry = trig
                signals.append({
                    "code": code,
                    "timestamp": current_t.isoformat(),
                    "signal_type": stype,
                    "direction": direction,
                    "current_price": cp,
                    "avwap": avwap,
                    "atr": atr,
                    "entry_trigger_price": entry,
                    "target_price": avwap,
                    "stop_loss_price": (df.iloc[-1]["high"] + config.STOP_LOSS_ATR_MULTIPLIER * atr) if direction == "short" else (df.iloc[-1]["low"] - config.STOP_LOSS_ATR_MULTIPLIER * atr),
                    "price_deviation": abs(cp - avwap),
                    "setup_threshold": config.AVWAP_DEVIATION_MULTIPLIER * atr,
                })
        current_t = current_t + pd.Timedelta(minutes=1)

    # Restore full data (optional)
    # Persist results
    out = {
        "date": trading_date,
        "monitoring_count": len(monitoring_list),
        "signals": signals,
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    logging.info(f"オフラインバックテスト完了: {len(signals)} 件のシグナルを {output_json} に保存")
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Asagake Offline Backtest")
    p.add_argument("--aoi", required=True, help="AOI samples CSV path")
    p.add_argument("--minute-dir", required=True, help="Minute CSV directory")
    p.add_argument("--date", required=True, help="Trading date YYYY-MM-DD (JST)")
    p.add_argument("--output", required=True, help="Output JSON path")
    p.add_argument("--log", default="INFO", help="Log level (default: INFO)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log.upper(), logging.INFO), format='%(asctime)s %(levelname)s %(message)s')
    run_offline_backtest(Path(args.aoi), Path(args.minute_dir), args.date, Path(args.output))


if __name__ == "__main__":
    main()
