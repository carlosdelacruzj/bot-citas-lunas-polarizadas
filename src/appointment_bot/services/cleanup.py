import logging
from datetime import datetime, timedelta
from pathlib import Path

from appointment_bot.config import Settings
from appointment_bot.db.cleanup import cleanup_database_history

logger = logging.getLogger(__name__)


def cleanup_old_files(settings: Settings) -> None:
    cutoff = datetime.now() - timedelta(days=settings.cleanup_retention_days)
    for directory in (settings.logs_dir, settings.screenshots_dir, settings.client_videos_dir):
        _cleanup_directory(directory, cutoff=cutoff)
    cleanup_database_history(settings)


def _cleanup_directory(directory: Path, *, cutoff: datetime) -> None:
    if not directory.exists():
        return

    for path in directory.iterdir():
        if not path.is_file() or path.name == ".gitkeep":
            continue

        modified_at = datetime.fromtimestamp(path.stat().st_mtime)
        if modified_at >= cutoff:
            continue

        try:
            path.unlink()
            logger.info("Removed old file: %s", path)
        except OSError as exc:
            logger.warning("Could not remove old file %s: %s", path, exc)
