"""
Notifier module
Sends desktop notifications using plyer per FR-4.
"""

import logging
from typing import Dict, List
from datetime import datetime
from plyer import notification

logger = logging.getLogger(__name__)


class Notifier:
    """Cross-platform desktop notification sender."""

    def __init__(self) -> None:
        self.notification_count = 0

    def send_signal_notification(self, signal: Dict) -> bool:
        """Send a single signal notification."""
        try:
            title, message = self._format_notification(signal)
            notification.notify(
                title=title,
                message=message,
                app_name="Asagake Signal Generator",
                timeout=10,
                toast=False,
            )

            self.notification_count += 1
            logger.info(f"シグナル通知を送信: {signal['code']} - {signal['signal_type']}")
            return True

        except Exception as e:
            logger.error(f"通知送信エラー: {e}")
            return False

    def _format_notification(self, signal: Dict) -> tuple:
        """Format notification title and message per FR-4.2."""
        code = signal["code"]
        signal_type = signal["signal_type"]
        direction = signal["direction"]
        current_price = signal["current_price"]
        entry_trigger = signal["entry_trigger_price"]
        target_price = signal["target_price"]
        stop_loss = signal["stop_loss_price"]
        timestamp = signal["timestamp"]

        title = f"{signal_type} シグナル発生"
        message = (
            f"銘柄コード: {code}\n"
            f"シグナル発生時刻: {timestamp}\n"
            f"売買方向: {direction}\n"
            f"現在価格: {current_price:.0f}円\n"
            f"エントリー・トリガー価格: {entry_trigger:.0f}円\n"
            f"利益確定目標価格 (AVWAP): {target_price:.0f}円\n"
            f"損切り価格: {stop_loss:.0f}円\n\n"
            f"AVWAP乖離: {signal.get('price_deviation', 0):.0f}\n"
            f"ATR(5): {signal.get('atr', 0):.0f}"
        )

        return title, message

    def send_batch_notifications(self, signals: List[Dict]) -> int:
        """Send notifications for a list of signals with small delay."""
        success_count = 0
        for signal in signals:
            if self.send_signal_notification(signal):
                success_count += 1
                import time
                time.sleep(1)
        logger.info(f"一括通知完了 {success_count}/{len(signals)} 件送信")
        return success_count

    def send_system_notification(self, title: str, message: str) -> bool:
        """Send a generic system notification."""
        try:
            notification.notify(
                title=title,
                message=message,
                app_name="Asagake Signal Generator",
                timeout=5,
                toast=False,
            )
            logger.info(f"システム通知を送信: {title}")
            return True
        except Exception as e:
            logger.error(f"システム通知送信エラー: {e}")
            return False

        
    def send_startup_notification(self, monitoring_count: int) -> bool:
        """Send startup notification with monitoring count."""
        title = "Asagake Signal Generator 起動"
        message = (
            f"システムが正常に起動しました\n"
            f"監視対象銘柄数: {monitoring_count}\n"
            f"開始時刻: {datetime.now().strftime('%H:%M:%S')}"
        )
        return self.send_system_notification(title, message)

    def send_shutdown_notification(self, signal_count: int) -> bool:
        """Send shutdown notification with signal count."""
        title = "Asagake Signal Generator 終了"
        message = (
            f"システムが正常に終了しました\n"
            f"生成シグナル数: {signal_count}\n"
            f"終了時刻: {datetime.now().strftime('%H:%M:%S')}"
        )
        return self.send_system_notification(title, message)

    def send_error_notification(self, error_message: str) -> bool:
        """Send error notification with message."""
        title = "Asagake Signal Generator エラー"
        message = (
            f"システムでエラーが発生しました\n"
            f"エラー内容: {error_message}\n"
            f"発生時刻: {datetime.now().strftime('%H:%M:%S')}"
        )
        return self.send_system_notification(title, message)

    def get_notification_stats(self) -> Dict:
        """Return simple notification stats."""
        return {
            "total_notifications_sent": self.notification_count,
            "last_notification_time": datetime.now().isoformat(),
        }

