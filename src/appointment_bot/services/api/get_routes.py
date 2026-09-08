from __future__ import annotations

from appointment_bot.services.api.captcha_shadow_routes import captcha_shadow_image_event_id
from appointment_bot.services.api.handlers import (
    appointment_reminder,
    captcha_authority,
    captcha_sampling,
    captcha_shadow,
    finance,
    manual_session,
    monthly_dashboard,
    monthly_dashboard_v2,
    operator_inbox,
    opportunity,
    post_appointment,
    run,
    service_order,
    service_package,
    whatsapp,
    whatsapp_message_template,
    worker,
)
from appointment_bot.services.api.opportunity_routes import opportunity_burst_id
from appointment_bot.services.api.routing import Route
from appointment_bot.services.api.whatsapp_routes import whatsapp_message_path

GET_ROUTES = (
    Route("/health", worker.get_health, authenticated=False),
    Route("/api/v1/worker", worker.get_worker),
    Route("/api/v1/worker/commands", worker.get_list_worker_commands),
    Route(
        "/api/v1/runtime-controls/captcha-sampling", captcha_sampling.get_captcha_sampling_control
    ),
    Route(
        "/api/v1/runtime-controls/captcha-authority",
        captcha_authority.get_captcha_authority_control,
    ),
    Route("/api/v1/runtime-controls/opportunity", opportunity.get_opportunity_control),
    Route("/api/v1/opportunity-bursts", opportunity.get_opportunity_bursts),
    Route("/api/v1/appointment-reminders", appointment_reminder.get_appointment_reminders),
    Route(
        "/api/v1/whatsapp-message-templates",
        whatsapp_message_template.get_whatsapp_message_templates,
    ),
    Route(lambda path: opportunity_burst_id(path), opportunity.get_opportunity_burst),
    Route("/api/v1/manual-sessions", manual_session.get_list_manual_sessions),
    Route("/api/v1/captcha-shadow/summary", captcha_shadow.get_captcha_shadow_summary),
    Route("/api/v1/captcha-shadow/events", captcha_shadow.get_captcha_shadow_events),
    Route("/api/v1/captcha-shadow/quality", captcha_shadow.get_captcha_shadow_quality),
    Route("/api/v1/captcha-shadow/quality/cases", captcha_shadow.get_captcha_shadow_quality_cases),
    Route(
        "/api/v1/captcha-shadow/dataset/export", captcha_shadow.get_captcha_shadow_dataset_export
    ),
    Route(
        lambda path: captcha_shadow_image_event_id(path), captcha_shadow.get_captcha_shadow_image
    ),
    Route("/api/v1/service-orders", service_order.get_list_service_orders),
    Route("/api/v1/service-packages", service_package.get_service_packages),
    Route("/api/v1/operator-inbox", operator_inbox.get_operator_inbox),
    Route("/api/v1/post-appointment-followups", post_appointment.get_post_appointment_followups),
    Route("/api/v1/monthly-summary", monthly_dashboard.get_monthly_dashboard),
    Route("/api/v2/monthly-summary", monthly_dashboard_v2.get_monthly_dashboard_v2),
    Route("/api/v1/finance/categories", finance.get_finance_categories),
    Route("/api/v1/finance/entries", finance.get_finance_entries),
    Route("/api/v1/finance/summary", finance.get_finance_summary),
    Route("/api/v1/finance/data-quality", finance.get_finance_data_quality),
    Route("/api/v1/finance/month-closure", finance.get_finance_month_closure),
    Route(lambda path: whatsapp_message_path(path, "attachment"), whatsapp.get_attachment),
    Route(
        lambda path: whatsapp_message_path(path, "payment-attachment"),
        whatsapp.get_payment_attachment,
    ),
    Route(
        lambda path: (
            True
            if path.startswith("/api/v1/whatsapp-followup-messages/") and "/attachments/" in path
            else None
        ),
        whatsapp.get_followup_attachment,
    ),
    Route(
        lambda path: True if path.startswith("/api/v1/service-orders/") else None,
        service_order.get_service_order_detail,
    ),
    Route("/api/v1/runs", run.get_list_runs),
    Route(lambda path: True if path.startswith("/api/v1/runs/") else None, run.get_run),
)
