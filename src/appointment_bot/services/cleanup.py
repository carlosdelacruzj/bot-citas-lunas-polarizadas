import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from appointment_bot.config import Settings
from appointment_bot.db.cleanup import cleanup_database_history

logger = logging.getLogger(__name__)

SCREENSHOT_PROTECTED_ROOTS = {
    "preflight",
    "whatsapp",
    "whatsapp-followup-outgoing",
    "whatsapp-outgoing",
}
SCREENSHOT_PROTECTED_NAME_MARKERS = (
    "available",
    "bloque",
    "confirmacion",
    "cupo",
    "defense",
    "defensa",
    "error",
    "fallo",
    "original-html",
    "original_html",
    "parcial",
    "partial",
    "portal",
    "post-submit",
    "post_submit",
    "preenvio",
    "programado",
    "rechaz",
    "rejected",
    "reservation-unconfirmed",
    "reservation_unconfirmed",
    "slot-lost",
    "slot_lost",
)


def cleanup_old_files(settings: Settings) -> None:
    cutoff = datetime.now() - timedelta(days=settings.cleanup_retention_days)
    _cleanup_directory(settings.logs_dir, cutoff=cutoff)
    _cleanup_directory(
        settings.screenshots_dir,
        cutoff=cutoff,
        preserve=lambda path: _preserve_screenshot(path, settings.screenshots_dir),
    )
    _cleanup_directory(settings.client_videos_dir, cutoff=cutoff)
    removed_rows = cleanup_database_history(settings)
    if any(removed_rows.values()):
        logger.info("Removed old database rows: %s", removed_rows)


def _cleanup_directory(
    directory: Path,
    *,
    cutoff: datetime,
    preserve: Callable[[Path], bool] | None = None,
) -> int:
    if not directory.exists():
        return 0

    removed = 0
    for path in directory.rglob("*"):
        if path.is_symlink() or not path.is_file() or path.name == ".gitkeep":
            continue
        if preserve is not None and preserve(path):
            continue

        try:
            modified_at = datetime.fromtimestamp(path.stat().st_mtime)
        except OSError as exc:
            logger.warning("Could not inspect old file %s: %s", path, exc)
            continue
        if modified_at >= cutoff:
            continue

        try:
            path.unlink()
            removed += 1
            logger.info("Removed old file: %s", path)
        except OSError as exc:
            logger.warning("Could not remove old file %s: %s", path, exc)

    _remove_empty_directories(directory)
    if removed:
        logger.info("Removed %s old file(s) below %s", removed, directory)
    return removed


def _preserve_screenshot(path: Path, screenshots_root: Path) -> bool:
    try:
        relative_path = path.relative_to(screenshots_root)
    except ValueError:
        return True
    if relative_path.parts and relative_path.parts[0].lower() in SCREENSHOT_PROTECTED_ROOTS:
        return True
    normalized_name = path.name.lower()
    return any(marker in normalized_name for marker in SCREENSHOT_PROTECTED_NAME_MARKERS)


def _remove_empty_directories(directory: Path) -> None:
    directories = sorted(
        (path for path in directory.rglob("*") if path.is_dir() and not path.is_symlink()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for path in directories:
        try:
            path.rmdir()
        except OSError:
            continue
