"""
J-Quants API Data Fetcher
・Pre-open board info (for AOI)
・Intraday 1-minute OHLCV (anchor-VWAP and ATR)
"""

import requests
import pandas as pd
import time
import logging
from typing import Dict, List, Optional
from datetime import datetime
import config

logger = logging.getLogger(__name__)


class JQuantsDataFetcher:
    """Wrapper for J-Quants API calls used by the app."""

    def __init__(self) -> None:
        self.base_url = "https://api.jquants.com/v1"
        self.refresh_token: Optional[str] = None
        self.id_token: Optional[str] = None
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
        })

    def authenticate(self) -> bool:
        """Authenticate and set session Authorization header."""
        try:
            # Refresh token
            refresh_url = f"{self.base_url}/token/auth_user"
            refresh_data = {
                "mailaddress": config.JQUANTS_EMAIL,
                "password": config.JQUANTS_PASSWORD,
            }

            response = self.session.post(refresh_url, json=refresh_data)
            response.raise_for_status()

            refresh_result = response.json()
            self.refresh_token = refresh_result.get("refreshToken")

            if not self.refresh_token:
                logger.error("refreshToken の取得に失敗しました")
                return False

            # ID token
            id_url = f"{self.base_url}/token/auth_refresh"
            id_data = {"refreshtoken": self.refresh_token}

            response = self.session.post(id_url, json=id_data)
            response.raise_for_status()

            id_result = response.json()
            self.id_token = id_result.get("idToken")

            if not self.id_token:
                logger.error("idToken の取得に失敗しました")
                return False

            # Set bearer token
            self.session.headers.update({
                'Authorization': f'Bearer {self.id_token}',
            })

            logger.info("J-Quants API認証が完了しました")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"認証エラー: {e}")
            return False
        except Exception as e:
            logger.error(f"予期しないエラー: {e}")
            return False

    def get_tse_prime_stocks(self) -> List[str]:
        """Get TSE Prime market stock codes for today."""
        try:
            url = f"{self.base_url}/listed/info"
            params = {
                "date": datetime.now().strftime("%Y-%m-%d"),
            }

            response = self.session.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            stocks: List[str] = []

            if data.get("info"):
                for item in data["info"]:
                    market_name = (
                        item.get("Market")
                        or item.get("MarketName")
                        or item.get("MarketCodeName")
                        or ""
                    )
                    # Try to match Prime/プライム
                    if str(market_name) in ("Prime", "プライム") or "プライム" in str(market_name):
                        code = item.get("Code") or item.get("code")
                        if code:
                            stocks.append(str(code))

            logger.info(f"東証プライム市場銘柄数: {len(stocks)}")
            return stocks

        except requests.exceptions.RequestException as e:
            logger.error(f"銘柄リスト取得エラー: {e}")
            return []
        except Exception as e:
            logger.error(f"予期しないエラー: {e}")
            return []

    def get_pre_market_board_info(self, code: str) -> Optional[Dict]:
        """Get pre-open board info and normalize to a common schema.

        Tries multiple endpoints commonly used in J-Quants:
        - /markets/quotes (depth aggregation)
        - /market/board_info (legacy path)
        - /markets/auction (if available)
        """
        date = datetime.now().strftime("%Y-%m-%d")

        # Try quotes endpoint (depth aggregation)
        try:
            url = f"{self.base_url}/markets/quotes"
            params = {"code": code, "date": date}
            resp = self.session.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                quotes = data.get("quotes") or data.get("data") or []
                if quotes:
                    q = quotes[0]
                    # Depth arrays may be BidQty/AskQty or BidVolume/AskVolume
                    bid_depth = q.get("BidQty") or q.get("BidVolume") or []
                    ask_depth = q.get("AskQty") or q.get("AskVolume") or []
                    bid_volume = sum(v for v in bid_depth if isinstance(v, (int, float)))
                    ask_volume = sum(v for v in ask_depth if isinstance(v, (int, float)))
                    return {
                        "code": code,
                        "timestamp": q.get("DateTime") or q.get("Timestamp"),
                        "bid_volume": bid_volume,
                        "ask_volume": ask_volume,
                        "bid_price": (q.get("BidPrice") or [None])[0] if isinstance(q.get("BidPrice"), list) else q.get("BidPrice"),
                        "ask_price": (q.get("AskPrice") or [None])[0] if isinstance(q.get("AskPrice"), list) else q.get("AskPrice"),
                    }
        except requests.exceptions.RequestException:
            pass
        except Exception:
            pass

        # Try legacy board_info
        try:
            url = f"{self.base_url}/market/board_info"
            params = {"code": code, "date": date}
            resp = self.session.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("board_info"):
                    b = data["board_info"][0]
                    return {
                        "code": code,
                        "timestamp": b.get("Timestamp"),
                        "bid_volume": b.get("BidVolume", 0),
                        "ask_volume": b.get("AskVolume", 0),
                        "bid_price": b.get("BidPrice", 0),
                        "ask_price": b.get("AskPrice", 0),
                    }
        except requests.exceptions.RequestException:
            pass
        except Exception:
            pass

        # Try auction endpoint (if available)
        try:
            url = f"{self.base_url}/markets/auction"
            params = {"code": code, "date": date}
            resp = self.session.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("auction") or data.get("data") or []
                if items:
                    a = items[0]
                    bid_volume = (
                        a.get("ImbalanceBuyQty")
                        or a.get("BuyQtyTotal")
                        or a.get("BidVolume")
                        or 0
                    )
                    ask_volume = (
                        a.get("ImbalanceSellQty")
                        or a.get("SellQtyTotal")
                        or a.get("AskVolume")
                        or 0
                    )
                    return {
                        "code": code,
                        "timestamp": a.get("DateTime") or a.get("Timestamp"),
                        "bid_volume": bid_volume,
                        "ask_volume": ask_volume,
                        "bid_price": a.get("IndicativePrice") or a.get("BidPrice"),
                        "ask_price": a.get("IndicativePrice") or a.get("AskPrice"),
                    }
        except requests.exceptions.RequestException:
            pass
        except Exception:
            pass

        logger.debug(f"板情報エンドポイント未対応/未取得: code={code}")
        return None

    def get_minute_data(self, code: str, date: Optional[str] = None) -> Optional[pd.DataFrame]:
        """Get 1-minute OHLCV for the specified date (or today).

        Tries, in order:
        - /markets/minutes
        - /markets/candles?timeframe=1min
        - fallback: returns None
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        # Try /markets/minutes
        try:
            url = f"{self.base_url}/markets/minutes"
            params = {"code": code, "date": date}
            r = self.session.get(url, params=params)
            if r.status_code == 200:
                data = r.json()
                key = "minutes" if "minutes" in data else ("data" if "data" in data else None)
                if key:
                    df = pd.DataFrame(data[key])
                    df = self._normalize_minutes_dataframe(df)
                    if df is not None:
                        return df
        except requests.exceptions.RequestException:
            pass
        except Exception:
            pass

        # Try /markets/candles?timeframe=1min
        try:
            url = f"{self.base_url}/markets/candles"
            params = {"code": code, "date": date, "timeframe": "1min"}
            r = self.session.get(url, params=params)
            if r.status_code == 200:
                data = r.json()
                key = "candles" if "candles" in data else ("data" if "data" in data else None)
                if key:
                    df = pd.DataFrame(data[key])
                    df = self._normalize_minutes_dataframe(df)
                    if df is not None:
                        return df
        except requests.exceptions.RequestException:
            pass
        except Exception:
            pass

        logger.debug(f"1分足エンドポイント未対応/未取得: code={code}, date={date}")
        return None

    def _normalize_minutes_dataframe(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """Normalize various minute OHLCV schemas to a common DataFrame."""
        if df is None or df.empty:
            return None

        # Try common columns
        candidates = [
            ("DateTime", "Open", "High", "Low", "Close", "Volume"),
            ("datetime", "open", "high", "low", "close", "volume"),
            ("EndTime", "Open", "High", "Low", "Close", "Volume"),
            ("Time", "Open", "High", "Low", "Close", "Volume"),
        ]

        for cols in candidates:
            if all(c in df.columns for c in cols):
                d = df[list(cols)].copy()
                d.columns = ["datetime", "open", "high", "low", "close", "volume"]
                d["datetime"] = pd.to_datetime(d["datetime"])
                d = d.sort_values("datetime").reset_index(drop=True)
                # Ensure numeric types
                for c in ["open", "high", "low", "close", "volume"]:
                    d[c] = pd.to_numeric(d[c], errors="coerce")
                d = d.dropna(subset=["datetime"]).reset_index(drop=True)
                return d

        return None

    def calculate_aoi(self, board_info: Dict) -> float:
        """Calculate Auction Order Imbalance (AOI). Range [-1, 1]."""
        if not board_info:
            return 0.0

        bid_volume = board_info.get("bid_volume", 0)
        ask_volume = board_info.get("ask_volume", 0)

        if bid_volume + ask_volume == 0:
            return 0.0

        aoi = (bid_volume - ask_volume) / (bid_volume + ask_volume)
        return aoi

    def retry_request(self, func, max_retries: int = 3, delay: float = 1.0):
        """Simple retry wrapper for transient request failures."""
        for attempt in range(max_retries):
            try:
                return func()
            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:
                    raise e
                logger.warning(f"リクエスト失敗 (試行 {attempt + 1}/{max_retries}): {e}")
                time.sleep(delay)
