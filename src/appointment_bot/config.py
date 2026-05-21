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


@dataclass(frozen=True)
class Settings:
    target_url: str
    login_username: str
    login_password: str
    headless: bool
    block_heavy_assets: bool
    screenshot_on_error: bool
    screenshot_on_relevant_result: bool
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
    heartbeat_enabled: bool
    heartbeat_interval_hours: int
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


def load_settings() -> Settings:
    load_dotenv()

    settings = Settings(
        target_url=os.getenv("TARGET_URL", "").strip(),
        login_username=os.getenv("LOGIN_USERNAME", "").strip(),
        login_password=os.getenv("LOGIN_PASSWORD", ""),
        headless=_parse_bool(os.getenv("HEADLESS"), default=False),
        block_heavy_assets=_parse_bool(os.getenv("BLOCK_HEAVY_ASSETS"), default=True),
        screenshot_on_error=_parse_bool(os.getenv("SCREENSHOT_ON_ERROR"), default=True),
        screenshot_on_relevant_result=_parse_bool(
            os.getenv("SCREENSHOT_ON_RELEVANT_RESULT"),
            default=True,
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
            default=180,
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
        heartbeat_enabled=_parse_bool(os.getenv("HEARTBEAT_ENABLED"), default=False),
        heartbeat_interval_hours=_parse_int(
            os.getenv("HEARTBEAT_INTERVAL_HOURS"),
            default=24,
            minimum=1,
        ),
        logs_dir=Path("logs"),
        screenshots_dir=Path("screenshots"),
        diagnostics_dir=Path("diagnostics"),
        state_dir=Path("state"),
    )

    if settings.run_jitter_max_seconds < settings.run_jitter_min_seconds:
        raise ValueError(
            "RUN_JITTER_MAX_SECONDS must be greater than or equal to RUN_JITTER_MIN_SECONDS"
        )

    missing = [
        name
        for name, value in {
            "TARGET_URL": settings.target_url,
            "LOGIN_USERNAME": settings.login_username,
            "LOGIN_PASSWORD": settings.login_password,
        }.items()
        if not value
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
