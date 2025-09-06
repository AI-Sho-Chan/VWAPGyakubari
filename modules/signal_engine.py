"""
Real-time Signal Engine
Computes AVWAP (anchored at 09:00) and ATR(5),
monitors setup and entry triggers, and produces trade signals.
"""

import time
import logging
import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from .data_fetcher import JQuantsDataFetcher
import config

logger = logging.getLogger(__name__)


class SignalEngine:
    """Real-time signal monitoring engine."""

    def __init__(self) -> None:
        self.data_fetcher = JQuantsDataFetcher()
        self.monitoring_list: List[Dict] = []
        self.price_data: Dict[str, pd.DataFrame] = {}
        self.anchor_time: Optional[datetime] = None  # 09:00 anchor
        self.signals_generated: List[Dict] = []

    def set_monitoring_list(self, monitoring_list: List[Dict]) -> None:
        """Set monitoring list produced by pre-market scanner."""
        self.monitoring_list = monitoring_list
        logger.info(f"監視対象銘柄数: {len(monitoring_list)}")

    def start_signal_monitoring(self) -> List[Dict]:
        """Run monitoring loop until 09:15 JST."""
        logger.info("シグナル監視を開始します (09:02–09:15 JST)")

        if not self.data_fetcher.authenticate():
            logger.error("J-Quants API認証に失敗しました")
            return []

        if not self.monitoring_list:
            logger.warning("監視対象銘柄が設定されていません")
            return []

        # Anchor at 09:00
        self.anchor_time = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
        end_time = datetime.now().replace(hour=9, minute=15, second=0, microsecond=0)

        # Wait until 09:02 if early
        start_time = datetime.now().replace(hour=9, minute=2, second=0, microsecond=0)
        now = datetime.now()
        if now < start_time:
            wait_seconds = (start_time - now).total_seconds()
            logger.info(f"シグナル監視開始まで {wait_seconds:.0f} 秒待機します")
            time.sleep(max(0, wait_seconds))

        # Initialize price data
        self._initialize_price_data()

        while datetime.now() <= end_time:
            try:
                for stock in self.monitoring_list:
                    code = stock["code"]
                    direction = stock["direction"]

                    # Refresh data
                    self._update_price_data(code)

                    # Check signal
                    signal = self._check_signal(code, direction)
                    if signal:
                        self.signals_generated.append(signal)
                        logger.info(f"シグナル生成: {code} - {signal['signal_type']}")

                # Sleep to next minute
                time.sleep(60)

            except Exception as e:
                logger.error(f"シグナル監視中にエラー: {e}")
                time.sleep(60)
                continue

        logger.info(f"シグナル監視終了。生成数: {len(self.signals_generated)}")
        return self.signals_generated

    def _initialize_price_data(self) -> None:
        """Fetch initial 1-minute data for each monitored code."""
        logger.info("初期価格データを取得中...")

        for stock in self.monitoring_list:
            code = stock["code"]
            try:
                df = self.data_fetcher.get_minute_data(code)
                if df is not None and not df.empty:
                    self.price_data[code] = df
                    logger.debug(f"{code}: {len(df)} 件のデータを取得")
                else:
                    logger.warning(f"{code}: データ取得失敗")
            except Exception as e:
                logger.warning(f"{code}: 初期データ取得エラー: {e}")

    def _update_price_data(self, code: str) -> None:
        """Refresh 1-minute data for a code."""
        try:
            df = self.data_fetcher.get_minute_data(code)
            if df is not None and not df.empty:
                self.price_data[code] = df
        except Exception as e:
            logger.warning(f"{code}: データ更新エラー: {e}")

    def calculate_avwap(self, code: str) -> Optional[float]:
        """Compute anchored VWAP from 09:00."""
        if code not in self.price_data:
            return None

        df = self.price_data[code]
        if df.empty:
            return None

        anchor_time = self.anchor_time
        if not anchor_time:
            return None

        df_filtered = df[df["datetime"] >= anchor_time].copy()
        if df_filtered.empty:
            return None

        df_filtered["vwap_component"] = df_filtered["close"] * df_filtered["volume"]
        total_vwap = float(df_filtered["vwap_component"].sum())
        total_volume = float(df_filtered["volume"].sum())

        if total_volume == 0:
            return None

        return total_vwap / total_volume

    def calculate_atr(self, code: str, period: int = 5) -> Optional[float]:
        """Compute ATR using simple moving average of True Range."""
        if code not in self.price_data:
            return None

        df = self.price_data[code]
        if len(df) < period + 1:
            return None

        df = df.copy()
        df["prev_close"] = df["close"].shift(1)
        df["tr1"] = df["high"] - df["low"]
        df["tr2"] = (df["high"] - df["prev_close"]).abs()
        df["tr3"] = (df["low"] - df["prev_close"]).abs()
        df["true_range"] = df[["tr1", "tr2", "tr3"]].max(axis=1)

        atr = df["true_range"].rolling(window=period).mean().iloc[-1]
        return float(atr) if pd.notna(atr) else None

    def _check_signal(self, code: str, direction: str) -> Optional[Dict]:
        """Check setup and entry trigger; return signal dict if triggered."""
        try:
            df = self.price_data.get(code)
            if df is None or df.empty:
                return None

            current_price = float(df["close"].iloc[-1])

            # Compute AVWAP and ATR
            avwap = self.calculate_avwap(code)
            atr = self.calculate_atr(code, config.ATR_PERIOD)
            if avwap is None or atr is None:
                return None

            # Setup condition
            price_deviation = abs(current_price - avwap)
            setup_threshold = config.AVWAP_DEVIATION_MULTIPLIER * atr
            if price_deviation < setup_threshold:
                return None

            # Entry trigger check (returns type and trigger price)
            trigger = self._check_entry_trigger(df, direction, avwap)
            if not trigger:
                return None

            signal_type, entry_trigger_price = trigger

            target_price = avwap
            stop_loss_price = self._calculate_stop_loss(df, direction, atr)

            signal = {
                "code": code,
                "name": self.data_fetcher.get_company_name(code) or code,
                "timestamp": datetime.now().isoformat(),
                "signal_type": signal_type,
                "direction": direction,
                "current_price": current_price,
                "avwap": avwap,
                "atr": atr,
                "entry_trigger_price": float(entry_trigger_price),
                "target_price": float(target_price),
                "stop_loss_price": float(stop_loss_price),
                "price_deviation": float(price_deviation),
                "setup_threshold": float(setup_threshold),
            }

            return signal

        except Exception as e:
            logger.warning(f"{code} のシグナルチェックでエラー: {e}")
            return None

    def _check_entry_trigger(self, df: pd.DataFrame, direction: str, avwap: float) -> Optional[Tuple[str, float]]:
        """Detect simple reversal entry trigger and return (type, trigger_price)."""
        if len(df) < 2:
            return None

        current_candle = df.iloc[-1]
        previous_candle = df.iloc[-2]
        current_price = float(current_candle["close"])

        if direction == "short":
            # Mean-reversion short: above AVWAP then reversal
            if current_price > avwap:
                # Previous was bullish, and close falls below prev open
                if (
                    previous_candle["close"] > previous_candle["open"]
                    and current_price < float(previous_candle["open"])
                ):
                    return ("逆張りショート", float(previous_candle["open"]))

        elif direction == "long":
            # Mean-reversion long: below AVWAP then reversal
            if current_price < avwap:
                # Previous was bearish, and close rises above prev open
                if (
                    previous_candle["close"] < previous_candle["open"]
                    and current_price > float(previous_candle["open"])
                ):
                    return ("逆張りロング", float(previous_candle["open"]))

        return None

    def _calculate_stop_loss(self, df: pd.DataFrame, direction: str, atr: float) -> float:
        """Compute stop loss per spec (candle extreme ± 1.3 * ATR)."""
        current_candle = df.iloc[-1]
        if direction == "short":
            return float(current_candle["high"]) + config.STOP_LOSS_ATR_MULTIPLIER * atr
        else:
            return float(current_candle["low"]) - config.STOP_LOSS_ATR_MULTIPLIER * atr

    def get_signal_summary(self) -> Dict:
        """Summary of generated signals."""
        total_signals = len(self.signals_generated)
        long_signals = len([s for s in self.signals_generated if s["direction"] == "long"])
        short_signals = len([s for s in self.signals_generated if s["direction"] == "short"])

        return {
            "total_signals": total_signals,
            "long_signals": long_signals,
            "short_signals": short_signals,
            "monitoring_stocks": len(self.monitoring_list),
            "monitoring_end_time": datetime.now().isoformat(),
        }
