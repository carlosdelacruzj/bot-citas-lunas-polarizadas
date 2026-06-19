import logging
from datetime import datetime, timedelta
from pathlib import Path

from appointment_bot.config import Settings
from appointment_bot.services.database import cleanup_database_history

logger = logging.getLogger(__name__)


def cleanup_old_files(settings: Settings) -> None:
    cutoff = datetime.now() - timedelta(days=settings.cleanup_retention_days)
    for directory in (settings.logs_dir, settings.screenshots_dir, settings.diagnostics_dir):
        _cleanup_directory(directory, cutoff=cutoff)
    cleanup_unconfirmed_video_artifacts(settings)
    cleanup_database_history(settings)


def cleanup_unconfirmed_video_artifacts(settings: Settings) -> None:
    videos_dir = settings.videos_dir
    confirmed_dir = settings.client_videos_dir
    if not videos_dir.exists():
        return

    try:
        confirmed_dir = confirmed_dir.resolve()
    except OSError:
        confirmed_dir = confirmed_dir.absolute()

    for path in videos_dir.rglob("*"):
        if not path.is_file() or path.name == ".gitkeep":
            continue
        try:
            resolved_path = path.resolve()
        except OSError:
            resolved_path = path.absolute()
        if _is_relative_to(resolved_path, confirmed_dir):
            continue
        try:
            path.unlink()
            logger.info("Removed unconfirmed video artifact: %s", path)
        except OSError as exc:
            logger.warning("Could not remove unconfirmed video artifact %s: %s", path, exc)

    directories = sorted(
        (item for item in videos_dir.rglob("*") if item.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    )
    for path in directories:
        try:
            resolved_path = path.resolve()
        except OSError:
            resolved_path = path.absolute()
        if _is_relative_to(resolved_path, confirmed_dir):
            continue
        try:
            path.rmdir()
            logger.info("Removed empty video artifact directory: %s", path)
        except OSError:
            pass


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


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
