"""
auカブコム証券 kabuステーション® API データ取得
・寄り前の板情報取得（board）

前提:
- kabuステーションが起動済みで、API機能が有効
- APIキーを取得し、config.KABU_API_KEY に設定
"""

from __future__ import annotations

import logging
from typing import Dict, Optional
import requests
from datetime import datetime
import config

logger = logging.getLogger(__name__)


class KabuDataFetcher:
    """kabuステーション API ラッパー"""

    def __init__(self) -> None:
        self.base_url = config.KABU_API_BASE_URL.rstrip("/")
        self.apikey = config.KABU_API_KEY
        self.token: Optional[str] = None
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def authenticate(self) -> bool:
        """POST /token でトークン取得（ローカルAPI）"""
        try:
            url = f"{self.base_url}/token"
            resp = self.session.post(url, json={"APIPassword": self.apikey}, timeout=3)
            resp.raise_for_status()
            data = resp.json()
            self.token = data.get("Token") or data.get("token")
            if not self.token:
                logger.error("kabu API token が取得できませんでした")
                return False
            self.session.headers.update({"X-API-KEY": self.apikey})
            logger.info("kabu API 認証成功")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"kabu API 認証エラー: {e}")
            return False
        except Exception as e:
            logger.error(f"kabu API 認証予期しないエラー: {e}")
            return False

    def get_board(self, code: str, exchange: int = None) -> Optional[Dict]:
        """板情報を取得

        GET /board/{symbol}@{exchange}
        exchange: 1=東証, 3=名証, 5=福証, 6=札証 など（仕様に準拠）
        """
        if exchange is None:
            exchange = config.KABU_EXCHANGE
        try:
            # 形式: /board/7203@1 （API仕様により /board/{symbol}?exchange=1 の場合もあり）
            url1 = f"{self.base_url}/board/{code}@{exchange}"
            resp = self.session.get(url1, timeout=3)
            if resp.status_code == 404:
                # 別形式
                url2 = f"{self.base_url}/board/{code}"
                resp = self.session.get(url2, params={"exchange": exchange}, timeout=3)
            resp.raise_for_status()
            b = resp.json()
            # 正規化
            # kabu API の板は Best/Depth を含み得る。ここでは累計買い/売り数量を合計する。
            def _sum_depth(arr):
                if not isinstance(arr, list):
                    return 0
                total = 0
                for item in arr:
                    # item は dict で Qty or Volume を持つことが多い
                    qty = (
                        item.get("Qty")
                        or item.get("qty")
                        or item.get("Volume")
                        or item.get("volume")
                        or 0
                    )
                    try:
                        total += int(qty)
                    except Exception:
                        pass
                return total

            bid_depth = b.get("Buy1") or b.get("Bid") or b.get("buys") or []
            ask_depth = b.get("Sell1") or b.get("Ask") or b.get("sells") or []
            # 可能なら Depth 形式
            if isinstance(b.get("Bids"), list):
                bid_depth = b.get("Bids")
            if isinstance(b.get("Asks"), list):
                ask_depth = b.get("Asks")

            bid_volume = _sum_depth(bid_depth)
            ask_volume = _sum_depth(ask_depth)

            best_bid = b.get("BidPrice") or (bid_depth[0].get("Price") if isinstance(bid_depth, list) and bid_depth else None)
            best_ask = b.get("AskPrice") or (ask_depth[0].get("Price") if isinstance(ask_depth, list) and ask_depth else None)

            return {
                "code": code,
                "timestamp": datetime.now().isoformat(),
                "bid_volume": bid_volume,
                "ask_volume": ask_volume,
                "bid_price": best_bid or 0,
                "ask_price": best_ask or 0,
            }
        except requests.exceptions.RequestException as e:
            logger.warning(f"板情報取得エラー {code}: {e}")
            return None
        except Exception as e:
            logger.warning(f"板情報取得予期せぬエラー {code}: {e}")
            return None

    @staticmethod
    def calculate_aoi(board: Dict) -> float:
        if not board:
            return 0.0
        b = board.get("bid_volume", 0)
        a = board.get("ask_volume", 0)
        s = (b + a)
        if s == 0:
            return 0.0
        return (b - a) / s

