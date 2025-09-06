"""
Pre-Market Scanner
08:55–08:59:50 JST: compute AOI at 10s intervals and select monitoring list.
"""

import time
import logging
import numpy as np
from datetime import datetime
from typing import List, Dict

from .data_fetcher import JQuantsDataFetcher
import config

logger = logging.getLogger(__name__)


class PreMarketScanner:
    """Scanner for pre-market AOI monitoring and selection."""

    def __init__(self) -> None:
        self.data_fetcher = JQuantsDataFetcher()
        self.aoi_history: Dict[str, List[float]] = {}
        self.monitoring_list: List[Dict] = []

    def scan_pre_market(self) -> List[Dict]:
        """Run pre-market AOI scan and return monitoring list."""
        logger.info("寄り付き前スキャンを開始します (08:55–08:59:50 JST)")

        # Authenticate
        if not self.data_fetcher.authenticate():
            logger.error("J-Quants API認証に失敗しました")
            return []

        # Fetch TSE Prime stock codes
        stock_codes = self.data_fetcher.get_tse_prime_stocks()
        if not stock_codes:
            logger.error("銘柄リストの取得に失敗しました")
            return []

        logger.info(f"対象銘柄数: {len(stock_codes)}")

        # Time window: 08:55:00 to 08:59:50 (local machine assumed JST)
        start_time = datetime.now().replace(hour=8, minute=55, second=0, microsecond=0)
        end_time = datetime.now().replace(hour=8, minute=59, second=50, microsecond=0)

        # Wait until start if early
        now = datetime.now()
        if now < start_time:
            wait_seconds = (start_time - now).total_seconds()
            logger.info(f"スキャン開始まで {wait_seconds:.0f} 秒待機します")
            time.sleep(max(0, wait_seconds))

        # AOI sampling loop
        iteration = 0
        while datetime.now() <= end_time:
            iteration += 1
            logger.info(f"AOIスキャン {iteration} 回目")

            for code in stock_codes:
                try:
                    board_info = self.data_fetcher.get_pre_market_board_info(code)
                    if not board_info:
                        continue

                    aoi = self.data_fetcher.calculate_aoi(board_info)
                    self.aoi_history.setdefault(code, []).append(aoi)
                    logger.debug(f"{code}: AOI={aoi:.4f}")
                except Exception as e:
                    logger.warning(f"{code} のAOI計算でエラー: {e}")
                    continue

            time.sleep(config.DATA_FETCH_INTERVAL)

        logger.info("AOIスキャンが完了しました")

        monitoring_list = self._select_monitoring_stocks()
        self.monitoring_list = monitoring_list

        logger.info(f"監視対象銘柄数: {len(monitoring_list)}")
        for stock in monitoring_list:
            logger.info(
                f"監視対象: {stock['code']} (AOI: {stock['aoi']:.4f}, 方向: {stock['direction']})"
            )

        return monitoring_list

    def _select_monitoring_stocks(self) -> List[Dict]:
        """Select monitoring stocks based on final AOI and stability."""
        monitoring_list: List[Dict] = []

        for code, aoi_values in self.aoi_history.items():
            if len(aoi_values) < 3:
                continue

            final_aoi = aoi_values[-1]
            aoi_std = float(np.std(aoi_values))

            imbalance = abs(final_aoi) >= config.AOI_THRESHOLD
            stable = aoi_std <= config.AOI_STABILITY_THRESHOLD

            if imbalance and stable:
                direction = "short" if final_aoi > 0 else "long"
                monitoring_list.append(
                    {
                        "code": code,
                        "aoi": final_aoi,
                        "aoi_std": aoi_std,
                        "direction": direction,
                        "aoi_history": aoi_values,
                    }
                )
                logger.info(
                    f"選定: {code} - AOI: {final_aoi:.4f}, 標準偏差: {aoi_std:.4f}, 方向: {direction}"
                )

        monitoring_list.sort(key=lambda x: abs(x["aoi"]), reverse=True)
        return monitoring_list

    def get_aoi_summary(self) -> Dict:
        """Return scan summary metrics."""
        total_stocks = len(self.aoi_history)
        monitoring_count = len(self.monitoring_list)

        return {
            "total_stocks_scanned": total_stocks,
            "monitoring_stocks_selected": monitoring_count,
            "selection_rate": monitoring_count / total_stocks if total_stocks > 0 else 0,
            "scan_timestamp": datetime.now().isoformat(),
        }

    def save_monitoring_list(self, filename: str | None = None) -> None:
        """Persist monitoring list to JSON file."""
        import json
        if filename is None:
            filename = f"monitoring_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        data = {
            "timestamp": datetime.now().isoformat(),
            "monitoring_list": self.monitoring_list,
            "summary": self.get_aoi_summary(),
        }

        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"監視リストを {filename} に保存しました")
        except Exception as e:
            logger.error(f"監視リストの保存に失敗: {e}")

    def load_monitoring_list(self, filename: str) -> bool:
        """Load monitoring list from JSON file."""
        import json
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.monitoring_list = data.get("monitoring_list", [])
            logger.info(f"監視リストを {filename} から読み込みました")
            return True
        except Exception as e:
            logger.error(f"監視リストの読み込みに失敗: {e}")
            return False

