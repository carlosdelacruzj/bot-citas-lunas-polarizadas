from dataclasses import dataclass, replace


@dataclass(frozen=True)
class ReservationSettings:
    target_url: str
    login_username: str
    login_password: str
    login_document_type: str
    auto_reserve: bool
    monitor_window_seconds: int
    monitor_max_attempts: int
    monitor_interval_min_seconds: int
    monitor_interval_max_seconds: int
    monitor_site_toggle_enabled: bool
    monitor_reload_probe_after_attempt: int
    session_retry_delays_seconds: tuple[int, ...]
    login_timeout_seconds: int
    postback_timeout_seconds: int
    read_timeout_seconds: int
    reservation_timeout_seconds: int

    @property
    def safe_username(self) -> str:
        if not self.login_username:
            return "<empty>"
        if len(self.login_username) <= 3:
            return "***"
        return f"{self.login_username[:2]}***{self.login_username[-1]}"


def settings_for_order(
    *,
    reservation_settings: ReservationSettings,
    username: str,
    password: str,
    document_type: str = "dni",
) -> ReservationSettings:
    return replace(
        reservation_settings,
        login_username=username,
        login_password=password,
        login_document_type=document_type,
    )
