from __future__ import annotations

import json
import logging
import os
import random
import signal
import threading
import time
import uuid
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
    def __init__(self, message: str = "Run exceeded the configured timeout") -> None:
        super().__init__(message)


class LockBusyError(RuntimeError):
    pass


class ProcessLock:
    def __init__(self, path: Path, *, stale_after: timedelta) -> None:
        self.path = path
        self.stale_after = stale_after
        self._fd: int | None = None
        self.owner_token: str | None = None

    def __enter__(self) -> ProcessLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if _legacy_lock_is_active(self.path):
            raise LockBusyError(
                f"Another appointment check is already running: {self.path} "
                f"({_read_lock_description(self.path)})"
            )
        self._fd = os.open(str(self.path), os.O_CREAT | os.O_RDWR)
        try:
            _lock_file_descriptor(self._fd)
        except OSError as exc:
            os.close(self._fd)
            self._fd = None
            owner = _read_lock_description(self.path)
            raise LockBusyError(
                f"Another appointment check is already running: {self.path} ({owner})"
            ) from exc

        self.owner_token = uuid.uuid4().hex
        payload = (
            f"pid={os.getpid()}\n"
            f"owner_token={self.owner_token}\n"
            f"created_at={datetime.now().isoformat()}\n"
        )
        os.lseek(self._fd, 0, os.SEEK_SET)
        os.ftruncate(self._fd, 0)
        os.write(self._fd, payload.encode("utf-8"))
        os.fsync(self._fd)
        logger.info("Acquired run lock: %s", self.path)
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self._fd is not None:
            try:
                _unlock_file_descriptor(self._fd)
            finally:
                os.close(self._fd)
            self._fd = None
        logger.info("Released run lock: %s", self.path)


def sleep_with_jitter(settings: Settings) -> None:
    if settings.run_jitter_max_seconds == 0:
        return

    delay = random.randint(settings.run_jitter_min_seconds, settings.run_jitter_max_seconds)
    if delay <= 0:
        return

    logger.info("Sleeping %s seconds before run jitter", delay)
    time.sleep(delay)


@contextmanager
def single_run_lock(settings: Settings) -> Iterator[ProcessLock]:
    lock = ProcessLock(
        settings.state_dir / "appointment_bot.lock",
        stale_after=timedelta(minutes=settings.lock_stale_minutes),
    )
    with lock:
        yield lock


@contextmanager
def run_timeout(settings: Settings) -> Iterator[None]:
    if hasattr(signal, "SIGALRM") and threading.current_thread() is threading.main_thread():
        with _signal_timeout(settings.run_timeout_seconds):
            yield
        return

    logger.debug(
        "Global run timeout is unavailable in this thread; operation-level timeouts apply."
    )
    yield


@contextmanager
def _signal_timeout(timeout_seconds: int) -> Iterator[None]:
    def _handle_timeout(signum, frame) -> None:
        raise RunTimeoutError(f"Run exceeded {timeout_seconds} seconds")

    previous_handler = signal.signal(signal.SIGALRM, _handle_timeout)
    signal.alarm(timeout_seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)


def _read_lock_pid(path: Path) -> int | None:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("pid="):
                return int(line.removeprefix("pid="))
    except (OSError, ValueError):
        return None
    return None


def _read_lock_description(path: Path) -> str:
    try:
        values = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator:
                values[key] = value
        pid = values.get("pid", "unknown")
        created_at = values.get("created_at", "unknown")
        return f"pid={pid}, created_at={created_at}"
    except OSError:
        return "owner unavailable"


def _legacy_lock_is_active(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return False
    if "owner_token=" in content:
        return False
    owner_pid = _read_lock_pid(path)
    return owner_pid is not None and _process_is_running(owner_pid)


def _lock_file_descriptor(fd: int) -> None:
    if os.name == "nt":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"\0")
            os.fsync(fd)
            os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        return

    import fcntl

    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file_descriptor(fd: int) -> None:
    if os.name == "nt":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(fd, fcntl.LOCK_UN)


def _process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True

    if os.name == "nt":
        return _windows_process_is_running(pid)

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _windows_process_is_running(pid: int) -> bool:
    from ctypes import POINTER, WinDLL, byref, get_last_error
    from ctypes.wintypes import BOOL, DWORD, HANDLE

    process_query_limited_information = 0x1000
    still_active = 259
    error_access_denied = 5
    kernel32 = WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [DWORD, BOOL, DWORD]
    kernel32.OpenProcess.restype = HANDLE
    kernel32.GetExitCodeProcess.argtypes = [HANDLE, POINTER(DWORD)]
    kernel32.GetExitCodeProcess.restype = BOOL
    kernel32.CloseHandle.argtypes = [HANDLE]
    kernel32.CloseHandle.restype = BOOL
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return get_last_error() == error_access_denied
    try:
        exit_code = DWORD()
        if not kernel32.GetExitCodeProcess(handle, byref(exit_code)):
            return True
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


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
