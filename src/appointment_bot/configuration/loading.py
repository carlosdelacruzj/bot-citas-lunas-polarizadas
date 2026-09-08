import os
from datetime import time as datetime_time
from pathlib import Path

from dotenv import load_dotenv

from appointment_bot.configuration.captcha import CaptchaSettings
from appointment_bot.configuration.evidence import EvidenceSettings
from appointment_bot.configuration.parsers import (
    _parse_bool,
    _parse_evidence_profile,
    _parse_float,
    _parse_int,
    _parse_int_list,
    _parse_time,
    _parse_time_windows,
)
from appointment_bot.configuration.reservation import ReservationSettings
from appointment_bot.configuration.runtime import (
    DEFAULT_OBSERVER_HOT_WINDOWS,
    OPPORTUNITY_BURST_SESSION_LIMIT,
    RuntimeSettings,
)
from appointment_bot.configuration.telegram import TelegramSettings
from appointment_bot.configuration.whatsapp import WhatsappSettings


def load_settings(
    *, require_login: bool = True
) -> tuple[
    RuntimeSettings,
    ReservationSettings,
    CaptchaSettings,
    EvidenceSettings,
    TelegramSettings,
    WhatsappSettings,
]:
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

    values = dict(
        artifact_prefix="",
        reservation_captcha_runtime_control_enabled=True,
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
        captcha_rejection_cooldown_seconds=_parse_int(
            os.getenv("CAPTCHA_REJECTION_COOLDOWN_SECONDS"),
            default=120,
            minimum=0,
        ),
        reservation_captcha_max_attempts=_parse_int(
            os.getenv("RESERVATION_CAPTCHA_MAX_ATTEMPTS"),
            default=2,
            minimum=1,
        ),
        reservation_captcha_sample_limit=_parse_int(
            os.getenv("RESERVATION_CAPTCHA_SAMPLE_LIMIT"),
            default=1,
            minimum=1,
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
        monitor_site_toggle_enabled=False,
        monitor_reload_probe_after_attempt=1,
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
        worker_embedded_api_enabled=_parse_bool(
            os.getenv("WORKER_EMBEDDED_API_ENABLED"),
            default=True,
        ),
        worker_progress_grace_seconds=_parse_int(
            os.getenv("WORKER_PROGRESS_GRACE_SECONDS"),
            default=55,
            minimum=1,
        ),
        final_ready_review_enabled=_parse_bool(
            os.getenv("FINAL_READY_REVIEW_ENABLED"),
            default=True,
        ),
        worker_daily_cutoff_time=_parse_time(
            os.getenv("WORKER_DAILY_CUTOFF_TIME"),
            default=datetime_time(hour=18),
        ),
        appointment_reminders_time=_parse_time(
            os.getenv("APPOINTMENT_REMINDERS_TIME"),
            default=datetime_time(hour=18),
        ),
        appointment_reminders_summary_grace_minutes=_parse_int(
            os.getenv("APPOINTMENT_REMINDERS_SUMMARY_GRACE_MINUTES"),
            default=15,
            minimum=1,
        ),
        appointment_reminders_reconcile_seconds=_parse_int(
            os.getenv("APPOINTMENT_REMINDERS_RECONCILE_SECONDS"),
            default=60,
            minimum=10,
        ),
        appointment_reminders_send_interval_seconds=_parse_int(
            os.getenv("APPOINTMENT_REMINDERS_SEND_INTERVAL_SECONDS"),
            default=5,
            minimum=0,
        ),
        appointment_reminders_daily_limit=_parse_int(
            os.getenv("APPOINTMENT_REMINDERS_DAILY_LIMIT"),
            default=100,
            minimum=1,
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
        observer_captcha_sample_limit=_parse_int(
            os.getenv("OBSERVER_CAPTCHA_SAMPLE_LIMIT"),
            default=5,
            minimum=0,
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
        observer_site_toggle_enabled=_parse_bool(
            os.getenv("OBSERVER_SITE_TOGGLE_ENABLED"),
            default=True,
        ),
        observer_site_toggle_attempts=_parse_int(
            os.getenv("OBSERVER_SITE_TOGGLE_ATTEMPTS"),
            default=15,
            minimum=1,
        ),
        observer_site_toggle_interval_min_seconds=_parse_int(
            os.getenv("OBSERVER_SITE_TOGGLE_INTERVAL_MIN_SECONDS"),
            default=2,
            minimum=1,
        ),
        observer_site_toggle_interval_max_seconds=_parse_int(
            os.getenv("OBSERVER_SITE_TOGGLE_INTERVAL_MAX_SECONDS"),
            default=2,
            minimum=1,
        ),
        observer_reload_probe_after_attempt=_parse_int(
            os.getenv("OBSERVER_RELOAD_PROBE_AFTER_ATTEMPT"),
            default=8,
            minimum=1,
        ),
        observer_active_order_limit=_parse_int(
            os.getenv("OBSERVER_ACTIVE_ORDER_LIMIT"),
            default=2,
            minimum=1,
        ),
        opportunity_handoff_max_candidates=_parse_int(
            os.getenv("OPPORTUNITY_HANDOFF_MAX_CANDIDATES"),
            default=10,
            minimum=1,
        ),
        opportunity_handoff_max_seconds=_parse_int(
            os.getenv("OPPORTUNITY_HANDOFF_MAX_SECONDS"),
            default=300,
            minimum=1,
        ),
        opportunity_burst_max_sessions=_parse_int(
            os.getenv("OPPORTUNITY_BURST_MAX_SESSIONS"),
            default=OPPORTUNITY_BURST_SESSION_LIMIT,
            minimum=2,
        ),
        opportunity_burst_max_clients=_parse_int(
            os.getenv("OPPORTUNITY_BURST_MAX_CLIENTS"),
            default=0,
            minimum=0,
        ),
        opportunity_burst_max_seconds=_parse_int(
            os.getenv("OPPORTUNITY_BURST_MAX_SECONDS"),
            default=300,
            minimum=1,
        ),
        opportunity_burst_session_seconds=_parse_int(
            os.getenv("OPPORTUNITY_BURST_SESSION_SECONDS"),
            default=20,
            minimum=1,
        ),
        opportunity_burst_attempts=_parse_int(
            os.getenv("OPPORTUNITY_BURST_ATTEMPTS"),
            default=5,
            minimum=1,
        ),
        opportunity_burst_reload_probe_after_attempt=_parse_int(
            os.getenv("OPPORTUNITY_BURST_RELOAD_PROBE_AFTER_ATTEMPT"),
            default=3,
            minimum=1,
        ),
        slot_lost_reobservation_seconds=_parse_int(
            os.getenv("SLOT_LOST_REOBSERVATION_SECONDS"),
            default=12,
            minimum=1,
        ),
        slot_lost_reobservation_attempts=_parse_int(
            os.getenv("SLOT_LOST_REOBSERVATION_ATTEMPTS"),
            default=5,
            minimum=1,
        ),
        slot_lost_reobservation_reload_probe_after_attempt=_parse_int(
            os.getenv("SLOT_LOST_REOBSERVATION_RELOAD_PROBE_AFTER_ATTEMPT"),
            default=3,
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
        captcha_shadow_enabled=_parse_bool(
            os.getenv("CAPTCHA_SHADOW_ENABLED"),
            default=False,
        ),
        captcha_shadow_url=(
            os.getenv("CAPTCHA_SHADOW_URL", "http://127.0.0.1:8787").strip()
            or "http://127.0.0.1:8787"
        ),
        captcha_shadow_queue_size=_parse_int(
            os.getenv("CAPTCHA_SHADOW_QUEUE_SIZE"),
            default=100,
            minimum=1,
        ),
        captcha_shadow_timeout_seconds=_parse_int(
            os.getenv("CAPTCHA_SHADOW_TIMEOUT_SECONDS"),
            default=2,
            minimum=1,
        ),
        reservation_math_pre_submit_delay_min_seconds=_parse_float(
            os.getenv("RESERVATION_MATH_PRE_SUBMIT_DELAY_MIN_SECONDS"),
            default=1.0,
            minimum=0.0,
        ),
        reservation_math_pre_submit_delay_max_seconds=_parse_float(
            os.getenv("RESERVATION_MATH_PRE_SUBMIT_DELAY_MAX_SECONDS"),
            default=2.0,
            minimum=0.0,
        ),
    )

    if values["monitor_interval_max_seconds"] < values["monitor_interval_min_seconds"]:
        raise ValueError(
            "MONITOR_INTERVAL_MAX_SECONDS must be greater than or equal to "
            "MONITOR_INTERVAL_MIN_SECONDS"
        )

    if values["queue_delay_max_seconds"] < values["queue_delay_min_seconds"]:
        raise ValueError(
            "QUEUE_DELAY_MAX_SECONDS must be greater than or equal to QUEUE_DELAY_MIN_SECONDS"
        )

    if (
        values["reservation_math_pre_submit_delay_max_seconds"]
        < values["reservation_math_pre_submit_delay_min_seconds"]
    ):
        raise ValueError(
            "RESERVATION_MATH_PRE_SUBMIT_DELAY_MAX_SECONDS must be greater than or equal "
            "to RESERVATION_MATH_PRE_SUBMIT_DELAY_MIN_SECONDS"
        )

    if values["observer_interval_max_seconds"] < values["observer_interval_min_seconds"]:
        raise ValueError(
            "OBSERVER_INTERVAL_MAX_SECONDS must be greater than or equal to "
            "OBSERVER_INTERVAL_MIN_SECONDS"
        )

    if (
        values["observer_site_toggle_interval_max_seconds"]
        < values["observer_site_toggle_interval_min_seconds"]
    ):
        raise ValueError(
            "OBSERVER_SITE_TOGGLE_INTERVAL_MAX_SECONDS must be greater than or equal to "
            "OBSERVER_SITE_TOGGLE_INTERVAL_MIN_SECONDS"
        )

    if (
        values["observer_site_toggle_enabled"]
        and values["observer_reload_probe_after_attempt"] > values["observer_site_toggle_attempts"]
    ):
        raise ValueError(
            "OBSERVER_RELOAD_PROBE_AFTER_ATTEMPT must be less than or equal to "
            "OBSERVER_SITE_TOGGLE_ATTEMPTS"
        )

    if (
        values["opportunity_burst_max_clients"] != 0
        and values["opportunity_burst_max_clients"] < values["opportunity_burst_max_sessions"]
    ):
        raise ValueError(
            "OPPORTUNITY_BURST_MAX_CLIENTS must be 0 or greater than or equal to "
            "OPPORTUNITY_BURST_MAX_SESSIONS"
        )

    if values["opportunity_burst_max_sessions"] > OPPORTUNITY_BURST_SESSION_LIMIT:
        raise ValueError(
            "OPPORTUNITY_BURST_MAX_SESSIONS must remain between 2 and "
            f"{OPPORTUNITY_BURST_SESSION_LIMIT}"
        )

    if values["opportunity_burst_max_seconds"] > 300:
        raise ValueError("OPPORTUNITY_BURST_MAX_SECONDS must be less than or equal to 300")

    if values["opportunity_burst_session_seconds"] > 20:
        raise ValueError("OPPORTUNITY_BURST_SESSION_SECONDS must be less than or equal to 20")

    if values["opportunity_burst_attempts"] > 5:
        raise ValueError("OPPORTUNITY_BURST_ATTEMPTS must be less than or equal to 5")

    if (
        values["opportunity_burst_reload_probe_after_attempt"]
        > values["opportunity_burst_attempts"]
    ):
        raise ValueError(
            "OPPORTUNITY_BURST_RELOAD_PROBE_AFTER_ATTEMPT must be less than or equal "
            "to OPPORTUNITY_BURST_ATTEMPTS"
        )

    if values["slot_lost_reobservation_seconds"] > 30:
        raise ValueError("SLOT_LOST_REOBSERVATION_SECONDS must be less than or equal to 30")

    if values["slot_lost_reobservation_attempts"] > 10:
        raise ValueError("SLOT_LOST_REOBSERVATION_ATTEMPTS must be less than or equal to 10")

    if (
        values["slot_lost_reobservation_reload_probe_after_attempt"]
        > values["slot_lost_reobservation_attempts"]
    ):
        raise ValueError(
            "SLOT_LOST_REOBSERVATION_RELOAD_PROBE_AFTER_ATTEMPT must be less than or "
            "equal to SLOT_LOST_REOBSERVATION_ATTEMPTS"
        )

    if values["observer_captcha_sample_limit"] > 50:
        raise ValueError("OBSERVER_CAPTCHA_SAMPLE_LIMIT must be less than or equal to 50")

    if values["reservation_captcha_sample_limit"] > 50:
        raise ValueError("RESERVATION_CAPTCHA_SAMPLE_LIMIT must be less than or equal to 50")

    if values["outside_hot_window_max_seconds"] < values["outside_hot_window_min_seconds"]:
        raise ValueError(
            "OUTSIDE_HOT_WINDOW_MAX_SECONDS must be greater than or equal to "
            "OUTSIDE_HOT_WINDOW_MIN_SECONDS"
        )

    if values["recovery_backoff_max_seconds"] < values["recovery_backoff_min_seconds"]:
        raise ValueError(
            "RECOVERY_BACKOFF_MAX_SECONDS must be greater than or equal to "
            "RECOVERY_BACKOFF_MIN_SECONDS"
        )

    missing = [
        name
        for name, value in {
            "TARGET_URL": values["target_url"],
            "APPOINTMENT_DATABASE_URL": values["database_url"],
            "LOGIN_USERNAME": values["login_username"],
            "LOGIN_PASSWORD": values["login_password"],
        }.items()
        if not value and (require_login or name in {"TARGET_URL", "APPOINTMENT_DATABASE_URL"})
    ]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"Missing required environment variables: {joined}")

    if values["telegram_enabled"]:
        telegram_missing = [
            name
            for name, value in {
                "TELEGRAM_BOT_TOKEN": values["telegram_bot_token"],
                "TELEGRAM_CHAT_ID": values["telegram_chat_id"],
            }.items()
            if not value
        ]
        if telegram_missing:
            joined = ", ".join(telegram_missing)
            raise ValueError(f"Missing required Telegram environment variables: {joined}")

    return (
        RuntimeSettings(
            headless=values["headless"],
            block_heavy_assets=values["block_heavy_assets"],
            log_level=values["log_level"],
            error_backoff_seconds=values["error_backoff_seconds"],
            queue_max_reservations_per_run=values["queue_max_reservations_per_run"],
            queue_delay_min_seconds=values["queue_delay_min_seconds"],
            queue_delay_max_seconds=values["queue_delay_max_seconds"],
            continuous_worker_enabled=values["continuous_worker_enabled"],
            worker_embedded_api_enabled=values["worker_embedded_api_enabled"],
            worker_progress_grace_seconds=values["worker_progress_grace_seconds"],
            final_ready_review_enabled=values["final_ready_review_enabled"],
            worker_daily_cutoff_time=values["worker_daily_cutoff_time"],
            observer_session_seconds=values["observer_session_seconds"],
            observer_max_attempts=values["observer_max_attempts"],
            observer_interval_min_seconds=values["observer_interval_min_seconds"],
            observer_interval_max_seconds=values["observer_interval_max_seconds"],
            observer_site_toggle_enabled=values["observer_site_toggle_enabled"],
            observer_site_toggle_attempts=values["observer_site_toggle_attempts"],
            observer_site_toggle_interval_min_seconds=values[
                "observer_site_toggle_interval_min_seconds"
            ],
            observer_site_toggle_interval_max_seconds=values[
                "observer_site_toggle_interval_max_seconds"
            ],
            observer_reload_probe_after_attempt=values["observer_reload_probe_after_attempt"],
            observer_active_order_limit=values["observer_active_order_limit"],
            opportunity_handoff_max_candidates=values["opportunity_handoff_max_candidates"],
            opportunity_handoff_max_seconds=values["opportunity_handoff_max_seconds"],
            opportunity_burst_max_sessions=values["opportunity_burst_max_sessions"],
            opportunity_burst_max_clients=values["opportunity_burst_max_clients"],
            opportunity_burst_max_seconds=values["opportunity_burst_max_seconds"],
            opportunity_burst_session_seconds=values["opportunity_burst_session_seconds"],
            opportunity_burst_attempts=values["opportunity_burst_attempts"],
            opportunity_burst_reload_probe_after_attempt=values[
                "opportunity_burst_reload_probe_after_attempt"
            ],
            slot_lost_reobservation_seconds=values["slot_lost_reobservation_seconds"],
            slot_lost_reobservation_attempts=values["slot_lost_reobservation_attempts"],
            slot_lost_reobservation_reload_probe_after_attempt=values[
                "slot_lost_reobservation_reload_probe_after_attempt"
            ],
            observer_required_site=values["observer_required_site"],
            observer_hot_windows=values["observer_hot_windows"],
            observer_hot_window_extension_seconds=values["observer_hot_window_extension_seconds"],
            outside_hot_window_min_seconds=values["outside_hot_window_min_seconds"],
            outside_hot_window_max_seconds=values["outside_hot_window_max_seconds"],
            unavailable_streak_limit=values["unavailable_streak_limit"],
            recovery_backoff_min_seconds=values["recovery_backoff_min_seconds"],
            recovery_backoff_max_seconds=values["recovery_backoff_max_seconds"],
            database_url=values["database_url"],
            logs_dir=values["logs_dir"],
            credential_encryption_keys=values["credential_encryption_keys"],
        ),
        ReservationSettings(
            target_url=values["target_url"],
            login_username=values["login_username"],
            login_password=values["login_password"],
            login_document_type=values["login_document_type"],
            auto_reserve=values["auto_reserve"],
            monitor_window_seconds=values["monitor_window_seconds"],
            monitor_max_attempts=values["monitor_max_attempts"],
            monitor_interval_min_seconds=values["monitor_interval_min_seconds"],
            monitor_interval_max_seconds=values["monitor_interval_max_seconds"],
            monitor_site_toggle_enabled=values["monitor_site_toggle_enabled"],
            monitor_reload_probe_after_attempt=values["monitor_reload_probe_after_attempt"],
            session_retry_delays_seconds=values["session_retry_delays_seconds"],
            login_timeout_seconds=values["login_timeout_seconds"],
            postback_timeout_seconds=values["postback_timeout_seconds"],
            read_timeout_seconds=values["read_timeout_seconds"],
            reservation_timeout_seconds=values["reservation_timeout_seconds"],
        ),
        CaptchaSettings(
            captcha_api_key=values["captcha_api_key"],
            captcha_rejection_cooldown_seconds=values["captcha_rejection_cooldown_seconds"],
            reservation_captcha_max_attempts=values["reservation_captcha_max_attempts"],
            observer_captcha_sample_limit=values["observer_captcha_sample_limit"],
            captcha_shadow_enabled=values["captcha_shadow_enabled"],
            captcha_shadow_url=values["captcha_shadow_url"],
            captcha_shadow_queue_size=values["captcha_shadow_queue_size"],
            captcha_shadow_timeout_seconds=values["captcha_shadow_timeout_seconds"],
            reservation_captcha_sample_limit=values["reservation_captcha_sample_limit"],
            reservation_captcha_runtime_control_enabled=values[
                "reservation_captcha_runtime_control_enabled"
            ],
            reservation_math_pre_submit_delay_min_seconds=values[
                "reservation_math_pre_submit_delay_min_seconds"
            ],
            reservation_math_pre_submit_delay_max_seconds=values[
                "reservation_math_pre_submit_delay_max_seconds"
            ],
        ),
        EvidenceSettings(
            screenshot_on_error=values["screenshot_on_error"],
            screenshot_on_relevant_result=values["screenshot_on_relevant_result"],
            screenshot_device_scale_factor=values["screenshot_device_scale_factor"],
            client_video_width=values["client_video_width"],
            client_video_height=values["client_video_height"],
            record_client_sessions=values["record_client_sessions"],
            record_client_video_final_mp4=values["record_client_video_final_mp4"],
            cleanup_retention_days=values["cleanup_retention_days"],
            screenshots_dir=values["screenshots_dir"],
            client_videos_dir=values["client_videos_dir"],
            artifact_prefix=values["artifact_prefix"],
        ),
        TelegramSettings(
            telegram_enabled=values["telegram_enabled"],
            telegram_bot_token=values["telegram_bot_token"],
            telegram_chat_id=values["telegram_chat_id"],
            telegram_notify_unavailable=values["telegram_notify_unavailable"],
        ),
        WhatsappSettings(
            appointment_reminders_time=values["appointment_reminders_time"],
            appointment_reminders_summary_grace_minutes=values[
                "appointment_reminders_summary_grace_minutes"
            ],
            appointment_reminders_reconcile_seconds=values[
                "appointment_reminders_reconcile_seconds"
            ],
            appointment_reminders_send_interval_seconds=values[
                "appointment_reminders_send_interval_seconds"
            ],
            appointment_reminders_daily_limit=values["appointment_reminders_daily_limit"],
        ),
    )


def load_runtime_settings(*, require_login: bool = True) -> RuntimeSettings:
    return load_settings(require_login=require_login)[0]


def load_reservation_settings(*, require_login: bool = True) -> ReservationSettings:
    return load_settings(require_login=require_login)[1]


def load_captcha_settings(*, require_login: bool = True) -> CaptchaSettings:
    return load_settings(require_login=require_login)[2]


def load_evidence_settings(*, require_login: bool = True) -> EvidenceSettings:
    return load_settings(require_login=require_login)[3]


def load_telegram_settings(*, require_login: bool = True) -> TelegramSettings:
    return load_settings(require_login=require_login)[4]


def load_whatsapp_settings(*, require_login: bool = True) -> WhatsappSettings:
    return load_settings(require_login=require_login)[5]
