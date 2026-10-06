import type { ReminderMode } from '../states/states.contracts';

export interface AppointmentReminderStatus {
  service_date: string;
  appointment_day: string;
  current_time: string;
  scheduler_window_open: boolean;
  configuration: {
    enabled: boolean;
    dry_run: boolean;
    time: string;
    summary_grace_minutes: number;
    reconcile_seconds: number;
    send_interval_seconds: number;
    daily_limit: number;
    timezone: string;
    effective_lead_days: 1 | 2 | 3;
  };
  control: {
    mode: ReminderMode;
    lead_days: 1 | 2 | 3;
    message_template: string;
    default_template: string;
    revision: number;
    template_revision: number;
    updated_at: string;
    updated_by: string;
    applies_from: string;
    lead_days_applies_from: 'current_service_date' | 'next_service_date';
    existing_jobs_policy: 'preserved';
  };
  allowed_variables: Array<'nombre' | 'fecha' | 'hora' | 'sede'>;
  day: {
    status: string;
    summary_status: string | null;
    eligible_count: number;
    queued_count: number;
    existing_count: number;
    missing_contact_count: number;
    invalid_date_count: number;
    last_error: string | null;
    summary_alerted_at: string | null;
    last_reconciled_at: string;
  } | null;
  job_counts: Partial<Record<string, number>>;
  candidates: Array<{
    order_id: string;
    applicant_name: string | null;
    appointment_day: string;
    appointment_date_label: string;
    appointment_hour: string | null;
    site: string | null;
    recipient: string;
    status: string;
  }>;
  jobs: Array<{
    job_key: string;
    order_id: string;
    appointment_day: string;
    recipient: string;
    status: string;
    error_message: string | null;
    created_at: string;
    started_at: string | null;
    finished_at: string | null;
    updated_at: string;
  }>;
}

export type PostAppointmentOutcome =
  | 'upcoming'
  | 'awaiting_update'
  | 'in_progress'
  | 'completed'
  | 'observation_with_progress'
  | 'observation_no_progress'
  | 'access_lost'
  | 'portal_unavailable'
  | 'review_required';

export interface PostAppointmentStage {
  stage_key: string;
  stage_label: string;
  stage_date: string | null;
  stage_hour: string | null;
  status_text: string | null;
  message_present: boolean;
  message_class: 'none' | 'ok' | 'observation' | 'unknown';
  message_text: string | null;
}

export interface PostAppointmentFollowup {
  order_id: string;
  parent_order_id: string | null;
  applicant_name: string;
  document_number_masked: string;
  reservation_id: string;
  site: string | null;
  program_expediente: string | null;
  program_plate: string | null;
  appointment_date: string | null;
  appointment_hour: string | null;
  review_id: string | null;
  access_status:
  | 'not_checked'
  | 'success'
  | 'invalid_credentials'
  | 'workflow_unavailable'
  | 'portal_error';
  outcome: PostAppointmentOutcome;
  observation_count: number;
  later_progress_observed: boolean;
  error_code: string | null;
  error_message: string | null;
  last_reviewed_at: string | null;
  review_freshness: 'not_applicable' | 'not_reviewed' | 'current' | 'stale';
  next_automatic_review_at: string | null;
  stages: PostAppointmentStage[];
}

export interface PostAppointmentPayload {
  summary: {
    total_confirmed: number;
    active_followups: number;
    needs_attention: number;
    access_lost: number;
    progressed_or_completed: number;
  };
  filter_counts: {
    active: number;
    attention: number;
    observations: number;
    progressed: number;
    history: number;
    access_lost: number;
    completed: number;
  };
  automation: {
    enabled: boolean;
    timezone: string;
    time: string;
    daily_limit: number;
    due_count: number;
    running: number;
    completed_today: number;
    failed_today: number;
    last_run_at: string | null;
    breaker_open: boolean;
    breaker_reason: 'three_consecutive_technical_failures' | null;
  };
  upcoming?: Array<{
    order_id: string;
    applicant_name: string;
    document_number_masked: string;
    site: string | null;
    appointment_date: string | null;
    appointment_hour: string | null;
    program_expediente: string | null;
    program_plate: string | null;
  }>;
  pagination: { limit: number; offset: number; total: number };
  items: PostAppointmentFollowup[];
}

export interface PostAppointmentQuery {
  filter: 'active' | 'attention' | 'observations' | 'access_lost' | 'progressed' | 'history';
  search: string;
  sort: 'priority' | 'appointment_date' | 'last_reviewed_at' | 'applicant';
  direction: 'asc' | 'desc';
  limit: number;
  offset: number;
  include_upcoming: boolean;
}
