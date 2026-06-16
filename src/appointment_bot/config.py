import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None or value == "":
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False

    raise ValueError(f"Invalid boolean value: {value!r}")


def _parse_int(value: str | None, *, default: int, minimum: int | None = None) -> int:
    if value is None or value == "":
        return default

    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"Invalid integer value: {value!r}") from exc

    if minimum is not None and parsed < minimum:
        raise ValueError(f"Integer value must be greater than or equal to {minimum}: {value!r}")

    return parsed


def _parse_int_list(value: str | None, *, default: tuple[int, ...]) -> tuple[int, ...]:
    if value is None or value.strip() == "":
        return default
    try:
        parsed = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid integer list value: {value!r}") from exc
    if not parsed or any(item < 0 for item in parsed):
        raise ValueError(f"Integer list must contain non-negative values: {value!r}")
    return parsed


@dataclass(frozen=True)
class Settings:
    target_url: str
    login_username: str
    login_password: str
    captcha_api_key: str
    headless: bool
    block_heavy_assets: bool
    auto_reserve: bool
    screenshot_on_error: bool
    screenshot_on_relevant_result: bool
    screenshot_device_scale_factor: int
    debug_snapshots: bool
    log_level: str
    telegram_enabled: bool
    telegram_bot_token: str
    telegram_chat_id: str
    telegram_notify_unavailable: bool
    cleanup_retention_days: int
    run_jitter_min_seconds: int
    run_jitter_max_seconds: int
    run_timeout_seconds: int
    lock_stale_minutes: int
    error_backoff_threshold: int
    error_backoff_seconds: int
    monitor_window_seconds: int
    monitor_max_attempts: int
    monitor_interval_min_seconds: int
    monitor_interval_max_seconds: int
    queue_max_reservations_per_run: int
    queue_delay_min_seconds: int
    queue_delay_max_seconds: int
    heartbeat_enabled: bool
    heartbeat_interval_hours: int
    continuous_worker_enabled: bool
    continuous_interval_min_seconds: int
    continuous_interval_max_seconds: int
    session_rotation_seconds: int
    session_retry_delays_seconds: tuple[int, ...]
    login_timeout_seconds: int
    postback_timeout_seconds: int
    read_timeout_seconds: int
    reservation_timeout_seconds: int
    database_path: Path
    logs_dir: Path
    screenshots_dir: Path
    diagnostics_dir: Path
    state_dir: Path

    @property
    def safe_username(self) -> str:
        if not self.login_username:
            return "<empty>"
        if len(self.login_username) <= 3:
            return "***"
        return f"{self.login_username[:2]}***{self.login_username[-1]}"


def load_settings(*, require_login: bool = True) -> Settings:
    load_dotenv()

    settings = Settings(
        target_url=os.getenv("TARGET_URL", "").strip(),
        login_username=os.getenv("LOGIN_USERNAME", "").strip(),
        login_password=os.getenv("LOGIN_PASSWORD", ""),
        captcha_api_key=os.getenv("APIKEY_2CAPTCHA", "").strip(),
        headless=_parse_bool(os.getenv("HEADLESS"), default=False),
        block_heavy_assets=_parse_bool(os.getenv("BLOCK_HEAVY_ASSETS"), default=True),
        auto_reserve=_parse_bool(os.getenv("AUTO_RESERVE"), default=True),
        screenshot_on_error=_parse_bool(os.getenv("SCREENSHOT_ON_ERROR"), default=True),
        screenshot_on_relevant_result=_parse_bool(
            os.getenv("SCREENSHOT_ON_RELEVANT_RESULT"),
            default=True,
        ),
        screenshot_device_scale_factor=_parse_int(
            os.getenv("SCREENSHOT_DEVICE_SCALE_FACTOR"),
            default=2,
            minimum=1,
        ),
        debug_snapshots=_parse_bool(os.getenv("DEBUG_SNAPSHOTS"), default=False),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
        telegram_enabled=_parse_bool(os.getenv("TELEGRAM_ENABLED"), default=False),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        telegram_notify_unavailable=_parse_bool(
            os.getenv("TELEGRAM_NOTIFY_UNAVAILABLE"),
            default=False,
        ),
        cleanup_retention_days=_parse_int(
            os.getenv("CLEANUP_RETENTION_DAYS"),
            default=14,
            minimum=1,
        ),
        run_jitter_min_seconds=_parse_int(
            os.getenv("RUN_JITTER_MIN_SECONDS"),
            default=0,
            minimum=0,
        ),
        run_jitter_max_seconds=_parse_int(
            os.getenv("RUN_JITTER_MAX_SECONDS"),
            default=0,
            minimum=0,
        ),
        run_timeout_seconds=_parse_int(
            os.getenv("RUN_TIMEOUT_SECONDS"),
            default=420,
            minimum=30,
        ),
        lock_stale_minutes=_parse_int(
            os.getenv("LOCK_STALE_MINUTES"),
            default=10,
            minimum=1,
        ),
        error_backoff_threshold=_parse_int(
            os.getenv("ERROR_BACKOFF_THRESHOLD"),
            default=3,
            minimum=1,
        ),
        error_backoff_seconds=_parse_int(
            os.getenv("ERROR_BACKOFF_SECONDS"),
            default=1800,
            minimum=60,
        ),
        monitor_window_seconds=_parse_int(
            os.getenv("MONITOR_WINDOW_SECONDS"),
            default=300,
            minimum=0,
        ),
        monitor_max_attempts=_parse_int(
            os.getenv("MONITOR_MAX_ATTEMPTS"),
            default=4,
            minimum=1,
        ),
        monitor_interval_min_seconds=_parse_int(
            os.getenv("MONITOR_INTERVAL_MIN_SECONDS"),
            default=80,
            minimum=1,
        ),
        monitor_interval_max_seconds=_parse_int(
            os.getenv("MONITOR_INTERVAL_MAX_SECONDS"),
            default=100,
            minimum=1,
        ),
        queue_max_reservations_per_run=_parse_int(
            os.getenv("QUEUE_MAX_RESERVATIONS_PER_RUN"),
            default=0,
            minimum=0,
        ),
        queue_delay_min_seconds=_parse_int(
            os.getenv("QUEUE_DELAY_MIN_SECONDS"),
            default=5,
            minimum=0,
        ),
        queue_delay_max_seconds=_parse_int(
            os.getenv("QUEUE_DELAY_MAX_SECONDS"),
            default=15,
            minimum=0,
        ),
        heartbeat_enabled=_parse_bool(os.getenv("HEARTBEAT_ENABLED"), default=False),
        heartbeat_interval_hours=_parse_int(
            os.getenv("HEARTBEAT_INTERVAL_HOURS"),
            default=24,
            minimum=1,
        ),
        continuous_worker_enabled=_parse_bool(
            os.getenv("CONTINUOUS_WORKER_ENABLED"),
            default=False,
        ),
        continuous_interval_min_seconds=_parse_int(
            os.getenv("CONTINUOUS_INTERVAL_MIN_SECONDS"),
            default=45,
            minimum=1,
        ),
        continuous_interval_max_seconds=_parse_int(
            os.getenv("CONTINUOUS_INTERVAL_MAX_SECONDS"),
            default=75,
            minimum=1,
        ),
        session_rotation_seconds=_parse_int(
            os.getenv("SESSION_ROTATION_SECONDS"),
            default=1500,
            minimum=60,
        ),
        session_retry_delays_seconds=_parse_int_list(
            os.getenv("SESSION_RETRY_DELAYS_SECONDS"),
            default=(10, 30, 60),
        ),
        login_timeout_seconds=_parse_int(
            os.getenv("LOGIN_TIMEOUT_SECONDS"),
            default=60,
            minimum=10,
        ),
        postback_timeout_seconds=_parse_int(
            os.getenv("POSTBACK_TIMEOUT_SECONDS"),
            default=30,
            minimum=5,
        ),
        read_timeout_seconds=_parse_int(
            os.getenv("READ_TIMEOUT_SECONDS"),
            default=15,
            minimum=5,
        ),
        reservation_timeout_seconds=_parse_int(
            os.getenv("RESERVATION_TIMEOUT_SECONDS"),
            default=180,
            minimum=30,
        ),
        database_path=Path(os.getenv("DATABASE_PATH", "data/appointment_bot.sqlite")),
        logs_dir=Path("logs"),
        screenshots_dir=Path("screenshots"),
        diagnostics_dir=Path("diagnostics"),
        state_dir=Path("state"),
    )

    if settings.run_jitter_max_seconds < settings.run_jitter_min_seconds:
        raise ValueError(
            "RUN_JITTER_MAX_SECONDS must be greater than or equal to RUN_JITTER_MIN_SECONDS"
        )

    if settings.monitor_interval_max_seconds < settings.monitor_interval_min_seconds:
        raise ValueError(
            "MONITOR_INTERVAL_MAX_SECONDS must be greater than or equal to "
            "MONITOR_INTERVAL_MIN_SECONDS"
        )

    # El timeout necesita margen para login, captcha, capturas y cierre.
    if (
        settings.monitor_window_seconds > 0
        and settings.run_timeout_seconds < settings.monitor_window_seconds + 60
    ):
        raise ValueError(
            "RUN_TIMEOUT_SECONDS must be at least 60 seconds greater than MONITOR_WINDOW_SECONDS"
        )

    if settings.queue_delay_max_seconds < settings.queue_delay_min_seconds:
        raise ValueError(
            "QUEUE_DELAY_MAX_SECONDS must be greater than or equal to QUEUE_DELAY_MIN_SECONDS"
        )

    if settings.continuous_interval_max_seconds < settings.continuous_interval_min_seconds:
        raise ValueError(
            "CONTINUOUS_INTERVAL_MAX_SECONDS must be greater than or equal to "
            "CONTINUOUS_INTERVAL_MIN_SECONDS"
        )

    missing = [
        name
        for name, value in {
            "TARGET_URL": settings.target_url,
            "LOGIN_USERNAME": settings.login_username,
            "LOGIN_PASSWORD": settings.login_password,
        }.items()
        if not value and (require_login or name == "TARGET_URL")
    ]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"Missing required environment variables: {joined}")

    if settings.telegram_enabled:
        telegram_missing = [
            name
            for name, value in {
                "TELEGRAM_BOT_TOKEN": settings.telegram_bot_token,
                "TELEGRAM_CHAT_ID": settings.telegram_chat_id,
            }.items()
            if not value
        ]
        if telegram_missing:
            joined = ", ".join(telegram_missing)
            raise ValueError(f"Missing required Telegram environment variables: {joined}")

    return settings
