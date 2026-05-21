from __future__ import annotations

import json
import logging
import os
import random
import signal
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from appointment_bot.config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunState:
    consecutive_errors: int = 0
    next_allowed_at: datetime | None = None
    last_heartbeat_at: datetime | None = None


class RunTimeoutError(TimeoutError):
    pass


class LockBusyError(RuntimeError):
    pass


class ProcessLock:
    def __init__(self, path: Path, *, stale_after: timedelta) -> None:
        self.path = path
        self.stale_after = stale_after
        self._fd: int | None = None

    def __enter__(self) -> ProcessLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._remove_stale_lock()
        try:
            self._fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise LockBusyError(
                f"Another appointment check is already running: {self.path}"
            ) from exc

        payload = f"pid={os.getpid()}\ncreated_at={datetime.now().isoformat()}\n"
        os.write(self._fd, payload.encode("utf-8"))
        logger.info("Acquired run lock: %s", self.path)
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        try:
            self.path.unlink()
            logger.info("Released run lock: %s", self.path)
        except FileNotFoundError:
            return

    def _remove_stale_lock(self) -> None:
        if not self.path.exists():
            return

        modified_at = datetime.fromtimestamp(self.path.stat().st_mtime)
        if datetime.now() - modified_at < self.stale_after:
            return

        logger.warning("Removing stale run lock: %s", self.path)
        self.path.unlink()


def sleep_with_jitter(settings: Settings) -> None:
    if settings.run_jitter_max_seconds == 0:
        return

    delay = random.randint(settings.run_jitter_min_seconds, settings.run_jitter_max_seconds)
    if delay <= 0:
        return

    logger.info("Sleeping %s seconds before run jitter", delay)
    time.sleep(delay)


@contextmanager
def single_run_lock(settings: Settings) -> Iterator[None]:
    lock = ProcessLock(
        settings.state_dir / "appointment_bot.lock",
        stale_after=timedelta(minutes=settings.lock_stale_minutes),
    )
    with lock:
        yield


@contextmanager
def run_timeout(settings: Settings) -> Iterator[None]:
    if not hasattr(signal, "SIGALRM"):
        logger.info("Global run timeout is not supported on this platform")
        yield
        return

    def _handle_timeout(signum, frame) -> None:
        raise RunTimeoutError(f"Run exceeded {settings.run_timeout_seconds} seconds")

    previous_handler = signal.signal(signal.SIGALRM, _handle_timeout)
    signal.alarm(settings.run_timeout_seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)


def load_run_state(settings: Settings) -> RunState:
    path = _state_path(settings)
    if not path.exists():
        return RunState()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read run state %s: %s", path, exc)
        return RunState()

    return RunState(
        consecutive_errors=int(data.get("consecutive_errors") or 0),
        next_allowed_at=_parse_datetime(data.get("next_allowed_at")),
        last_heartbeat_at=_parse_datetime(data.get("last_heartbeat_at")),
    )


def save_run_state(settings: Settings, state: RunState) -> None:
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "consecutive_errors": state.consecutive_errors,
        "next_allowed_at": _format_datetime(state.next_allowed_at),
        "last_heartbeat_at": _format_datetime(state.last_heartbeat_at),
    }
    _state_path(settings).write_text(json.dumps(data, indent=2), encoding="utf-8")


def should_skip_for_backoff(state: RunState) -> bool:
    return state.next_allowed_at is not None and datetime.now() < state.next_allowed_at


def seconds_until_next_run(state: RunState) -> int:
    if state.next_allowed_at is None:
        return 0

    return max(0, int((state.next_allowed_at - datetime.now()).total_seconds()))


def record_success(settings: Settings, state: RunState) -> RunState:
    updated = RunState(
        consecutive_errors=0,
        next_allowed_at=None,
        last_heartbeat_at=state.last_heartbeat_at,
    )
    save_run_state(settings, updated)
    return updated


def record_failure(settings: Settings, state: RunState) -> RunState:
    consecutive_errors = state.consecutive_errors + 1
    next_allowed_at = None
    if consecutive_errors >= settings.error_backoff_threshold:
        next_allowed_at = datetime.now() + timedelta(seconds=settings.error_backoff_seconds)
        logger.warning(
            "Entering backoff for %s seconds after %s consecutive errors",
            settings.error_backoff_seconds,
            consecutive_errors,
        )

    updated = RunState(
        consecutive_errors=consecutive_errors,
        next_allowed_at=next_allowed_at,
        last_heartbeat_at=state.last_heartbeat_at,
    )
    save_run_state(settings, updated)
    return updated


def should_send_heartbeat(settings: Settings, state: RunState) -> bool:
    if not settings.heartbeat_enabled:
        return False
    if state.last_heartbeat_at is None:
        return True

    elapsed = datetime.now() - state.last_heartbeat_at
    return elapsed >= timedelta(hours=settings.heartbeat_interval_hours)


def record_heartbeat(settings: Settings, state: RunState) -> RunState:
    updated = RunState(
        consecutive_errors=state.consecutive_errors,
        next_allowed_at=state.next_allowed_at,
        last_heartbeat_at=datetime.now(),
    )
    save_run_state(settings, updated)
    return updated


def _state_path(settings: Settings) -> Path:
    return settings.state_dir / "run-state.json"


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat(timespec="seconds")
