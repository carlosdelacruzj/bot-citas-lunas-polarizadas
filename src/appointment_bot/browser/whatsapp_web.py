"""Compatibility exports retained until post-extraction natural acceptance."""

from __future__ import annotations

from appointment_bot.browser.whatsapp.album import (
    _attach_album_with_safe_page_retry as _attach_album_with_safe_page_retry,
)
from appointment_bot.browser.whatsapp.album import _prepare_album as _prepare_album
from appointment_bot.browser.whatsapp.album import _send_album as _send_album
from appointment_bot.browser.whatsapp.api import (
    prepare_whatsapp_web_album as prepare_whatsapp_web_album,
)
from appointment_bot.browser.whatsapp.api import (
    prepare_whatsapp_web_documents as prepare_whatsapp_web_documents,
)
from appointment_bot.browser.whatsapp.api import (
    prepare_whatsapp_web_draft as prepare_whatsapp_web_draft,
)
from appointment_bot.browser.whatsapp.api import (
    send_whatsapp_web_appointment_reminder as send_whatsapp_web_appointment_reminder,
)
from appointment_bot.browser.whatsapp.api import (
    send_whatsapp_web_daily_slot_summary as send_whatsapp_web_daily_slot_summary,
)
from appointment_bot.browser.whatsapp.api import (
    send_whatsapp_web_registration_notice as send_whatsapp_web_registration_notice,
)
from appointment_bot.browser.whatsapp.api import (
    validate_whatsapp_web_session as validate_whatsapp_web_session,
)
from appointment_bot.browser.whatsapp.attachments import _attach_document as _attach_document
from appointment_bot.browser.whatsapp.attachments import _attach_image as _attach_image
from appointment_bot.browser.whatsapp.attachments import (
    _choose_document_files as _choose_document_files,
)
from appointment_bot.browser.whatsapp.attachments import (
    _click_attachment_button as _click_attachment_button,
)
from appointment_bot.browser.whatsapp.attachments import (
    _wait_for_attachment_menu as _wait_for_attachment_menu,
)
from appointment_bot.browser.whatsapp.common import (
    CHAT_READY_TIMEOUT_SECONDS as CHAT_READY_TIMEOUT_SECONDS,
)
from appointment_bot.browser.whatsapp.common import (
    COMMAND_TIMEOUT_SECONDS as COMMAND_TIMEOUT_SECONDS,
)
from appointment_bot.browser.whatsapp.common import (
    DAILY_SUMMARY_IMAGE_BATCH_SIZE as DAILY_SUMMARY_IMAGE_BATCH_SIZE,
)
from appointment_bot.browser.whatsapp.common import (
    PLAIN_TEXT_CONFIRMATION_GRACE_SECONDS as PLAIN_TEXT_CONFIRMATION_GRACE_SECONDS,
)
from appointment_bot.browser.whatsapp.common import (
    PLAIN_TEXT_CONFIRMATION_TIMEOUT_SECONDS as PLAIN_TEXT_CONFIRMATION_TIMEOUT_SECONDS,
)
from appointment_bot.browser.whatsapp.common import PROFILE_DIR as PROFILE_DIR
from appointment_bot.browser.whatsapp.common import WhatsAppSendUncertain as WhatsAppSendUncertain
from appointment_bot.browser.whatsapp.common import (
    _AttachmentBeforeFileSelectionError as _AttachmentBeforeFileSelectionError,
)
from appointment_bot.browser.whatsapp.common import _result as _result
from appointment_bot.browser.whatsapp.common import logger as logger
from appointment_bot.browser.whatsapp.composition import (
    _click_and_replace_text as _click_and_replace_text,
)
from appointment_bot.browser.whatsapp.composition import _fill_caption as _fill_caption
from appointment_bot.browser.whatsapp.composition import (
    _fill_selected_album_caption as _fill_selected_album_caption,
)
from appointment_bot.browser.whatsapp.composition import _paste_text_message as _paste_text_message
from appointment_bot.browser.whatsapp.confirmation import (
    _message_container_has_confirmed_status as _message_container_has_confirmed_status,
)
from appointment_bot.browser.whatsapp.confirmation import (
    _message_container_has_large_image as _message_container_has_large_image,
)
from appointment_bot.browser.whatsapp.confirmation import (
    _message_container_has_pending_status as _message_container_has_pending_status,
)
from appointment_bot.browser.whatsapp.confirmation import (
    _message_container_is_outgoing as _message_container_is_outgoing,
)
from appointment_bot.browser.whatsapp.confirmation import (
    _message_container_signature as _message_container_signature,
)
from appointment_bot.browser.whatsapp.confirmation import (
    _outgoing_image_message_records as _outgoing_image_message_records,
)
from appointment_bot.browser.whatsapp.confirmation import (
    _outgoing_message_signatures as _outgoing_message_signatures,
)
from appointment_bot.browser.whatsapp.confirmation import (
    _plain_text_send_is_confirmed as _plain_text_send_is_confirmed,
)
from appointment_bot.browser.whatsapp.confirmation import (
    _wait_until_outgoing_images_uploaded as _wait_until_outgoing_images_uploaded,
)
from appointment_bot.browser.whatsapp.confirmation import (
    _wait_until_plain_text_send_finishes as _wait_until_plain_text_send_finishes,
)
from appointment_bot.browser.whatsapp.confirmation import (
    _wait_until_send_attempt_finishes as _wait_until_send_attempt_finishes,
)
from appointment_bot.browser.whatsapp.documents import _prepare_documents as _prepare_documents
from appointment_bot.browser.whatsapp.dom import _album_control_summary as _album_control_summary
from appointment_bot.browser.whatsapp.dom import _album_thumbnails as _album_thumbnails
from appointment_bot.browser.whatsapp.dom import (
    _attachment_control_summary as _attachment_control_summary,
)
from appointment_bot.browser.whatsapp.dom import (
    _attachment_menu_summary as _attachment_menu_summary,
)
from appointment_bot.browser.whatsapp.dom import (
    _attachment_menu_visible as _attachment_menu_visible,
)
from appointment_bot.browser.whatsapp.dom import (
    _attachment_option_container as _attachment_option_container,
)
from appointment_bot.browser.whatsapp.dom import (
    _attachment_preview_visible as _attachment_preview_visible,
)
from appointment_bot.browser.whatsapp.dom import _caption_editor as _caption_editor
from appointment_bot.browser.whatsapp.dom import _caption_editor_summary as _caption_editor_summary
from appointment_bot.browser.whatsapp.dom import (
    _compact_alphanumeric_text as _compact_alphanumeric_text,
)
from appointment_bot.browser.whatsapp.dom import _document_file_input as _document_file_input
from appointment_bot.browser.whatsapp.dom import (
    _document_preview_visible as _document_preview_visible,
)
from appointment_bot.browser.whatsapp.dom import _file_input_summary as _file_input_summary
from appointment_bot.browser.whatsapp.dom import (
    _file_input_summary_from as _file_input_summary_from,
)
from appointment_bot.browser.whatsapp.dom import _image_file_input as _image_file_input
from appointment_bot.browser.whatsapp.dom import (
    _locator_has_visible_match as _locator_has_visible_match,
)
from appointment_bot.browser.whatsapp.dom import (
    _normal_chat_composer_visible as _normal_chat_composer_visible,
)
from appointment_bot.browser.whatsapp.dom import _plain_text_ready as _plain_text_ready
from appointment_bot.browser.whatsapp.dom import _safe_get_attribute as _safe_get_attribute
from appointment_bot.browser.whatsapp.dom import _safe_text_content as _safe_text_content
from appointment_bot.browser.whatsapp.dom import _same_editor_text as _same_editor_text
from appointment_bot.browser.whatsapp.dom import _visible as _visible
from appointment_bot.browser.whatsapp.drafts import _prepare_draft as _prepare_draft
from appointment_bot.browser.whatsapp.evidence import (
    _safe_whatsapp_artifact_name as _safe_whatsapp_artifact_name,
)
from appointment_bot.browser.whatsapp.evidence import (
    _save_context_failure_screenshot as _save_context_failure_screenshot,
)
from appointment_bot.browser.whatsapp.evidence import (
    _save_whatsapp_debug_screenshot as _save_whatsapp_debug_screenshot,
)
from appointment_bot.browser.whatsapp.evidence import (
    _whatsapp_qr_image_data_url as _whatsapp_qr_image_data_url,
)
from appointment_bot.browser.whatsapp.manager import _MANAGER as _MANAGER
from appointment_bot.browser.whatsapp.manager import (
    WhatsAppWebDraftManager as WhatsAppWebDraftManager,
)
from appointment_bot.browser.whatsapp.manager import _DraftCommand as _DraftCommand
from appointment_bot.browser.whatsapp.navigation import (
    _chat_not_ready_result as _chat_not_ready_result,
)
from appointment_bot.browser.whatsapp.navigation import (
    _click_username_chat_result as _click_username_chat_result,
)
from appointment_bot.browser.whatsapp.navigation import (
    _dismiss_safe_whatsapp_dialog as _dismiss_safe_whatsapp_dialog,
)
from appointment_bot.browser.whatsapp.navigation import (
    _dismiss_whatsapp_updates_dialog as _dismiss_whatsapp_updates_dialog,
)
from appointment_bot.browser.whatsapp.navigation import (
    _invalid_recipient_visible as _invalid_recipient_visible,
)
from appointment_bot.browser.whatsapp.navigation import _open_recipient_chat as _open_recipient_chat
from appointment_bot.browser.whatsapp.navigation import (
    _row_belongs_to_chat_results as _row_belongs_to_chat_results,
)
from appointment_bot.browser.whatsapp.navigation import (
    _visible_username_chat_result_rows as _visible_username_chat_result_rows,
)
from appointment_bot.browser.whatsapp.navigation import (
    _visible_whatsapp_dialogs as _visible_whatsapp_dialogs,
)
from appointment_bot.browser.whatsapp.navigation import (
    _visible_whatsapp_search as _visible_whatsapp_search,
)
from appointment_bot.browser.whatsapp.navigation import _wait_for_chat as _wait_for_chat
from appointment_bot.browser.whatsapp.navigation import (
    _wait_for_stable_username_chat_results as _wait_for_stable_username_chat_results,
)
from appointment_bot.browser.whatsapp.navigation import (
    _whatsapp_chat_row_label as _whatsapp_chat_row_label,
)
from appointment_bot.browser.whatsapp.notifications import (
    _send_appointment_reminder as _send_appointment_reminder,
)
from appointment_bot.browser.whatsapp.notifications import (
    _send_daily_slot_summary as _send_daily_slot_summary,
)
from appointment_bot.browser.whatsapp.notifications import (
    _send_registration_notice as _send_registration_notice,
)
from appointment_bot.browser.whatsapp.sending import (
    _click_bottom_right_send_button as _click_bottom_right_send_button,
)
from appointment_bot.browser.whatsapp.sending import _click_send_button as _click_send_button
from appointment_bot.browser.whatsapp.sending import (
    _click_visible_send_button as _click_visible_send_button,
)
from appointment_bot.browser.whatsapp.sending import (
    _send_plain_text_message as _send_plain_text_message,
)
from appointment_bot.browser.whatsapp.session import (
    _HEADLESS_WHATSAPP_USER_AGENT as _HEADLESS_WHATSAPP_USER_AGENT,
)
from appointment_bot.browser.whatsapp.session import _close_context as _close_context
from appointment_bot.browser.whatsapp.session import _ensure_context as _ensure_context
from appointment_bot.browser.whatsapp.session import _fresh_whatsapp_page as _fresh_whatsapp_page
from appointment_bot.browser.whatsapp.session import (
    _headless_whatsapp_user_agent as _headless_whatsapp_user_agent,
)
from appointment_bot.browser.whatsapp.session import (
    _is_closed_target_error as _is_closed_target_error,
)
from appointment_bot.browser.whatsapp.session import (
    _validate_whatsapp_session as _validate_whatsapp_session,
)
from appointment_bot.browser.whatsapp.session import (
    _whatsapp_session_ready as _whatsapp_session_ready,
)
