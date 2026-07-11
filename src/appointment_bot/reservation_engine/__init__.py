"""Public reservation-engine facade for the migration target package."""

from importlib import import_module
from typing import Any

__all__ = [
    "InvalidPortalCredentials",
    "capture_blocked_captcha_evidence",
    "click_program_action",
    "complete_available_reservation",
    "execute_session_flow",
    "login",
    "open_appointment_panel",
    "open_hidden_appointment_panel_for_observer",
    "run_with_report",
    "select_available_site",
    "select_available_site_for_observer",
]

_EXPORT_MODULES = {
    "InvalidPortalCredentials": "appointment_bot.reservation_engine.portal",
    "capture_blocked_captcha_evidence": "appointment_bot.reservation_engine.submit",
    "click_program_action": "appointment_bot.reservation_engine.portal",
    "complete_available_reservation": "appointment_bot.reservation_engine.submit",
    "execute_session_flow": "appointment_bot.reservation_engine.flow",
    "login": "appointment_bot.reservation_engine.portal",
    "open_appointment_panel": "appointment_bot.reservation_engine.portal",
    "open_hidden_appointment_panel_for_observer": "appointment_bot.reservation_engine.portal",
    "run_with_report": "appointment_bot.reservation_engine.flow",
    "select_available_site": "appointment_bot.reservation_engine.portal",
    "select_available_site_for_observer": "appointment_bot.reservation_engine.portal",
}


def __getattr__(name: str) -> Any:
    if name not in _EXPORT_MODULES:
        raise AttributeError(name)
    module = import_module(_EXPORT_MODULES[name])
    value = getattr(module, name)
    globals()[name] = value
    return value
