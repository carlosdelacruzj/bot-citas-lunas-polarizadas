"""Public reservation-engine facade for the migration target package."""

from appointment_bot.reservation_engine.flow import execute_session_flow, run_with_report
from appointment_bot.reservation_engine.portal import (
    InvalidPortalCredentials,
    click_program_action,
    login,
    open_appointment_panel,
    open_hidden_appointment_panel_for_observer,
    select_available_site,
    select_available_site_for_observer,
)
from appointment_bot.reservation_engine.submit import (
    capture_blocked_captcha_evidence,
    complete_available_reservation,
)

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
