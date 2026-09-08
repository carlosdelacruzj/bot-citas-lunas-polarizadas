from __future__ import annotations

from psycopg import Connection


def validate_current_schema(connection: Connection, schema_version: int) -> None:
    required_tables = {
        "schema_version",
        "applicants",
        "portal_accounts",
        "whatsapp_contacts",
        "applicant_contacts",
        "service_orders",
        "order_state",
        "runs",
        "order_checks",
        "observer_window_metrics",
        "reservation_attempts",
        "run_screenshots",
        "reservations",
        "payments",
        "payment_receipts",
        "worker_state",
        "worker_commands",
        "remote_control_audit",
        "finance_categories",
        "finance_entries",
        "finance_month_closures",
        "payment_amount_reconciliations",
        "whatsapp_messages",
        "whatsapp_followup_messages",
        "whatsapp_automation_jobs",
        "appointment_reminder_days",
        "appointment_reminder_control",
        "whatsapp_message_templates",
        "whatsapp_message_template_versions",
        "captcha_shadow_outbox",
        "telegram_alert_outbox",
        "captcha_sampling_control",
        "captcha_authority_control",
        "captcha_authority_decisions",
        "post_appointment_reviews",
        "post_appointment_stage_snapshots",
        "post_appointment_automatic_reviews",
        "opportunity_bursts",
        "opportunity_burst_candidates",
        "opportunity_burst_executions",
        "slot_lost_reobservation_events",
        "opportunity_runtime_control",
    }
    tables = {
        row["table_name"]
        for row in connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()"
        )
    }
    required_columns = {
        ("schema_version", "version"),
        ("whatsapp_contacts", "contact_source"),
        ("whatsapp_contacts", "username"),
        ("portal_accounts", "applicant_id"),
        ("portal_accounts", "password"),
        ("portal_accounts", "document_type"),
        ("service_orders", "status"),
        ("service_orders", "service_type"),
        ("service_orders", "reservation_price"),
        ("service_orders", "service_package"),
        ("service_orders", "official_fee_amount"),
        ("service_orders", "initial_payment_amount"),
        ("service_orders", "acquisition_source"),
        ("service_orders", "acquisition_source_origin"),
        ("service_orders", "minimum_hour"),
        ("service_orders", "minimum_date"),
        ("service_orders", "maximum_date"),
        ("service_orders", "allowed_weekdays"),
        ("service_orders", "excluded_date_ranges"),
        ("service_orders", "parent_order_id"),
        ("service_orders", "program_expediente"),
        ("service_orders", "program_plate"),
        ("service_orders", "closure_reason"),
        ("service_orders", "closure_note"),
        ("service_orders", "closed_at"),
        ("service_orders", "lease_owner"),
        ("service_orders", "lease_expires_at"),
        ("runs", "reservation_attempted"),
        ("runs", "reservation_confirmed"),
        ("order_checks", "checked_at"),
        ("order_state", "credential_failures"),
        ("order_state", "program_listing"),
        ("order_state", "preflight_status"),
        ("order_state", "preflight_message"),
        ("order_state", "preflight_started_at"),
        ("order_state", "preflight_validated_at"),
        ("order_state", "preflight_details"),
        ("order_state", "preflight_cycle"),
        ("reservation_attempts", "idempotency_key"),
        ("reservation_attempts", "status"),
        ("reservations", "run_id"),
        ("reservations", "status"),
        ("reservations", "appointment_day"),
        ("reservations", "program_expediente"),
        ("reservations", "program_plate"),
        ("payments", "reservation_id"),
        ("payments", "status"),
        ("worker_state", "current_order_id"),
        ("worker_state", "owner_token"),
        ("worker_state", "lease_expires_at"),
        ("worker_commands", "command"),
        ("worker_commands", "status"),
        ("worker_commands", "requested_at"),
        ("remote_control_audit", "actor"),
        ("remote_control_audit", "action"),
        ("remote_control_audit", "status"),
        ("remote_control_audit", "created_at"),
        ("finance_categories", "category_code"),
        ("finance_entries", "entry_kind"),
        ("finance_entries", "amount_original"),
        ("finance_entries", "amount_pen"),
        ("finance_entries", "status"),
        ("payment_receipts", "payment_id"),
        ("payment_receipts", "order_id"),
        ("payment_receipts", "amount"),
        ("payment_receipts", "received_at"),
        ("payment_receipts", "source"),
        ("payment_receipts", "actor"),
        ("payment_receipts", "corrects_receipt_id"),
        ("payment_receipts", "correction_reason"),
        ("finance_month_closures", "month_start"),
        ("finance_month_closures", "opening_prepaid_balance"),
        ("finance_month_closures", "closing_prepaid_balance"),
        ("finance_month_closures", "status"),
        ("finance_month_closures", "reconciled_at"),
        ("finance_month_closures", "reconciled_by"),
        ("payment_amount_reconciliations", "payment_id"),
        ("payment_amount_reconciliations", "resolution_type"),
        ("payment_amount_reconciliations", "reason"),
        ("payment_amount_reconciliations", "reconciled_by"),
        ("whatsapp_messages", "message_id"),
        ("whatsapp_messages", "recipient_phone"),
        ("whatsapp_messages", "recipient_username"),
        ("whatsapp_messages", "attachment_path"),
        ("whatsapp_messages", "payment_attachment_path"),
        ("whatsapp_messages", "status"),
        ("whatsapp_messages", "test_mode"),
        ("whatsapp_messages", "sent_at"),
        ("whatsapp_messages", "confirmation_template_key"),
        ("whatsapp_messages", "confirmation_template_revision"),
        ("whatsapp_messages", "payment_template_key"),
        ("whatsapp_messages", "payment_template_revision"),
        ("whatsapp_followup_messages", "message_id"),
        ("whatsapp_followup_messages", "recipient_phone"),
        ("whatsapp_followup_messages", "recipient_username"),
        ("whatsapp_followup_messages", "steps"),
        ("whatsapp_followup_messages", "status"),
        ("whatsapp_followup_messages", "test_mode"),
        ("whatsapp_followup_messages", "sent_at"),
        ("whatsapp_followup_messages", "message_text"),
        ("whatsapp_followup_messages", "template_key"),
        ("whatsapp_followup_messages", "template_revision"),
        ("whatsapp_automation_jobs", "job_key"),
        ("whatsapp_automation_jobs", "order_id"),
        ("whatsapp_automation_jobs", "job_kind"),
        ("whatsapp_automation_jobs", "status"),
        ("whatsapp_automation_jobs", "attempt_count"),
        ("whatsapp_automation_jobs", "lease_expires_at"),
        ("whatsapp_automation_jobs", "next_attempt_at"),
        ("whatsapp_automation_jobs", "preflight_error"),
        ("whatsapp_automation_jobs", "preflight_alerted_at"),
        ("whatsapp_automation_jobs", "review_resolution"),
        ("whatsapp_automation_jobs", "review_note"),
        ("whatsapp_automation_jobs", "reviewed_at"),
        ("whatsapp_automation_jobs", "reviewed_by"),
        ("whatsapp_automation_jobs", "report_date"),
        ("whatsapp_automation_jobs", "recipient_phone"),
        ("whatsapp_automation_jobs", "recipient_username"),
        ("whatsapp_automation_jobs", "message_text"),
        ("whatsapp_automation_jobs", "publication_text"),
        ("whatsapp_automation_jobs", "attachment_paths"),
        ("whatsapp_automation_jobs", "registration_notice_type"),
        ("whatsapp_automation_jobs", "preflight_cycle"),
        ("whatsapp_automation_jobs", "reservation_id"),
        ("whatsapp_automation_jobs", "appointment_day"),
        ("whatsapp_automation_jobs", "priority"),
        ("whatsapp_automation_jobs", "template_key"),
        ("whatsapp_automation_jobs", "template_revision"),
        ("appointment_reminder_days", "service_date"),
        ("appointment_reminder_days", "appointment_day"),
        ("appointment_reminder_days", "status"),
        ("appointment_reminder_days", "last_reconciled_at"),
        ("appointment_reminder_control", "mode"),
        ("appointment_reminder_control", "lead_days"),
        ("appointment_reminder_control", "revision"),
        ("whatsapp_message_templates", "template_key"),
        ("whatsapp_message_templates", "message_template"),
        ("whatsapp_message_templates", "revision"),
        ("whatsapp_message_templates", "enabled"),
        ("whatsapp_message_templates", "updated_at"),
        ("whatsapp_message_templates", "updated_by"),
        ("whatsapp_message_template_versions", "template_key"),
        ("whatsapp_message_template_versions", "revision"),
        ("whatsapp_message_template_versions", "message_template"),
        ("whatsapp_message_template_versions", "created_at"),
        ("whatsapp_message_template_versions", "created_by"),
        ("captcha_shadow_outbox", "event_key"),
        ("captcha_shadow_outbox", "event_id"),
        ("captcha_shadow_outbox", "sequence"),
        ("captcha_shadow_outbox", "status"),
        ("captcha_shadow_outbox", "next_attempt_at"),
        ("telegram_alert_outbox", "dedupe_key"),
        ("telegram_alert_outbox", "payload"),
        ("telegram_alert_outbox", "status"),
        ("telegram_alert_outbox", "attempt_count"),
        ("telegram_alert_outbox", "next_attempt_at"),
        ("captcha_sampling_control", "enabled"),
        ("captcha_sampling_control", "sample_limit"),
        ("captcha_sampling_control", "updated_at"),
        ("captcha_sampling_control", "updated_by"),
        ("captcha_authority_control", "mode"),
        ("captcha_authority_control", "canary_limit"),
        ("captcha_authority_control", "local_decisions"),
        ("captcha_authority_control", "circuit_state"),
        ("captcha_authority_decisions", "event_id"),
        ("captcha_authority_decisions", "source"),
        ("captcha_authority_decisions", "portal_outcome"),
        ("post_appointment_reviews", "order_id"),
        ("post_appointment_reviews", "access_status"),
        ("post_appointment_reviews", "outcome"),
        ("post_appointment_reviews", "finished_at"),
        ("post_appointment_stage_snapshots", "review_id"),
        ("post_appointment_stage_snapshots", "stage_key"),
        ("post_appointment_stage_snapshots", "message_present"),
        ("post_appointment_stage_snapshots", "message_class"),
        ("post_appointment_stage_snapshots", "message_text"),
        ("post_appointment_automatic_reviews", "service_date"),
        ("post_appointment_automatic_reviews", "reservation_id"),
        ("post_appointment_automatic_reviews", "order_id"),
        ("post_appointment_automatic_reviews", "status"),
        ("post_appointment_automatic_reviews", "review_id"),
        ("post_appointment_automatic_reviews", "claimed_at"),
        ("post_appointment_automatic_reviews", "finished_at"),
        ("opportunity_bursts", "burst_id"),
        ("opportunity_bursts", "status"),
        ("opportunity_bursts", "admission_deadline_at"),
        ("opportunity_bursts", "max_active_sessions"),
        ("opportunity_burst_candidates", "candidate_id"),
        ("opportunity_burst_candidates", "queue_position"),
        ("opportunity_burst_candidates", "state"),
        ("opportunity_burst_executions", "execution_id"),
        ("opportunity_burst_executions", "role"),
        ("opportunity_burst_executions", "state"),
        ("opportunity_burst_executions", "first_read_at"),
        ("opportunity_burst_executions", "submitted_at"),
        ("slot_lost_reobservation_events", "event_key"),
        ("slot_lost_reobservation_events", "reobservation_id"),
        ("slot_lost_reobservation_events", "event_type"),
        ("slot_lost_reobservation_events", "original_attempt_id"),
        ("slot_lost_reobservation_events", "second_attempt_id"),
        ("opportunity_runtime_control", "burst_mode"),
        ("opportunity_runtime_control", "obs007_mode"),
        ("opportunity_runtime_control", "revision"),
        ("opportunity_runtime_control", "applied_revision"),
        ("opportunity_runtime_control", "circuit_state"),
    }
    columns = {
        (row["table_name"], row["column_name"])
        for row in connection.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema()"
        )
    }
    required_constraints = {
        "uq_portal_accounts_identity",
        "fk_service_orders_account_applicant",
        "ck_service_orders_lease_pair",
        "ck_service_orders_integral_terms",
        "uq_runs_order",
        "ck_runs_timestamps",
        "ck_runs_reservation_flags",
        "uq_reservations_order",
        "fk_reservations_run_order",
        "fk_payments_reservation_order",
        "ck_payments_paid_fields",
        "uq_payments_payment_order",
        "uq_payment_receipts_identity_payment_order",
        "fk_payment_receipts_payment_order",
        "fk_payment_receipts_correction_original",
        "ck_payment_receipts_movement",
        "fk_worker_state_current_order",
        "ck_whatsapp_messages_sent",
        "ck_whatsapp_messages_recipient",
        "ck_whatsapp_messages_confirmation_template_trace",
        "ck_whatsapp_messages_payment_template_trace",
        "ck_whatsapp_followup_messages_sent",
        "ck_whatsapp_followup_messages_recipient",
        "ck_whatsapp_followup_messages_template_trace",
        "ck_whatsapp_automation_job_review",
        "ck_whatsapp_automation_job_status",
        "ck_whatsapp_automation_job_attempt",
        "ck_whatsapp_automation_job_kind",
        "ck_whatsapp_automation_job_target",
        "fk_whatsapp_automation_jobs_reservation",
        "ck_appointment_reminder_control_lead_days",
        "ck_appointment_reminder_control_mode",
        "ck_appointment_reminder_day_target",
        "ck_post_appointment_reviews_timestamps",
        "ck_post_appointment_automatic_review_finished",
        "ck_opportunity_bursts_timestamps",
        "ck_opportunity_bursts_finished",
        "ck_opportunity_bursts_configured_max_sessions",
        "ck_opportunity_bursts_max_active_sessions",
        "ck_opportunity_burst_candidate_timestamps",
        "ck_opportunity_burst_execution_role",
        "ck_opportunity_burst_execution_finished",
        "ck_opportunity_burst_execution_timestamps",
        "ck_opportunity_runtime_control_circuit",
        "ck_opportunity_runtime_control_burst_mode",
        "ck_opportunity_runtime_control_obs007_mode",
        "ck_captcha_authority_circuit",
        "ck_captcha_authority_decision_resolution",
        "ck_finance_month_closure_reconciliation",
        "ck_payment_amount_reconciliation_reason",
    }
    constraint_rows = connection.execute(
        "SELECT conname, convalidated FROM pg_constraint "
        "WHERE connamespace = (SELECT oid FROM pg_namespace WHERE nspname = current_schema())"
    ).fetchall()
    constraints = {row["conname"] for row in constraint_rows}
    indexes = {
        row["indexname"]
        for row in connection.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema()"
        )
    }
    missing = sorted(required_tables - tables)
    missing.extend(f"{table}.{column}" for table, column in sorted(required_columns - columns))
    if "appointment_reminder_template_versions" in tables:
        missing.append("retired:appointment_reminder_template_versions")
    if ("appointment_reminder_control", "message_template") in columns:
        missing.append("retired:appointment_reminder_control.message_template")
    if (
        "whatsapp_followup_messages" in tables
        and ("whatsapp_followup_messages", "message_text") in columns
    ):
        empty_followup_text = connection.execute(
            """
            SELECT count(*) AS count
            FROM whatsapp_followup_messages
            WHERE NULLIF(BTRIM(message_text), '') IS NULL
            """
        ).fetchone()
        if empty_followup_text is None or int(empty_followup_text["count"]) != 0:
            missing.append("whatsapp_followup_messages.message_text empty")
    missing.extend(sorted(required_constraints - constraints))
    missing.extend(
        f"unvalidated:{row['conname']}"
        for row in constraint_rows
        if row["conname"] in required_constraints and not row["convalidated"]
    )
    if "idx_payments_order_created" not in indexes:
        missing.append("idx_payments_order_created")
    if "idx_order_checks_order_checked" not in indexes:
        missing.append("idx_order_checks_order_checked")
    if "idx_observer_window_metrics_date" not in indexes:
        missing.append("idx_observer_window_metrics_date")
    if "idx_reservation_attempts_order_created" not in indexes:
        missing.append("idx_reservation_attempts_order_created")
    if "uq_reservation_attempts_active_order" not in indexes:
        missing.append("uq_reservation_attempts_active_order")
    if "idx_worker_commands_pending" not in indexes:
        missing.append("idx_worker_commands_pending")
    if "idx_finance_entries_occurred" not in indexes:
        missing.append("idx_finance_entries_occurred")
    for index_name in (
        "idx_payment_receipts_received",
        "idx_payment_receipts_order_received",
        "idx_payment_receipts_payment_order",
        "idx_payment_receipts_correction_original",
    ):
        if index_name not in indexes:
            missing.append(index_name)
    if "idx_whatsapp_messages_order_prepared" not in indexes:
        missing.append("idx_whatsapp_messages_order_prepared")
    if "idx_whatsapp_followup_messages_order_prepared" not in indexes:
        missing.append("idx_whatsapp_followup_messages_order_prepared")
    if "idx_whatsapp_automation_jobs_queued" not in indexes:
        missing.append("idx_whatsapp_automation_jobs_queued")
    if "uq_whatsapp_contacts_username_lower" not in indexes:
        missing.append("uq_whatsapp_contacts_username_lower")
    if "uq_whatsapp_automation_jobs_running" not in indexes:
        missing.append("uq_whatsapp_automation_jobs_running")
    if "idx_reservations_appointment_day_confirmed" not in indexes:
        missing.append("idx_reservations_appointment_day_confirmed")
    if "idx_whatsapp_automation_jobs_priority" not in indexes:
        missing.append("idx_whatsapp_automation_jobs_priority")
    if "idx_captcha_shadow_outbox_pending" not in indexes:
        missing.append("idx_captcha_shadow_outbox_pending")
    if "idx_telegram_alert_outbox_pending" not in indexes:
        missing.append("idx_telegram_alert_outbox_pending")
    if "idx_captcha_authority_decisions_created" not in indexes:
        missing.append("idx_captcha_authority_decisions_created")
    if "idx_post_appointment_reviews_order_finished" not in indexes:
        missing.append("idx_post_appointment_reviews_order_finished")
    if "idx_post_appointment_automatic_reviews_status" not in indexes:
        missing.append("idx_post_appointment_automatic_reviews_status")
    for index_name in (
        "uq_opportunity_bursts_active",
        "idx_opportunity_bursts_started",
        "uq_opportunity_burst_candidates_order",
        "idx_opportunity_burst_candidates_state",
        "uq_opportunity_burst_detector",
        "uq_opportunity_burst_execution_candidate",
        "idx_opportunity_burst_executions_position",
        "idx_opportunity_burst_executions_order",
        "idx_slot_lost_reobservation_sequence",
        "idx_slot_lost_reobservation_burst",
    ):
        if index_name not in indexes:
            missing.append(index_name)
    receipt_triggers = {
        row["tgname"]
        for row in connection.execute(
            """
            SELECT trigger.tgname
            FROM pg_trigger trigger
            JOIN pg_class relation ON relation.oid = trigger.tgrelid
            JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = current_schema()
              AND relation.relname = 'payment_receipts'
              AND NOT trigger.tgisinternal
            """
        )
    }
    missing.extend(
        sorted(
            {
                "trg_payment_receipts_validate_insert",
                "trg_payment_receipts_immutable",
            }
            - receipt_triggers
        )
    )
    if missing:
        message = f"Database schema v{schema_version} is incomplete: "
        raise RuntimeError(message + ", ".join(missing))
