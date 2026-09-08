from __future__ import annotations

from appointment_bot.services.api.captcha_shadow_routes import captcha_shadow_human_label_event_id
from appointment_bot.services.api.finance_routes import (
    finance_entry_action_path,
    finance_payment_reconciliation_path,
)
from appointment_bot.services.api.handlers import (
    appointment_reminder,
    captcha_authority,
    captcha_sampling,
    captcha_shadow,
    finance,
    manual_session,
    opportunity,
    post_appointment,
    service_order,
    whatsapp,
    whatsapp_message_template,
    worker,
)
from appointment_bot.services.api.post_appointment_routes import post_appointment_review_order_id
from appointment_bot.services.api.routing import Route
from appointment_bot.services.api.service_order_routes import (
    payment_paid_path,
    payment_partial_path,
    service_order_action,
    service_order_close_path,
    service_order_contact_path,
    service_order_credentials_path,
    service_order_priority_path,
    service_order_program_resolution_path,
    service_order_restrictions_path,
    service_order_revalidate_path,
    service_order_split_programs_path,
)
from appointment_bot.services.api.whatsapp_message_template_routes import (
    whatsapp_message_template_action_path,
)
from appointment_bot.services.api.whatsapp_routes import (
    order_followup_prepare_path,
    order_prepare_path,
    whatsapp_followup_message_path,
    whatsapp_message_path,
    whatsapp_review_job_path,
)

POST_ROUTES = (
    Route(
        lambda path: whatsapp_message_template_action_path(path, "preview"),
        whatsapp_message_template.post_preview_whatsapp_message_template,
    ),
    Route("/api/v1/appointment-reminders", appointment_reminder.post_update_appointment_reminders),
    Route(
        "/api/v1/runtime-controls/captcha-sampling",
        captcha_sampling.post_update_captcha_sampling_control,
    ),
    Route(
        "/api/v1/runtime-controls/captcha-authority",
        captcha_authority.post_update_captcha_authority_control,
    ),
    Route("/api/v1/runtime-controls/opportunity", opportunity.post_update_opportunity_control),
    Route(
        lambda path: captcha_shadow_human_label_event_id(path),
        captcha_shadow.post_save_captcha_shadow_human_label,
    ),
    Route("/api/v1/service-orders", service_order.post_create_service_order),
    Route("/api/v1/service-orders/search", service_order.post_search_service_orders),
    Route(
        lambda path: post_appointment_review_order_id(path),
        post_appointment.post_review_post_appointment,
    ),
    Route("/api/v1/whatsapp-messages/test/prepare", whatsapp.post_prepare_test),
    Route("/api/v1/whatsapp-followup-messages/test/prepare", whatsapp.post_prepare_followup_test),
    Route("/api/v1/whatsapp-web/session/validate", whatsapp.post_validate_whatsapp_session),
    Route(lambda path: order_prepare_path(path), whatsapp.post_prepare_order),
    Route(lambda path: whatsapp_message_path(path, "sent"), whatsapp.post_mark_sent),
    Route(lambda path: whatsapp_message_path(path, "web/prepare"), whatsapp.post_prepare_web),
    Route(lambda path: order_followup_prepare_path(path), whatsapp.post_prepare_followup),
    Route(
        lambda path: whatsapp_followup_message_path(path, "web/prepare"),
        whatsapp.post_prepare_followup_web,
    ),
    Route(
        lambda path: whatsapp_followup_message_path(path, "sent"), whatsapp.post_mark_followup_sent
    ),
    Route(lambda path: whatsapp_review_job_path(path), whatsapp.post_resolve_whatsapp_review),
    Route("/api/v1/finance/entries", finance.post_create_finance_entry),
    Route(lambda path: finance_entry_action_path(path, "edit"), finance.post_update_finance_entry),
    Route(lambda path: finance_entry_action_path(path, "void"), finance.post_void_finance_entry),
    Route("/api/v1/finance/month-closure", finance.post_upsert_finance_month_closure),
    Route(
        lambda path: finance_payment_reconciliation_path(path),
        finance.post_reconcile_payment_amount,
    ),
    Route(
        lambda path: service_order_contact_path(path),
        service_order.post_update_service_order_contact,
    ),
    Route(
        lambda path: service_order_credentials_path(path),
        service_order.post_update_service_order_credentials,
    ),
    Route(
        lambda path: service_order_priority_path(path),
        service_order.post_update_service_order_priority,
    ),
    Route(
        lambda path: service_order_restrictions_path(path),
        service_order.post_update_service_order_restrictions,
    ),
    Route(
        lambda path: service_order_revalidate_path(path),
        service_order.post_revalidate_service_order,
    ),
    Route(lambda path: payment_paid_path(path), service_order.post_mark_payment_paid),
    Route(lambda path: payment_partial_path(path), service_order.post_record_partial_payment),
    Route(lambda path: service_order_close_path(path), service_order.post_close_service_order),
    Route(
        lambda path: service_order_split_programs_path(path),
        service_order.post_split_service_order_programs,
    ),
    Route(
        lambda path: service_order_program_resolution_path(path),
        service_order.post_resolve_service_order_programs,
    ),
    Route(lambda path: service_order_action(path), service_order.post_apply_service_order_action),
    Route("/api/v1/worker/restart", worker.post_worker_restart),
    Route("/api/v1/manual-session/open", manual_session.post_open_manual_session),
    Route("/api/v1/manual-session/close", manual_session.post_close_manual_session),
    Route(
        lambda path: True if path in {"/api/v1/worker/pause", "/api/v1/worker/resume"} else None,
        worker.post_worker_control,
    ),
)
