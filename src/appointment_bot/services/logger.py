import logging
import threading
from datetime import datetime
from logging.handlers import RotatingFileHandler

from appointment_bot.config import Settings

_SETUP_LOCK = threading.Lock()


def setup_logging(settings: Settings) -> None:
    with _SETUP_LOCK:
        root_logger = logging.getLogger()
        if getattr(root_logger, "_appointment_bot_configured", False):
            root_logger.setLevel(settings.log_level)
            return

        settings.logs_dir.mkdir(parents=True, exist_ok=True)
        log_file = settings.logs_dir / f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
        formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)

        root_logger.setLevel(settings.log_level)
        root_logger.addHandler(stream_handler)
        root_logger.addHandler(file_handler)
        root_logger._appointment_bot_configured = True
