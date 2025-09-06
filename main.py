"""
Asagake Screener (Hybrid Architecture - Component A)
寄り付き前 AOI スクリーニング専用（kabuステーション® API）
出力: 監視銘柄コードのリスト（コンソール/テキスト）
"""

import logging
import sys
from datetime import datetime
from typing import Tuple
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:  # pragma: no cover
    ZoneInfo = None

import config
from modules.kabu_screener import KabuScreener


def setup_logging() -> None:
    """Initialize logging for console and file."""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    file_handler = logging.FileHandler(config.LOG_FILE, encoding='utf-8')
    file_handler.setLevel(getattr(logging, config.LOG_LEVEL))
    file_handler.setFormatter(logging.Formatter(log_format))

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format))

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)


class AsagakeScreenerApp:
    """Asagake Python Screener (Component A)"""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self.scheduler = BlockingScheduler()
        self.screener = KabuScreener()
        self.watchlist_output = "watchlist.txt"
        self.is_running = False

    def run_pre_market_scan(self) -> None:
        """8:55〜8:59:50 スキャンし、ウォッチリストを出力後に終了。"""
        try:
            self.logger.info("寄り付き前スクリーニングを開始します (kabu API)")
            codes = self.screener.load_prime_codes()
            selected = self.screener.scan(codes)

            # 出力
            copy_str = self.screener.format_list_for_copy(selected)
            print(copy_str)
            self.screener.write_watchlist(selected, self.watchlist_output)
            self.logger.info(f"選定銘柄数: {len(selected)}")

            # スケジューラ停止（プロセス終了）
            if self.scheduler.running:
                self.scheduler.shutdown(wait=False)
        except Exception as e:
            self.logger.error(f"スクリーニングでエラー: {e}")

    def setup_scheduler(self) -> None:
        """Configure APScheduler jobs for JST schedule."""
        try:
            def _hms(value: str) -> Tuple[int, int, int]:
                h, m, s = value.split(":")
                return int(h), int(m), int(s)

            pm_h, pm_m, pm_s = _hms(config.PRE_MARKET_START_TIME)

            tz = ZoneInfo("Asia/Tokyo") if ZoneInfo else None

            # Screener (Mon-Fri)
            self.scheduler.add_job(
                func=self.run_pre_market_scan,
                trigger=CronTrigger(
                    day_of_week='mon-fri',
                    hour=pm_h,
                    minute=pm_m,
                    second=pm_s,
                    timezone=tz,
                ),
                id='screener',
                name='kabu_preopen_screener',
                max_instances=1,
            )

            # Signal monitoring (Mon-Fri)
            self.scheduler.add_job(
                func=self.run_signal_monitoring,
                trigger=CronTrigger(
                    day_of_week='mon-fri',
                    hour=se_h,
                    minute=se_m,
                    second=se_s,
                    timezone=tz,
                ),
                id='signal_monitoring',
                name='signal_monitoring',
                max_instances=1,
            )

            self.logger.info("スケジューラーを設定しました")

        except Exception as e:
            self.logger.error(f"スケジューラー設定エラー: {e}")
            raise

    def start(self) -> None:
        """Start the application and scheduler."""
        try:
            self.logger.info("Asagake Screener を開始します")
            self.logger.info(f"寄り付き前スクリーニング: 毎営業日 {config.PRE_MARKET_START_TIME}")

            self.is_running = True
            self.setup_scheduler()
            self.scheduler.start()

        except KeyboardInterrupt:
            self.logger.info("ユーザーによる停止要求を受信しました")
            self.stop()
        except Exception as e:
            self.logger.error(f"アプリケーション実行エラー: {e}")
            self.notifier.send_error_notification(f"アプリケーションエラー: {e}")
            raise

    def stop(self) -> None:
        """Stop the application and scheduler."""
        try:
            self.logger.info("Asagake Signal Generator を停止します")
            self.is_running = False

            if self.scheduler.running:
                self.scheduler.shutdown()

            self.logger.info("アプリケーションが正常に終了しました")

        except Exception as e:
            self.logger.error(f"アプリケーション停止エラー: {e}")

    def run_now(self, output: str | None = None) -> None:
        """即時実行（テスト/手動）"""
        self.logger.info("即時スクリーニングを開始します")

        try:
            if output:
                self.watchlist_output = output
            codes = self.screener.load_prime_codes()
            selected = self.screener.scan(codes)
            print(self.screener.format_list_for_copy(selected))
            self.screener.write_watchlist(selected, self.watchlist_output)

        except Exception as e:
            self.logger.error(f"即時スクリーニングでエラー: {e}")


def main() -> None:
    """Main entry point."""
    setup_logging()
    logger = logging.getLogger(__name__)

    try:
        app = AsagakeScreenerApp()

        if len(sys.argv) > 1 and sys.argv[1] == "--run-now":
            out = sys.argv[2] if len(sys.argv) > 2 else None
            logger.info("即時モードで実行します")
            app.run_now(output=out)
        else:
            logger.info("スケジュールモードで実行します")
            app.start()

    except Exception as e:
        logger.error(f"メイン関数でエラー: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
