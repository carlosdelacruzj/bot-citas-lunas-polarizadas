"""Compatibility exports for portal navigation and selection steps."""

from appointment_bot.flows.appointments import (
    open_appointment_panel,
    open_hidden_appointment_panel_for_observer,
    select_available_site,
    select_available_site_for_observer,
)
from appointment_bot.flows.login import InvalidPortalCredentials, login
from appointment_bot.flows.programs import click_program_action

__all__ = [
    "InvalidPortalCredentials",
    "click_program_action",
    "login",
    "open_appointment_panel",
    "open_hidden_appointment_panel_for_observer",
    "select_available_site",
    "select_available_site_for_observer",
]
