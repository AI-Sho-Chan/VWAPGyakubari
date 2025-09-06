"""
Asagake Signal Generator - Main Application
寄り付き逆張りスキャルピング・シグナルジェネレーター
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
from modules.pre_market_scanner import PreMarketScanner
from modules.signal_engine import SignalEngine
from modules.notifier import Notifier


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


class AsagakeSignalGenerator:
    """Asagake Signal Generator main class."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self.scheduler = BlockingScheduler()
        self.pre_market_scanner = PreMarketScanner()
        self.signal_engine = SignalEngine()
        self.notifier = Notifier()
        self.monitoring_list = []
        self.is_running = False

    def run_pre_market_scan(self) -> None:
        """Run pre-market scan."""
        try:
            self.logger.info("寄り付き前スキャンを開始します")

            monitoring_list = self.pre_market_scanner.scan_pre_market()

            if monitoring_list:
                self.monitoring_list = monitoring_list
                self.signal_engine.set_monitoring_list(monitoring_list)

                # Send startup notification
                self.notifier.send_startup_notification(len(monitoring_list))

                self.logger.info(f"監視対象銘柄 {len(monitoring_list)} 件を設定しました")
            else:
                self.logger.warning("監視対象銘柄が見つかりませんでした")
                self.notifier.send_system_notification(
                    "監視対象銘柄なし",
                    "寄り付き前スキャンで監視対象銘柄が見つかりませんでした",
                )

        except Exception as e:
            self.logger.error(f"寄り付き前スキャンでエラー: {e}")
            self.notifier.send_error_notification(f"寄り付き前スキャンエラー: {e}")

    def run_signal_monitoring(self) -> None:
        """Run real-time signal monitoring."""
        try:
            if not self.monitoring_list:
                self.logger.warning("監視対象銘柄が設定されていません")
                return

            self.logger.info("シグナル監視を開始します")

            signals = self.signal_engine.start_signal_monitoring()

            if signals:
                success_count = self.notifier.send_batch_notifications(signals)
                self.logger.info(
                    f"シグナル {len(signals)} 件を生成し、{success_count} 件の通知を送信しました"
                )
            else:
                self.logger.info("シグナルは生成されませんでした")

            self.notifier.send_shutdown_notification(len(signals))

        except Exception as e:
            self.logger.error(f"シグナル監視でエラー: {e}")
            self.notifier.send_error_notification(f"シグナル監視エラー: {e}")

    def setup_scheduler(self) -> None:
        """Configure APScheduler jobs for JST schedule."""
        try:
            def _hms(value: str) -> Tuple[int, int, int]:
                h, m, s = value.split(":")
                return int(h), int(m), int(s)

            pm_h, pm_m, pm_s = _hms(config.PRE_MARKET_START_TIME)
            se_h, se_m, se_s = _hms(config.SIGNAL_ENGINE_START_TIME)

            tz = ZoneInfo("Asia/Tokyo") if ZoneInfo else None

            # Pre-market scan (Mon-Fri)
            self.scheduler.add_job(
                func=self.run_pre_market_scan,
                trigger=CronTrigger(
                    day_of_week='mon-fri',
                    hour=pm_h,
                    minute=pm_m,
                    second=pm_s,
                    timezone=tz,
                ),
                id='pre_market_scan',
                name='pre_market_scan',
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
            self.logger.info("Asagake Signal Generator を開始します")
            self.logger.info(f"寄り付き前スキャン: 毎営業日 {config.PRE_MARKET_START_TIME}")
            self.logger.info(
                f"シグナル監視: 毎営業日 {config.SIGNAL_ENGINE_START_TIME} - {config.SIGNAL_ENGINE_END_TIME}"
            )

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

    def run_manual_test(self) -> None:
        """Run pre-market scan and signal monitoring immediately (test mode)."""
        self.logger.info("手動テストモードを開始します")

        try:
            # Run pre-market scan
            self.run_pre_market_scan()

            if self.monitoring_list:
                # Run signal monitoring
                self.run_signal_monitoring()
            else:
                self.logger.info("監視対象銘柄がないため、シグナル監視をスキップします")

        except Exception as e:
            self.logger.error(f"手動テストでエラー: {e}")
            self.notifier.send_error_notification(f"手動テストエラー: {e}")


def main() -> None:
    """Main entry point."""
    setup_logging()
    logger = logging.getLogger(__name__)

    try:
        app = AsagakeSignalGenerator()

        if len(sys.argv) > 1 and sys.argv[1] == "--test":
            logger.info("テストモードで実行します")
            app.run_manual_test()
        else:
            logger.info("通常モードで実行します")
            app.start()

    except Exception as e:
        logger.error(f"メイン関数でエラー: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

