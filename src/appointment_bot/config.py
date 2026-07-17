import os
from dataclasses import dataclass
from datetime import time as datetime_time
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


def _parse_evidence_profile(value: str | None) -> str:
    profile = (value or "custom").strip().lower()
    if not profile:
        return "custom"
    if profile not in {"custom", "fast", "diagnostic"}:
        raise ValueError("EVIDENCE_PROFILE must be custom, fast, or diagnostic.")
    return profile


def _parse_time_windows(
    value: str | None,
    *,
    default: tuple[tuple[datetime_time, datetime_time], ...],
) -> tuple[tuple[datetime_time, datetime_time], ...]:
    if value is None or value.strip() == "":
        return default

    windows = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            start_text, end_text = (part.strip() for part in item.split("-", maxsplit=1))
            start = datetime_time.fromisoformat(start_text)
            end = datetime_time.fromisoformat(end_text)
        except ValueError as exc:
            raise ValueError(
                f"Invalid time window. Use HH:MM-HH:MM entries separated by commas: {value!r}"
            ) from exc
        if start >= end:
            raise ValueError(f"Time window start must be before end: {item!r}")
        windows.append((start, end))

    return tuple(windows)


DEFAULT_OBSERVER_HOT_WINDOWS = (
    (datetime_time(hour=8, minute=15), datetime_time(hour=8, minute=50)),
    (datetime_time(hour=9, minute=30), datetime_time(hour=10, minute=0)),
    (datetime_time(hour=11, minute=40), datetime_time(hour=12, minute=40)),
    (datetime_time(hour=15, minute=55), datetime_time(hour=16, minute=30)),
)


@dataclass(frozen=True)
class Settings:
    target_url: str
    login_username: str
    login_password: str
    login_document_type: str
    captcha_api_key: str
    headless: bool
    block_heavy_assets: bool
    auto_reserve: bool
    screenshot_on_error: bool
    screenshot_on_relevant_result: bool
    screenshot_device_scale_factor: int
    client_video_width: int
    client_video_height: int
    record_client_sessions: bool
    record_client_video_final_mp4: bool
    evidence_profile: str
    log_level: str
    telegram_enabled: bool
    telegram_bot_token: str
    telegram_chat_id: str
    telegram_notify_unavailable: bool
    cleanup_retention_days: int
    error_backoff_seconds: int
    order_rule_cooldown_seconds: int
    monitor_window_seconds: int
    monitor_max_attempts: int
    monitor_interval_min_seconds: int
    monitor_interval_max_seconds: int
    queue_max_reservations_per_run: int
    queue_delay_min_seconds: int
    queue_delay_max_seconds: int
    continuous_worker_enabled: bool
    continuous_interval_min_seconds: int
    continuous_interval_max_seconds: int
    final_ready_review_enabled: bool
    session_rotation_seconds: int
    observer_session_seconds: int
    observer_max_attempts: int
    observer_interval_min_seconds: int
    observer_interval_max_seconds: int
    observer_active_order_limit: int
    observer_required_site: str
    observer_hot_windows: tuple[tuple[datetime_time, datetime_time], ...]
    observer_hot_window_extension_seconds: int
    outside_hot_window_min_seconds: int
    outside_hot_window_max_seconds: int
    unavailable_streak_limit: int
    recovery_backoff_min_seconds: int
    recovery_backoff_max_seconds: int
    session_retry_delays_seconds: tuple[int, ...]
    login_timeout_seconds: int
    postback_timeout_seconds: int
    read_timeout_seconds: int
    reservation_timeout_seconds: int
    database_url: str
    logs_dir: Path
    screenshots_dir: Path
    client_videos_dir: Path
    credential_encryption_keys: tuple[str, ...] = ()
    artifact_prefix: str = ""

    @property
    def safe_username(self) -> str:
        if not self.login_username:
            return "<empty>"
        if len(self.login_username) <= 3:
            return "***"
        return f"{self.login_username[:2]}***{self.login_username[-1]}"


def load_settings(*, require_login: bool = True) -> Settings:
    load_dotenv()

    evidence_profile = _parse_evidence_profile(os.getenv("EVIDENCE_PROFILE"))
    screenshot_on_error = _parse_bool(os.getenv("SCREENSHOT_ON_ERROR"), default=True)
    screenshot_on_relevant_result = _parse_bool(
        os.getenv("SCREENSHOT_ON_RELEVANT_RESULT"),
        default=True,
    )
    record_client_sessions = _parse_bool(
        os.getenv("RECORD_CLIENT_SESSIONS"),
        default=False,
    )
    record_client_video_final_mp4 = _parse_bool(
        os.getenv("RECORD_CLIENT_VIDEO_FINAL_MP4"),
        default=True,
    )
    if evidence_profile == "fast":
        record_client_sessions = False
        record_client_video_final_mp4 = False
        screenshot_on_relevant_result = False
    elif evidence_profile == "diagnostic":
        record_client_sessions = True
        record_client_video_final_mp4 = True
        screenshot_on_relevant_result = True
        screenshot_on_error = True

    settings = Settings(
        target_url=os.getenv("TARGET_URL", "").strip(),
        login_username=os.getenv("LOGIN_USERNAME", "").strip(),
        login_password=os.getenv("LOGIN_PASSWORD", ""),
        login_document_type=os.getenv("LOGIN_DOCUMENT_TYPE", "dni").strip() or "dni",
        captcha_api_key=os.getenv("APIKEY_2CAPTCHA", "").strip(),
        headless=_parse_bool(os.getenv("HEADLESS"), default=False),
        block_heavy_assets=_parse_bool(os.getenv("BLOCK_HEAVY_ASSETS"), default=True),
        auto_reserve=_parse_bool(os.getenv("AUTO_RESERVE"), default=True),
        screenshot_on_error=screenshot_on_error,
        screenshot_on_relevant_result=screenshot_on_relevant_result,
        screenshot_device_scale_factor=_parse_int(
            os.getenv("SCREENSHOT_DEVICE_SCALE_FACTOR"),
            default=2,
            minimum=1,
        ),
        client_video_width=_parse_int(
            os.getenv("CLIENT_VIDEO_WIDTH"),
            default=1920,
            minimum=320,
        ),
        client_video_height=_parse_int(
            os.getenv("CLIENT_VIDEO_HEIGHT"),
            default=1080,
            minimum=240,
        ),
        record_client_sessions=record_client_sessions,
        record_client_video_final_mp4=record_client_video_final_mp4,
        evidence_profile=evidence_profile,
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
        error_backoff_seconds=_parse_int(
            os.getenv("ERROR_BACKOFF_SECONDS"),
            default=1800,
            minimum=60,
        ),
        order_rule_cooldown_seconds=_parse_int(
            os.getenv("ORDER_RULE_COOLDOWN_SECONDS"),
            default=900,
            minimum=0,
        ),
        monitor_window_seconds=_parse_int(
            os.getenv("MONITOR_WINDOW_SECONDS"),
            default=120,
            minimum=0,
        ),
        monitor_max_attempts=_parse_int(
            os.getenv("MONITOR_MAX_ATTEMPTS"),
            default=4,
            minimum=1,
        ),
        monitor_interval_min_seconds=_parse_int(
            os.getenv("MONITOR_INTERVAL_MIN_SECONDS"),
            default=25,
            minimum=1,
        ),
        monitor_interval_max_seconds=_parse_int(
            os.getenv("MONITOR_INTERVAL_MAX_SECONDS"),
            default=35,
            minimum=1,
        ),
        queue_max_reservations_per_run=_parse_int(
            os.getenv("QUEUE_MAX_RESERVATIONS_PER_RUN"),
            default=1,
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
        continuous_worker_enabled=_parse_bool(
            os.getenv("CONTINUOUS_WORKER_ENABLED"),
            default=False,
        ),
        continuous_interval_min_seconds=_parse_int(
            os.getenv("CONTINUOUS_INTERVAL_MIN_SECONDS"),
            default=30,
            minimum=1,
        ),
        continuous_interval_max_seconds=_parse_int(
            os.getenv("CONTINUOUS_INTERVAL_MAX_SECONDS"),
            default=55,
            minimum=1,
        ),
        final_ready_review_enabled=_parse_bool(
            os.getenv("FINAL_READY_REVIEW_ENABLED"),
            default=True,
        ),
        session_rotation_seconds=_parse_int(
            os.getenv("SESSION_ROTATION_SECONDS"),
            default=1500,
            minimum=60,
        ),
        observer_session_seconds=_parse_int(
            os.getenv("OBSERVER_SESSION_SECONDS"),
            default=120,
            minimum=60,
        ),
        observer_max_attempts=_parse_int(
            os.getenv("OBSERVER_MAX_ATTEMPTS"),
            default=4,
            minimum=1,
        ),
        observer_interval_min_seconds=_parse_int(
            os.getenv("OBSERVER_INTERVAL_MIN_SECONDS"),
            default=25,
            minimum=1,
        ),
        observer_interval_max_seconds=_parse_int(
            os.getenv("OBSERVER_INTERVAL_MAX_SECONDS"),
            default=35,
            minimum=1,
        ),
        observer_active_order_limit=_parse_int(
            os.getenv("OBSERVER_ACTIVE_ORDER_LIMIT"),
            default=2,
            minimum=1,
        ),
        observer_required_site=os.getenv("OBSERVER_REQUIRED_SITE", "LIMA-LA VICTORIA").strip(),
        observer_hot_windows=_parse_time_windows(
            os.getenv("OBSERVER_HOT_WINDOWS"),
            default=DEFAULT_OBSERVER_HOT_WINDOWS,
        ),
        observer_hot_window_extension_seconds=_parse_int(
            os.getenv("OBSERVER_HOT_WINDOW_EXTENSION_SECONDS"),
            default=900,
            minimum=0,
        ),
        outside_hot_window_min_seconds=_parse_int(
            os.getenv("OUTSIDE_HOT_WINDOW_MIN_SECONDS"),
            default=1200,
            minimum=60,
        ),
        outside_hot_window_max_seconds=_parse_int(
            os.getenv("OUTSIDE_HOT_WINDOW_MAX_SECONDS"),
            default=2400,
            minimum=60,
        ),
        unavailable_streak_limit=_parse_int(
            os.getenv("UNAVAILABLE_STREAK_LIMIT"),
            default=8,
            minimum=0,
        ),
        recovery_backoff_min_seconds=_parse_int(
            os.getenv("RECOVERY_BACKOFF_MIN_SECONDS"),
            default=1800,
            minimum=60,
        ),
        recovery_backoff_max_seconds=_parse_int(
            os.getenv("RECOVERY_BACKOFF_MAX_SECONDS"),
            default=3600,
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
        database_url=os.getenv("APPOINTMENT_DATABASE_URL", "").strip(),
        logs_dir=Path("logs"),
        screenshots_dir=Path("screenshots"),
        client_videos_dir=Path(
            os.getenv("RECORD_CLIENT_VIDEO_DIR", "videos/reservations").strip()
            or "videos/reservations"
        ),
        credential_encryption_keys=tuple(
            key.strip()
            for key in os.getenv("APPOINTMENT_CREDENTIAL_KEYS", "").split(",")
            if key.strip()
        ),
    )

    if settings.monitor_interval_max_seconds < settings.monitor_interval_min_seconds:
        raise ValueError(
            "MONITOR_INTERVAL_MAX_SECONDS must be greater than or equal to "
            "MONITOR_INTERVAL_MIN_SECONDS"
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

    if settings.observer_interval_max_seconds < settings.observer_interval_min_seconds:
        raise ValueError(
            "OBSERVER_INTERVAL_MAX_SECONDS must be greater than or equal to "
            "OBSERVER_INTERVAL_MIN_SECONDS"
        )

    if settings.outside_hot_window_max_seconds < settings.outside_hot_window_min_seconds:
        raise ValueError(
            "OUTSIDE_HOT_WINDOW_MAX_SECONDS must be greater than or equal to "
            "OUTSIDE_HOT_WINDOW_MIN_SECONDS"
        )

    if settings.recovery_backoff_max_seconds < settings.recovery_backoff_min_seconds:
        raise ValueError(
            "RECOVERY_BACKOFF_MAX_SECONDS must be greater than or equal to "
            "RECOVERY_BACKOFF_MIN_SECONDS"
        )

    missing = [
        name
        for name, value in {
            "TARGET_URL": settings.target_url,
            "APPOINTMENT_DATABASE_URL": settings.database_url,
            "LOGIN_USERNAME": settings.login_username,
            "LOGIN_PASSWORD": settings.login_password,
        }.items()
        if not value and (require_login or name in {"TARGET_URL", "APPOINTMENT_DATABASE_URL"})
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
