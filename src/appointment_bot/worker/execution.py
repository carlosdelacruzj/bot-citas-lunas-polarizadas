from __future__ import annotations

from dataclasses import replace

from appointment_bot.config import Settings
from appointment_bot.core.models import ServiceOrderCandidate, ServiceOrderRuntime
from appointment_bot.reports.run_reporting import settings_for_order


def continuous_order_settings(
    base_settings: Settings,
    order: ServiceOrderCandidate | ServiceOrderRuntime,
) -> Settings:
    order_settings = settings_for_order(
        base_settings,
        username=order.username,
        password=getattr(order, "password", ""),
        document_type=order.document_type,
    )
    return continuous_settings(order_settings)


def continuous_settings(settings: Settings) -> Settings:
    return replace(
        settings,
        telegram_notify_unavailable=False,
        monitor_window_seconds=settings.observer_session_seconds,
        monitor_max_attempts=settings.observer_max_attempts,
        monitor_interval_min_seconds=settings.observer_interval_min_seconds,
        monitor_interval_max_seconds=settings.observer_interval_max_seconds,
    )


def observer_confirmation_settings(settings: Settings) -> Settings:
    return replace(
        continuous_settings(settings),
        monitor_window_seconds=0,
        monitor_max_attempts=1,
    )
