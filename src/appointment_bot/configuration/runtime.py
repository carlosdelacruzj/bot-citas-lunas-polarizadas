from dataclasses import dataclass
from datetime import time as datetime_time
from pathlib import Path


@dataclass(frozen=True)
class RuntimeSettings:
    headless: bool
    block_heavy_assets: bool
    log_level: str
    error_backoff_seconds: int
    queue_max_reservations_per_run: int
    queue_delay_min_seconds: int
    queue_delay_max_seconds: int
    continuous_worker_enabled: bool
    worker_embedded_api_enabled: bool
    worker_progress_grace_seconds: int
    final_ready_review_enabled: bool
    worker_daily_cutoff_time: datetime_time
    observer_session_seconds: int
    observer_max_attempts: int
    observer_interval_min_seconds: int
    observer_interval_max_seconds: int
    observer_site_toggle_enabled: bool
    observer_site_toggle_attempts: int
    observer_site_toggle_interval_min_seconds: int
    observer_site_toggle_interval_max_seconds: int
    observer_reload_probe_after_attempt: int
    observer_active_order_limit: int
    opportunity_handoff_max_candidates: int
    opportunity_handoff_max_seconds: int
    opportunity_burst_max_sessions: int
    opportunity_burst_max_clients: int
    opportunity_burst_max_seconds: int
    opportunity_burst_session_seconds: int
    opportunity_burst_attempts: int
    opportunity_burst_reload_probe_after_attempt: int
    slot_lost_reobservation_seconds: int
    slot_lost_reobservation_attempts: int
    slot_lost_reobservation_reload_probe_after_attempt: int
    observer_required_site: str
    observer_hot_windows: tuple[tuple[datetime_time, datetime_time], ...]
    observer_hot_window_extension_seconds: int
    outside_hot_window_min_seconds: int
    outside_hot_window_max_seconds: int
    unavailable_streak_limit: int
    recovery_backoff_min_seconds: int
    recovery_backoff_max_seconds: int
    database_url: str
    logs_dir: Path
    credential_encryption_keys: tuple[str, ...]
