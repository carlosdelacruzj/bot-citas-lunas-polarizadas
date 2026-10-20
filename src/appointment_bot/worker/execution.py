from __future__ import annotations

from dataclasses import replace

from appointment_bot.configuration.reservation import ReservationSettings, settings_for_order
from appointment_bot.configuration.runtime import RuntimeSettings
from appointment_bot.core.models import ServiceOrderCandidate, ServiceOrderRuntime


def continuous_order_settings(
    order: ServiceOrderCandidate | ServiceOrderRuntime,
    *,
    runtime_settings: RuntimeSettings,
    reservation_settings: ReservationSettings,
) -> ReservationSettings:
    order_settings = settings_for_order(
        reservation_settings=reservation_settings,
        username=order.username,
        password=getattr(order, "password", ""),
        document_type=order.document_type,
    )
    effective = continuous_settings(
        runtime_settings=runtime_settings, reservation_settings=order_settings
    )
    if not runtime_settings.observer_site_toggle_enabled:
        return effective
    return replace(
        effective,
        monitor_max_attempts=runtime_settings.observer_site_toggle_attempts,
        monitor_interval_min_seconds=runtime_settings.observer_site_toggle_interval_min_seconds,
        monitor_interval_max_seconds=runtime_settings.observer_site_toggle_interval_max_seconds,
        monitor_site_toggle_enabled=True,
        monitor_reload_probe_after_attempt=runtime_settings.observer_reload_probe_after_attempt,
    )


def continuous_settings(
    *, runtime_settings: RuntimeSettings, reservation_settings: ReservationSettings
) -> ReservationSettings:
    return replace(
        reservation_settings,
        monitor_window_seconds=runtime_settings.observer_session_seconds,
        monitor_max_attempts=runtime_settings.observer_max_attempts,
        monitor_interval_min_seconds=runtime_settings.observer_interval_min_seconds,
        monitor_interval_max_seconds=runtime_settings.observer_interval_max_seconds,
    )


def observer_confirmation_settings(
    *, runtime_settings: RuntimeSettings, reservation_settings: ReservationSettings
) -> ReservationSettings:
    return replace(
        continuous_settings(
            runtime_settings=runtime_settings, reservation_settings=reservation_settings
        ),
        monitor_window_seconds=0,
        monitor_max_attempts=1,
    )
