from __future__ import annotations

import argparse
import logging

from appointment_bot.services.telegram.access import TelegramRateLimiter as TelegramRateLimiter
from appointment_bot.services.telegram.access import _callback_is_mutation as _callback_is_mutation
from appointment_bot.services.telegram.access import _command_parts as _command_parts
from appointment_bot.services.telegram.access import (
    _mutation_user_authorized as _mutation_user_authorized,
)
from appointment_bot.services.telegram.admin_api_client import AdminApiClient as AdminApiClient
from appointment_bot.services.telegram.audit import _audit_target as _audit_target
from appointment_bot.services.telegram.audit import _record_audit_safe as _record_audit_safe
from appointment_bot.services.telegram.audit import _telegram_actor as _telegram_actor
from appointment_bot.services.telegram.bot_api import TelegramBotApi as TelegramBotApi
from appointment_bot.services.telegram.bot_api import _multipart_form_data as _multipart_form_data
from appointment_bot.services.telegram.callbacks import (
    _process_callback_query as _process_callback_query,
)
from appointment_bot.services.telegram.captcha_conversation import (
    _captcha_model_short_label as _captcha_model_short_label,
)
from appointment_bot.services.telegram.captcha_conversation import (
    _captcha_prediction_choices as _captcha_prediction_choices,
)
from appointment_bot.services.telegram.captcha_conversation import (
    _captcha_review_markup as _captcha_review_markup,
)
from appointment_bot.services.telegram.captcha_conversation import (
    _captcha_review_reason as _captcha_review_reason,
)
from appointment_bot.services.telegram.captcha_conversation import (
    _clear_captcha_review_buttons as _clear_captcha_review_buttons,
)
from appointment_bot.services.telegram.captcha_conversation import (
    _next_pending_captcha as _next_pending_captcha,
)
from appointment_bot.services.telegram.captcha_conversation import (
    _process_captcha_review_callback as _process_captcha_review_callback,
)
from appointment_bot.services.telegram.captcha_conversation import (
    _process_captcha_review_message as _process_captcha_review_message,
)
from appointment_bot.services.telegram.captcha_conversation import (
    _save_captcha_review_answer as _save_captcha_review_answer,
)
from appointment_bot.services.telegram.captcha_conversation import (
    _send_next_captcha_review as _send_next_captcha_review,
)
from appointment_bot.services.telegram.captcha_conversation import (
    _start_captcha_review as _start_captcha_review,
)
from appointment_bot.services.telegram.client_conversation import (
    _client_creation_error_reason as _client_creation_error_reason,
)
from appointment_bot.services.telegram.client_conversation import (
    _continue_new_client_conversation as _continue_new_client_conversation,
)
from appointment_bot.services.telegram.client_conversation import (
    _delete_message_safe as _delete_message_safe,
)
from appointment_bot.services.telegram.client_conversation import (
    _delete_sensitive_message as _delete_sensitive_message,
)
from appointment_bot.services.telegram.client_conversation import (
    _execute_client_creation as _execute_client_creation,
)
from appointment_bot.services.telegram.client_conversation import (
    _persisted_client_creation_matches as _persisted_client_creation_matches,
)
from appointment_bot.services.telegram.client_conversation import (
    _process_new_client_message as _process_new_client_message,
)
from appointment_bot.services.telegram.client_conversation import (
    _recover_persisted_client_creation as _recover_persisted_client_creation,
)
from appointment_bot.services.telegram.client_conversation import (
    _send_client_creation_message_safe as _send_client_creation_message_safe,
)
from appointment_bot.services.telegram.client_conversation import (
    _start_new_client_conversation as _start_new_client_conversation,
)
from appointment_bot.services.telegram.client_forms import (
    _apply_manual_client_value as _apply_manual_client_value,
)
from appointment_bot.services.telegram.client_forms import (
    _apply_new_client_value as _apply_new_client_value,
)
from appointment_bot.services.telegram.client_forms import (
    _fixed_service_package_values as _fixed_service_package_values,
)
from appointment_bot.services.telegram.client_forms import (
    _manual_client_step_prompt as _manual_client_step_prompt,
)
from appointment_bot.services.telegram.client_forms import (
    _new_client_prompt_markup as _new_client_prompt_markup,
)
from appointment_bot.services.telegram.client_forms import _rewind_new_client as _rewind_new_client
from appointment_bot.services.telegram.client_forms import (
    _telegram_service_package_option as _telegram_service_package_option,
)
from appointment_bot.services.telegram.config import _positive_int as _positive_int
from appointment_bot.services.telegram.config import (
    _validated_admin_api_url as _validated_admin_api_url,
)
from appointment_bot.services.telegram.config import load_control_config as load_control_config
from appointment_bot.services.telegram.constants import (
    CAPTCHA_REVIEW_TTL_SECONDS as CAPTCHA_REVIEW_TTL_SECONDS,
)
from appointment_bot.services.telegram.constants import CLIENTS_PAGE_SIZE as CLIENTS_PAGE_SIZE
from appointment_bot.services.telegram.constants import (
    CONFIRMATION_TTL_SECONDS as CONFIRMATION_TTL_SECONDS,
)
from appointment_bot.services.telegram.constants import (
    CONVERSATION_TTL_SECONDS as CONVERSATION_TTL_SECONDS,
)
from appointment_bot.services.telegram.constants import (
    DEFAULT_ADMIN_API_URL as DEFAULT_ADMIN_API_URL,
)
from appointment_bot.services.telegram.constants import (
    DEFAULT_POLL_TIMEOUT_SECONDS as DEFAULT_POLL_TIMEOUT_SECONDS,
)
from appointment_bot.services.telegram.constants import GENERAL_RATE_LIMIT as GENERAL_RATE_LIMIT
from appointment_bot.services.telegram.constants import HELP_TEXT as HELP_TEXT
from appointment_bot.services.telegram.constants import LIMA_TIMEZONE as LIMA_TIMEZONE
from appointment_bot.services.telegram.constants import MUTATING_COMMANDS as MUTATING_COMMANDS
from appointment_bot.services.telegram.constants import MUTATION_RATE_LIMIT as MUTATION_RATE_LIMIT
from appointment_bot.services.telegram.constants import (
    NEW_CLIENT_CONFIRMATION_TTL_SECONDS as NEW_CLIENT_CONFIRMATION_TTL_SECONDS,
)
from appointment_bot.services.telegram.constants import (
    NEW_CLIENT_CONVERSATION_TTL_SECONDS as NEW_CLIENT_CONVERSATION_TTL_SECONDS,
)
from appointment_bot.services.telegram.constants import (
    ORDER_TARGET_COMMANDS as ORDER_TARGET_COMMANDS,
)
from appointment_bot.services.telegram.constants import (
    RATE_LIMIT_WINDOW_SECONDS as RATE_LIMIT_WINDOW_SECONDS,
)
from appointment_bot.services.telegram.constants import RETRY_DELAY_SECONDS as RETRY_DELAY_SECONDS
from appointment_bot.services.telegram.constants import (
    SENSITIVE_MESSAGE_TTL_SECONDS as SENSITIVE_MESSAGE_TTL_SECONDS,
)
from appointment_bot.services.telegram.constants import (
    WORKER_COMMAND_TIMEOUT_SECONDS as WORKER_COMMAND_TIMEOUT_SECONDS,
)
from appointment_bot.services.telegram.constants import (
    WORKER_MONITOR_END_MINUTE as WORKER_MONITOR_END_MINUTE,
)
from appointment_bot.services.telegram.constants import (
    WORKER_MONITOR_FAILURE_THRESHOLD as WORKER_MONITOR_FAILURE_THRESHOLD,
)
from appointment_bot.services.telegram.constants import (
    WORKER_MONITOR_INTERVAL_SECONDS as WORKER_MONITOR_INTERVAL_SECONDS,
)
from appointment_bot.services.telegram.constants import (
    WORKER_MONITOR_START_MINUTE as WORKER_MONITOR_START_MINUTE,
)
from appointment_bot.services.telegram.errors import TelegramControlError as TelegramControlError
from appointment_bot.services.telegram.interface_callbacks import (
    _process_interface_callback as _process_interface_callback,
)
from appointment_bot.services.telegram.models import (
    CaptchaReviewConversation as CaptchaReviewConversation,
)
from appointment_bot.services.telegram.models import NewClientConversation as NewClientConversation
from appointment_bot.services.telegram.models import PendingClientCreation as PendingClientCreation
from appointment_bot.services.telegram.models import PendingOrderChange as PendingOrderChange
from appointment_bot.services.telegram.models import (
    PendingWorkerConfirmation as PendingWorkerConfirmation,
)
from appointment_bot.services.telegram.models import RulesConversation as RulesConversation
from appointment_bot.services.telegram.models import SearchConversation as SearchConversation
from appointment_bot.services.telegram.models import TelegramControlConfig as TelegramControlConfig
from appointment_bot.services.telegram.order_changes import (
    _execute_order_change as _execute_order_change,
)
from appointment_bot.services.telegram.order_changes import (
    _execute_order_revalidation as _execute_order_revalidation,
)
from appointment_bot.services.telegram.order_changes import (
    _order_change_matches as _order_change_matches,
)
from appointment_bot.services.telegram.order_changes import (
    _request_credentials_change as _request_credentials_change,
)
from appointment_bot.services.telegram.order_changes import (
    _request_payment_change as _request_payment_change,
)
from appointment_bot.services.telegram.order_changes import (
    _request_priority_change as _request_priority_change,
)
from appointment_bot.services.telegram.order_changes import (
    _send_order_change_confirmation as _send_order_change_confirmation,
)
from appointment_bot.services.telegram.order_changes import (
    _store_order_change as _store_order_change,
)
from appointment_bot.services.telegram.order_queries import (
    _wait_for_order_preflight as _wait_for_order_preflight,
)
from appointment_bot.services.telegram.panels import _parse_list_page as _parse_list_page
from appointment_bot.services.telegram.panels import _send_clients as _send_clients
from appointment_bot.services.telegram.panels import _send_daily_summary as _send_daily_summary
from appointment_bot.services.telegram.panels import _send_main_menu as _send_main_menu
from appointment_bot.services.telegram.panels import (
    _send_operational_order_list as _send_operational_order_list,
)
from appointment_bot.services.telegram.panels import _send_order_panel as _send_order_panel
from appointment_bot.services.telegram.panels import _send_order_query as _send_order_query
from appointment_bot.services.telegram.panels import _send_payment_menu as _send_payment_menu
from appointment_bot.services.telegram.panels import (
    _send_pending_attention as _send_pending_attention,
)
from appointment_bot.services.telegram.panels import (
    _send_pending_payments as _send_pending_payments,
)
from appointment_bot.services.telegram.panels import _send_priority_menu as _send_priority_menu
from appointment_bot.services.telegram.panels import _send_queue as _send_queue
from appointment_bot.services.telegram.panels import _send_recent_errors as _send_recent_errors
from appointment_bot.services.telegram.panels import _send_search_results as _send_search_results
from appointment_bot.services.telegram.panels import _send_tools_menu as _send_tools_menu
from appointment_bot.services.telegram.presentation import (
    _applicant_display_name as _applicant_display_name,
)
from appointment_bot.services.telegram.presentation import _change_value as _change_value
from appointment_bot.services.telegram.presentation import _display_text as _display_text
from appointment_bot.services.telegram.presentation import (
    _format_excluded_date_ranges as _format_excluded_date_ranges,
)
from appointment_bot.services.telegram.presentation import (
    _format_lima_datetime as _format_lima_datetime,
)
from appointment_bot.services.telegram.presentation import (
    _format_manual_client_details as _format_manual_client_details,
)
from appointment_bot.services.telegram.presentation import (
    _format_new_client_confirmation as _format_new_client_confirmation,
)
from appointment_bot.services.telegram.presentation import (
    _format_operator_date as _format_operator_date,
)
from appointment_bot.services.telegram.presentation import (
    _format_opportunity_control as _format_opportunity_control,
)
from appointment_bot.services.telegram.presentation import (
    _format_order_change_comparison as _format_order_change_comparison,
)
from appointment_bot.services.telegram.presentation import (
    _format_worker_command_success as _format_worker_command_success,
)
from appointment_bot.services.telegram.presentation import _is_failed_run as _is_failed_run
from appointment_bot.services.telegram.presentation import _main_menu_markup as _main_menu_markup
from appointment_bot.services.telegram.presentation import _money_text as _money_text
from appointment_bot.services.telegram.presentation import (
    _order_status_counts as _order_status_counts,
)
from appointment_bot.services.telegram.presentation import (
    _order_status_label as _order_status_label,
)
from appointment_bot.services.telegram.presentation import (
    _payment_status_label as _payment_status_label,
)
from appointment_bot.services.telegram.presentation import (
    _preflight_status_label as _preflight_status_label,
)
from appointment_bot.services.telegram.presentation import (
    _reservation_status_label as _reservation_status_label,
)
from appointment_bot.services.telegram.presentation import _safe_run_message as _safe_run_message
from appointment_bot.services.telegram.presentation import (
    _service_scope_text as _service_scope_text,
)
from appointment_bot.services.telegram.presentation import (
    _service_type_label as _service_type_label,
)
from appointment_bot.services.telegram.presentation import _short_text as _short_text
from appointment_bot.services.telegram.presentation import _weekday_name as _weekday_name
from appointment_bot.services.telegram.presentation import (
    _worker_command_label as _worker_command_label,
)
from appointment_bot.services.telegram.presentation import (
    format_order_detail as format_order_detail,
)
from appointment_bot.services.telegram.presentation import format_order_rules as format_order_rules
from appointment_bot.services.telegram.presentation import (
    format_worker_status as format_worker_status,
)
from appointment_bot.services.telegram.router import _process_update as _process_update
from appointment_bot.services.telegram.rules_conversation import (
    _continue_rules_conversation as _continue_rules_conversation,
)
from appointment_bot.services.telegram.rules_conversation import (
    _process_rules_conversation_message as _process_rules_conversation_message,
)
from appointment_bot.services.telegram.rules_conversation import (
    _rules_prompt_markup as _rules_prompt_markup,
)
from appointment_bot.services.telegram.rules_conversation import (
    _rules_step_prompt as _rules_step_prompt,
)
from appointment_bot.services.telegram.rules_conversation import (
    _start_rules_conversation as _start_rules_conversation,
)
from appointment_bot.services.telegram.runtime import (
    _install_signal_handlers as _install_signal_handlers,
)
from appointment_bot.services.telegram.runtime import run_control as run_control
from appointment_bot.services.telegram.state import (
    _cancel_chat_client_state as _cancel_chat_client_state,
)
from appointment_bot.services.telegram.state import (
    _cancel_chat_confirmations as _cancel_chat_confirmations,
)
from appointment_bot.services.telegram.state import (
    _cancel_chat_confirmations_unlocked as _cancel_chat_confirmations_unlocked,
)
from appointment_bot.services.telegram.state import (
    _cancel_chat_order_state as _cancel_chat_order_state,
)
from appointment_bot.services.telegram.state import (
    _cancel_chat_order_state_unlocked as _cancel_chat_order_state_unlocked,
)
from appointment_bot.services.telegram.state import (
    _cancel_pending_client_creation_unlocked as _cancel_pending_client_creation_unlocked,
)
from appointment_bot.services.telegram.state import _load_next_offset as _load_next_offset
from appointment_bot.services.telegram.state import (
    _remove_expired_captcha_state as _remove_expired_captcha_state,
)
from appointment_bot.services.telegram.state import (
    _remove_expired_client_state as _remove_expired_client_state,
)
from appointment_bot.services.telegram.state import (
    _remove_expired_confirmations as _remove_expired_confirmations,
)
from appointment_bot.services.telegram.state import (
    _remove_expired_order_state as _remove_expired_order_state,
)
from appointment_bot.services.telegram.state import _store_next_offset as _store_next_offset
from appointment_bot.services.telegram.state import _update_id as _update_id
from appointment_bot.services.telegram.transport import (
    MAX_TELEGRAM_RESPONSE_BYTES as MAX_TELEGRAM_RESPONSE_BYTES,
)
from appointment_bot.services.telegram.transport import (
    _read_json_response as _read_json_response,
)
from appointment_bot.services.telegram.validation import _money_value as _money_value
from appointment_bot.services.telegram.validation import _parse_rules_step as _parse_rules_step
from appointment_bot.services.telegram.validation import (
    _parse_single_weekday as _parse_single_weekday,
)
from appointment_bot.services.telegram.validation import _payment_balance as _payment_balance
from appointment_bot.services.telegram.validation import _rules_payload as _rules_payload
from appointment_bot.services.telegram.validation import _valid_order_id as _valid_order_id
from appointment_bot.services.telegram.validation import (
    _validate_rules_payload as _validate_rules_payload,
)
from appointment_bot.services.telegram.validation import (
    _validated_payment_amount as _validated_payment_amount,
)
from appointment_bot.services.telegram.worker_controls import (
    WorkerHealthMonitor as WorkerHealthMonitor,
)
from appointment_bot.services.telegram.worker_controls import (
    _execute_opportunity_control as _execute_opportunity_control,
)
from appointment_bot.services.telegram.worker_controls import (
    _execute_worker_command as _execute_worker_command,
)
from appointment_bot.services.telegram.worker_controls import (
    _request_opportunity_confirmation as _request_opportunity_confirmation,
)
from appointment_bot.services.telegram.worker_controls import (
    _request_worker_confirmation as _request_worker_confirmation,
)
from appointment_bot.services.telegram.worker_controls import (
    _wait_for_worker_command as _wait_for_worker_command,
)
from appointment_bot.services.telegram.worker_controls import (
    _wait_for_worker_effect as _wait_for_worker_effect,
)
from appointment_bot.services.telegram.worker_panels import (
    _send_opportunity_panel as _send_opportunity_panel,
)
from appointment_bot.services.telegram.worker_panels import _send_worker_panel as _send_worker_panel

logger = logging.getLogger("appointment_bot.services.telegram_control")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Telegram remote-control receiver.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate Telegram and Admin API connectivity without consuming updates.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    try:
        raise SystemExit(run_control(check_only=args.check))
    except TelegramControlError as exc:
        logger.error("Telegram control could not start: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
