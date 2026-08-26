import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { RequestScope } from './request-cancellation';

import { ExcludedDateRange } from './reservation-rules.model';

export type { ExcludedDateRange } from './reservation-rules.model';

export interface HealthPayload {
  status: string;
  message: string;
  worker_running: boolean;
  reason: string;
  captcha_shadow_enabled: boolean;
}

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
  };
  control: {
    mode: 'disabled' | 'dry_run' | 'canary' | 'live';
    message_template: string;
    default_template: string;
    canary_order_ids: string[];
    revision: number;
    updated_at: string;
    updated_by: string;
    applies_from: 'next_reconciliation';
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

export interface WhatsAppMessageTemplate {
  status: 'ok';
  template_key: string;
  display_name: string;
  message_template: string;
  recommended_template: string;
  allowed_variables: string[];
  required_variables: string[];
  optional_line_variables: string[];
  revision: number;
  enabled: boolean;
  updated_at: string;
  updated_by: string;
  preview: string;
  preview_context: Record<string, string>;
  usage: string;
  applies_from:
    | 'next_prepared_job'
    | 'next_prepared_message'
    | 'next_prepared_followup'
    | 'next_reconciliation';
  consumer_connected: boolean;
}

export interface WhatsAppMessageTemplatesResponse {
  status: 'ok';
  templates: WhatsAppMessageTemplate[];
}

export interface WhatsAppMessageTemplatePreview {
  status: 'ok';
  template_key: string;
  preview: string;
  preview_context: Record<string, string>;
  persists: false;
  sends_message: false;
}

export interface WorkerStatus {
  phase?: string;
  paused?: boolean;
  current_order_id?: string | null;
  masked_account?: string | null;
  session_started_at?: string | null;
  last_check_at?: string | null;
  next_check_at?: string | null;
  confirmed_reservations?: number;
  consecutive_errors?: number;
  last_error?: string | null;
  updated_at?: string | null;
  worker_running?: boolean;
  continuous_worker_enabled?: boolean;
  owner_token?: string | null;
  lease_expires_at?: string | null;
  availability_signature?: string | null;
}

export type OpportunityControlTarget = 'obs006' | 'obs007';
export type OpportunityControlAction = 'activate' | 'deactivate' | 'drain' | 'reset_breaker';

export interface OpportunityControlMode {
  desired_mode: string;
  effective_mode: string;
  admissions_allowed: boolean;
}

export interface OpportunityActiveBurst {
  burst_id: string;
  status: string;
  started_at: string;
  max_active_sessions: number;
  scheduled_clients: number;
  completion_reason: string | null;
}

export interface OpportunityControl {
  revision: number;
  source: string;
  obs006: OpportunityControlMode;
  obs007: OpportunityControlMode;
  breaker: {
    state: string;
    reason: string | null;
    opened_at: string | null;
  };
  active_burst: OpportunityActiveBurst | null;
  updated_at: string | null;
  updated_by: string | null;
  pending_application: boolean;
  status?: string;
  message?: string;
}

export interface OpportunityBurst {
  burst_id: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  completion_reason: string | null;
  max_active_sessions: number;
  candidate_count: number;
  scheduled_clients: number;
}

export interface OpportunityBurstsResponse {
  bursts: OpportunityBurst[];
}

export interface OpportunityControlActionPayload {
  action: OpportunityControlAction;
  target: OpportunityControlTarget;
  reason: string;
  expected_revision: number;
}

export interface CaptchaSamplingControl {
  enabled: boolean;
  sample_limit: number;
  effective_sample_limit: number;
  estimated_extra_seconds: number;
  applies_from: 'next_captcha_batch';
  rapid_mode_effective_sample_limit: 1;
  updated_at: string | null;
  updated_by: string;
  source: 'database' | 'environment_fallback';
}

export interface CaptchaAuthorityControl {
  mode: '2captcha' | 'canary';
  canary_limit: number;
  local_decisions: number;
  local_confirmed: number;
  local_rejected: number;
  fallback_decisions: number;
  remaining_local_decisions: number;
  local_admission_open: boolean;
  min_char_confidence: number;
  sequence_confidence_product: number;
  timeout_ms: number;
  circuit_state: 'closed' | 'open';
  circuit_reason: string | null;
  circuit_opened_at: string | null;
  activated_at: string | null;
  updated_at: string;
  updated_by: string;
  applies_from: 'next_reservation_captcha';
  rollback: { mode: '2captcha' };
}

export interface ServiceOrder {
  order_id: string;
  applicant_id: string;
  applicant_name: string | null;
  document_number_masked: string;
  document_type: 'dni' | 'foreign_resident_card';
  contact_name: string | null;
  contact_whatsapp_masked: string | null;
  contact_whatsapp_username_masked: string | null;
  contact_source: string | null;
  priority: number;
  charge_required: boolean;
  service_type: 'standard' | 'selected_weekday' | 'custom';
  reservation_price: string;
  status: string;
  reservation_status: string | null;
  reservation_site: string | null;
  reservation_date: string | null;
  reservation_hour: string | null;
  payment_status: string | null;
  amount_agreed: string | null;
  amount_paid: string | null;
  whatsapp_message_status: string | null;
  whatsapp_message_sent_at: string | null;
  whatsapp_message_action_state: WhatsAppActionState;
  whatsapp_followup_status: string | null;
  whatsapp_followup_sent_at: string | null;
  whatsapp_followup_action_state: WhatsAppActionState;
  parent_order_id: string | null;
  program_expediente: string | null;
  program_plate: string | null;
  closure_reason: string | null;
  closure_note: string | null;
  closed_at: string | null;
  minimum_reservation_hour: number | null;
  minimum_reservation_date: string | null;
  maximum_reservation_date: string | null;
  allowed_weekdays: number[] | null;
  excluded_date_ranges: ExcludedDateRange[];
  preflight_status: 'not_required' | 'pending' | 'running' | 'validated' | 'failed';
  preflight_message: string | null;
  preflight_started_at: string | null;
  preflight_validated_at: string | null;
  preflight_details: Record<string, unknown> | null;
  preflight_cycle: number;
  registration_notice_type: string | null;
  registration_notice_status: WhatsAppActionState | null;
  registration_notice_updated_at: string | null;
  registration_notice_error: string | null;
  created_at: string;
  updated_at: string;
}

export type WhatsAppActionState =
  | 'manual_required'
  | 'queued'
  | 'blocked'
  | 'running'
  | 'sent'
  | 'failed'
  | 'uncertain'
  | 'resolved'
  | 'not_applicable';

export interface ServiceOrderDetail extends ServiceOrder {
  document_number: string;
  contact_whatsapp: string | null;
  contact_whatsapp_username: string | null;
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
  items: PostAppointmentFollowup[];
}

export interface RunSummary {
  run_id: string;
  order_id: string | null;
  status: string;
  message: string;
  exit_code: number;
  started_at: string;
  finished_at: string;
  duration_seconds: number;
  reservation_attempted: boolean;
  reservation_confirmed: boolean;
  screenshot_count?: number;
  screenshot_path?: string | null;
  screenshot_paths?: string[];
  details?: Record<string, unknown> | null;
  created_at?: string;
}

export type RunDetail = RunSummary;

export interface CaptchaPrediction {
  model_name: 'v1_real' | 'v2_scratch' | 'v2_selected' | 'v3_selected' | string;
  prediction: string;
  mean_confidence: number;
  min_char_confidence: number;
  sequence_confidence_product: number;
  char_confidences: number[];
  inference_ms: number;
  created_at_utc: string;
}

export interface CaptchaEvent {
  event_id: string;
  image_sha256: string;
  received_at_utc: string;
  external_answer: string | null;
  external_source: '2captcha' | 'v6' | null;
  external_solve_ms: number | null;
  portal_accepted: boolean | null;
  review_priority_reason:
    | 'canary_v6'
    | 'anomaly'
    | 'model_disagreement'
    | 'control_sample'
    | null;
  human_label: {
    review_id: number;
    event_id: string;
    image_sha256: string;
    answer: string;
    reviewer: string;
    note: string;
    supersedes_id: number | null;
    created_at_utc: string;
  } | null;
  selected_matches_external: boolean;
  selected_model_name: string | null;
  image_url: string;
  metadata: {
    run_id?: string | null;
    order_id?: string | null;
    attempt?: number | null;
    captured_at_utc?: string | null;
    source_image_kind?: string | null;
    detection_origin?: string | null;
    backfilled?: boolean | null;
    observer?: number | boolean | null;
    portal_stage?: string | null;
  };
  predictions: CaptchaPrediction[];
}

export interface CaptchaSummary {
  status: string;
  device: string | null;
  models: string[];
  selected_model: string;
  started_at_utc: string | null;
  stats: {
    events: number;
    with_external_answer: number;
    portal_accepted: number;
    human_labeled: number;
    models: Record<
      string,
      {
        predictions: number;
        matches_external: number;
        accepted_reference_total: number;
        matches_accepted_reference: number;
        accepted_reference_accuracy: number | null;
        average_inference_ms: number;
      }
    >;
  };
  outbox: { pending: number; processed: number; attempts: number };
}

export interface CaptchaEventsPage {
  events: CaptchaEvent[];
  pagination: { page: number; page_size: number; total: number; total_pages: number };
  filters: {
    q: string;
    agreement: string;
    portal_status: string;
    source: string;
    review_status: string;
    review_scope: string;
    sort: string;
  };
}

export interface CaptchaHumanLabelResponse {
  event: CaptchaEvent;
}

export type CaptchaQualityCaseType =
  'wrong' | 'high_confidence_wrong' | 'unanimous_wrong' | 'majority_wrong' | 'disagreement';

export interface CaptchaMetricDistribution {
  samples: number;
  average: number | null;
  p50: number | null;
  p90: number | null;
}

export interface CaptchaQualityModel {
  model_name: string;
  predictions: number;
  evaluated: number;
  correct: number;
  accuracy: number | null;
  confidence: {
    average: number | null;
    correct_average: number | null;
    wrong_average: number | null;
  };
  inference_ms: CaptchaMetricDistribution;
}

export interface CaptchaQualityWeek {
  week: string;
  validated: number;
  models: Record<string, { evaluated: number; correct: number; accuracy: number | null }>;
}

export interface CaptchaQuality {
  events: number;
  validated_images: number;
  weeks_observed: number;
  trend_ready: boolean;
  models: CaptchaQualityModel[];
  ensemble: {
    unanimous: number;
    unanimous_validated: number;
    unanimous_wrong: number;
    majority: number;
    majority_wrong: number;
    all_different: number;
  };
  weekly: CaptchaQualityWeek[];
  useful_case_counts: Record<CaptchaQualityCaseType, number>;
  local_total_ms: CaptchaMetricDistribution;
  external_solver_ms: CaptchaMetricDistribution;
  definitions: {
    accuracy_reference: string;
    percentile_method: string;
    high_confidence_threshold: number;
  };
}

export interface CaptchaQualityCase {
  event_id: string;
  image_sha256: string;
  received_at_utc: string;
  human_answer: string;
  case_types: CaptchaQualityCaseType[];
  agreement_types: Array<'unanimous' | 'majority' | 'all_different'>;
  consensus_answer: string;
  vote_count: number;
  wrong_models: string[];
  high_confidence_wrong_models: string[];
  external_answer: string | null;
  external_solve_ms: number | null;
  portal_accepted: boolean | null;
  image_url: string;
  metadata: CaptchaEvent['metadata'];
  predictions: CaptchaPrediction[];
}

export interface CaptchaQualityCasesPage {
  cases: CaptchaQualityCase[];
  pagination: { page: number; page_size: number; total: number; total_pages: number };
  filters: { type: CaptchaQualityCaseType };
}

interface ServiceOrdersResponse {
  service_orders: ServiceOrder[];
}

interface RunsResponse {
  runs: RunSummary[];
}

interface WorkerCommandsResponse {
  commands: WorkerCommand[];
}

interface ManualSessionsResponse {
  manual_sessions: ManualSession[];
}

export interface ManualSession {
  session_id: string;
  order_id: string;
  username: string;
  mode: ManualSessionMode;
  order_status: string;
  status: string;
  status_message: string | null;
  started_at: string;
  updated_at: string;
  close_requested: boolean;
  diagnostic_report_path: string | null;
  diagnostic_event_count: number;
  diagnostic_submission_seen: boolean;
  diagnostic_honeypot_blocked: boolean;
}

export type ManualSessionMode = 'appointment' | 'portal' | 'diagnostic';

export interface MonthlySummary {
  month: string;
  period: { start: string; end: string };
  metrics: {
    revenue_collected: number;
    payments_received: number;
    reservations_confirmed: number;
    orders_created: number;
    active_orders: number;
    pending_payments: number;
    pending_amount: number;
    average_ticket: number;
    conversion_rate: number;
  };
  previous: {
    month: string;
    revenue_collected: number;
    payments_received: number;
  };
  daily_revenue: Array<{ date: string; amount: number; payments: number }>;
  sources: Array<{
    source: string;
    orders_created: number;
    reservations_confirmed: number;
    revenue_collected: number;
  }>;
  attention: {
    missing_contact_count: number;
    pending_payments: Array<{
      order_id: string;
      name: string;
      source: string;
      amount_agreed: number;
      reservation_date: string | null;
      reservation_hour: string | null;
    }>;
    aged_active_orders: Array<{
      order_id: string;
      name: string;
      status: string;
      created_date: string;
    }>;
  };
}

export interface MetricRatio {
  value: number;
  numerator: number;
  denominator: number;
}

export interface MetricPeriod {
  start: string;
  end_exclusive: string;
  coverage_end_exclusive: string;
  is_closed: boolean;
}

export interface MonthlyEventMetrics {
  orders_created: number;
  confirmed_reservation_events: number;
  orders_reserved: number;
  payments_received: number;
  revenue_collected: number;
  average_ticket: MetricRatio;
  daily_revenue: Array<{ date: string; amount: number; payments: number }>;
}

export interface MonthlyPeriodMetrics extends MonthlyEventMetrics {
  period: MetricPeriod;
}

export interface MonthlySummaryV2 {
  contract_version: '2.0';
  month: string;
  as_of: string;
  period_metrics: MonthlyPeriodMetrics;
  cohort_metrics: {
    cohort: {
      created_from: string;
      created_to_exclusive: string;
      outcomes_observed_as_of: string;
    };
    orders_created: number;
    orders_ever_reserved: number;
    orders_ever_paid: number;
    revenue_ever_collected: number;
    reservation_conversion_rate: MetricRatio;
    payment_conversion_rate: MetricRatio;
    funnel: {
      validated: {
        orders_created: number;
        orders_ever_reserved: number;
        orders_ever_paid: number;
      };
      legacy_not_required: {
        orders_created: number;
        orders_ever_reserved: number;
        orders_ever_paid: number;
      };
      note: string;
    };
    sources: Array<{
      source: string;
      orders_created: number;
      order_creation_source_orders: number;
      historical_backfill_source_orders: number;
      orders_ever_reserved: number;
      orders_ever_paid: number;
      revenue_ever_collected: number;
    }>;
    source_semantics: {
      preferred: string;
      historical_backfill: string;
      historical_fallback: string;
      frozen_storage_available: boolean;
    };
  };
  current_attention_snapshot: {
    as_of: string;
    active_orders: number;
    missing_contact_count: number;
    valid_contact_rule: string;
    pending_payments: number;
    pending_amount: number;
    pending_payment_items: Array<{
      order_id: string;
      name: string;
      source: string;
      pending_amount: number;
      reservation_date: string | null;
      reservation_hour: string | null;
    }>;
    aged_active_orders: Array<{
      order_id: string;
      name: string;
      status: string;
      created_date: string;
    }>;
    list_limit: number;
  };
  comparisons: {
    same_day_window: {
      elapsed_days: number;
      selected: { period: MetricPeriod; metrics: MonthlyEventMetrics };
      previous: { period: MetricPeriod; metrics: MonthlyEventMetrics };
    } | null;
    closed_months: {
      selected: { period: MetricPeriod; metrics: MonthlyEventMetrics };
      previous: { period: MetricPeriod; metrics: MonthlyEventMetrics };
    };
  };
}

export interface FinanceCategory {
  category_code: string;
  display_name: string;
  cost_behavior: 'variable' | 'fixed' | 'mixed';
  active: boolean;
}

export type FinanceEntryKind = 'expense' | 'prepaid_topup' | 'prepaid_consumption' | 'refund';
export type FinanceDataQuality = 'actual' | 'estimated' | 'pending';

export interface FinanceEntry {
  entry_id: string;
  occurred_on: string;
  entry_kind: FinanceEntryKind;
  category_code: string;
  category_name?: string;
  cost_behavior?: string;
  vendor: string | null;
  description: string;
  amount_original: number;
  currency: string;
  exchange_rate_pen: number | null;
  amount_pen: number | null;
  quantity: number | null;
  unit: string | null;
  channel: string | null;
  campaign: string | null;
  order_id: string | null;
  evidence_reference: string | null;
  notes: string | null;
  data_quality: FinanceDataQuality;
  status: 'active' | 'voided';
  voided_at: string | null;
  void_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface FinanceEntryPayload {
  occurred_on: string;
  entry_kind: FinanceEntryKind;
  category_code: string;
  vendor?: string | null;
  description: string;
  amount_original: string;
  currency: string;
  exchange_rate_pen?: string | null;
  quantity?: string | null;
  unit?: string | null;
  channel?: string | null;
  campaign?: string | null;
  order_id?: string | null;
  evidence_reference?: string | null;
  notes?: string | null;
  data_quality: FinanceDataQuality;
}

export interface FinanceSummary {
  month: string;
  revenue_collected: number;
  recognized_costs: number;
  operating_margin_before_unregistered_costs: number;
  net_cash_outflow: number;
  prepaid_topups: number;
  prepaid_consumption: number;
  unconverted_entries: number;
  active_entries: number;
  is_complete: boolean;
  conversion_complete?: boolean;
  cost_capture_complete?: null;
  completeness_semantics?: string;
  by_category: Array<{
    category_code: string;
    category_name: string;
    recognized_cost: number;
  }>;
}

export type PaymentResolutionType = 'discount' | 'waiver' | 'correction';

export interface FinanceDataQualitySummary {
  month: string;
  data_quality: Record<FinanceDataQuality, {
    entry_count: number;
    amount_pen: number;
    unconverted_count: number;
  }>;
  unconverted_entries: Array<{
    entry_id: string;
    occurred_on: string;
    entry_kind: FinanceEntryKind;
    category_code: string;
    description: string;
    amount_original: number;
    currency: string;
    data_quality: FinanceDataQuality;
  }>;
  paid_amount_mismatches: Array<{
    payment_id: string;
    order_id: string;
    amount_agreed: number | null;
    amount_paid: number | null;
    difference: number | null;
    currency: string;
    paid_at: string | null;
    reconciliation: {
      resolution_type: PaymentResolutionType;
      reason: string;
      reconciled_by: string;
      reconciled_at: string;
    } | null;
  }>;
  unreconciled_paid_amount_mismatch_count: number;
}

export interface FinanceMonthClosure {
  month: string;
  closure: {
    opening_prepaid_balance: number | null;
    closing_prepaid_balance: number | null;
    status: 'draft' | 'reconciled';
    reconciled_at: string | null;
    reconciled_by: string | null;
    notes: string | null;
    created_at: string;
    updated_at: string;
  } | null;
  movements: {
    prepaid_topups: number;
    prepaid_consumption: number;
    refunds: number;
    prepaid_refunds: number;
    pending_entries: number;
    unconverted_entries: number;
    estimated_entries: number;
  };
  expected_closing_prepaid_balance: number | null;
  balance_difference: number | null;
}

export interface FinanceMonthClosurePayload {
  month: string;
  opening_prepaid_balance: string | null;
  closing_prepaid_balance: string | null;
  status: 'draft' | 'reconciled';
  reconciled_by: string | null;
  notes: string | null;
}

export interface ApiActionResponse {
  status: string;
  message?: string;
  command_id?: string;
  command?: string;
  released_backoff_count?: number;
  protected_backoff_count?: number;
  session_id?: string;
  mode?: ManualSessionMode;
  order_status?: string;
  order_id?: string;
  applicant_id?: string;
  portal_account_id?: string;
  contact_id?: string | null;
  parent_order_id?: string;
  parent_archived?: boolean;
  service_orders?: ApiActionResponse[];
  sent_at?: string | null;
  test_mode?: boolean;
}

export interface ContactUpdatePayload {
  contact_whatsapp?: string | null;
  contact_whatsapp_username?: string | null;
  contact_name?: string | null;
  contact_source?: string | null;
}

export interface PriorityUpdatePayload {
  priority: number;
}

export interface ReservationRestrictionsUpdatePayload {
  minimum_reservation_date: string | null;
  maximum_reservation_date: string | null;
  allowed_weekdays: number[] | null;
  excluded_date_ranges: ExcludedDateRange[];
}

export interface PaymentPaidPayload {
  amount_paid: string;
  amount_agreed?: string | null;
  expected_payment_status?: string | null;
  expected_amount_agreed?: string | null;
  expected_amount_paid?: string | null;
}

export interface WhatsAppMessagePackage {
  message_id: string;
  order_id: string | null;
  test_mode: boolean;
  status: 'prepared' | 'sent';
  recipient_phone: string | null;
  recipient_phone_masked: string | null;
  recipient_username: string | null;
  recipient_label: string;
  greeting: string;
  evidence_caption: string;
  payment_message: string;
  whatsapp_url: string | null;
  attachment_url: string;
  payment_attachment_url: string;
  prepared_at: string;
  sent_at: string | null;
}

export interface WhatsAppFollowUpStep {
  title: string;
  text: string;
  attachment_urls: string[];
}

export interface WhatsAppFollowUpPackage {
  message_id: string;
  order_id: string | null;
  test_mode: boolean;
  status: 'prepared' | 'sent';
  recipient_phone: string | null;
  recipient_phone_masked: string | null;
  recipient_username: string | null;
  recipient_label: string;
  steps: WhatsAppFollowUpStep[];
  combined_text: string;
  prepared_at: string;
  sent_at: string | null;
}

export type WhatsAppReviewResolution =
  | 'confirmed_complete'
  | 'completed_missing'
  | 'dismissed';

export interface WhatsAppReviewJob {
  job_key: string;
  order_id: string;
  job_kind: 'reservation_album' | 'post_payment_followup';
  status: 'failed' | 'uncertain';
  message_id: string | null;
  error_message: string | null;
  review_resolution: WhatsAppReviewResolution | null;
  review_note: string | null;
  reviewed_at: string | null;
  reviewed_by: string | null;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
}

export interface WhatsAppReviewPayload {
  job: WhatsAppReviewJob;
  message: WhatsAppFollowUpPackage | null;
}

export interface WhatsAppReviewResponse extends ApiActionResponse {
  job_key: string;
  resolution: WhatsAppReviewResolution;
  note: string | null;
  reviewed_at: string;
  reviewed_by: string;
}

export interface WhatsAppWebDraftResponse {
  status: 'login_required' | 'session_ready' | 'draft_ready' | 'web_unavailable' | 'sent';
  message: string;
  message_id: string | null;
  manual_send_required: boolean;
  sent: boolean;
  sent_at?: string | null;
  qr_image_data_url?: string | null;
  draft_mode?:
    'caption' | 'queued_text' | 'album' | 'documents' | 'image_sequence' | 'document_sequence';
}

export interface CloseServiceOrderPayload {
  closure_reason: string;
  closure_note?: string | null;
}

export interface CreateServiceOrderPayload {
  document_number: string;
  document_type: 'dni' | 'foreign_resident_card';
  password: string;
  contact_name: string;
  contact_source: string;
  priority?: number;
  contact_whatsapp?: string | null;
  contact_whatsapp_username?: string | null;
  applicant_name?: string | null;
  charge_required?: boolean;
  service_type?: 'standard' | 'selected_weekday' | 'custom';
  reservation_price?: string;
  minimum_reservation_date?: string | null;
  maximum_reservation_date?: string | null;
  allowed_weekdays?: number[] | null;
  excluded_date_ranges?: ExcludedDateRange[];
  parent_order_id?: string | null;
  program_expediente?: string | null;
  program_plate?: string | null;
}

export interface CredentialsUpdatePayload {
  document_number: string;
  document_type: 'dni' | 'foreign_resident_card';
  password: string;
}

export interface WorkerCommand {
  command_id: string;
  command: string;
  status: string;
  requested_by: string | null;
  requested_at: string;
  claimed_at: string | null;
  processed_at: string | null;
  error_message: string | null;
}

@Injectable({ providedIn: 'root' })
export class AppointmentApiService {
  private readonly http = inject(HttpClient);

  async getHealth(scope?: RequestScope): Promise<HealthPayload> {
    return this.read<HealthPayload>('/health', scope);
  }

  async getWorker(scope?: RequestScope): Promise<WorkerStatus> {
    return this.read<WorkerStatus>('/api/v1/worker', scope);
  }

  async getAppointmentReminders(scope?: RequestScope): Promise<AppointmentReminderStatus> {
    return this.read<AppointmentReminderStatus>('/api/v1/appointment-reminders', scope);
  }

  async updateAppointmentReminders(payload: {
    mode: AppointmentReminderStatus['control']['mode'];
    message_template: string;
    canary_order_ids: string[];
    expected_revision: number;
  }): Promise<AppointmentReminderStatus> {
    return this.post<AppointmentReminderStatus>('/api/v1/appointment-reminders', payload);
  }

  async getWhatsAppMessageTemplates(
    scope?: RequestScope,
  ): Promise<WhatsAppMessageTemplate[]> {
    const response = await this.read<WhatsAppMessageTemplatesResponse>(
      '/api/v1/whatsapp-message-templates',
      scope,
    );
    return response.templates;
  }

  async previewWhatsAppMessageTemplate(
    templateKey: string,
    messageTemplate: string,
  ): Promise<WhatsAppMessageTemplatePreview> {
    return this.post<WhatsAppMessageTemplatePreview>(
      `/api/v1/whatsapp-message-templates/${encodeURIComponent(templateKey)}/preview`,
      { message_template: messageTemplate },
    );
  }

  async updateWhatsAppMessageTemplate(
    templateKey: string,
    messageTemplate: string,
    expectedRevision: number,
  ): Promise<WhatsAppMessageTemplate> {
    return this.put<WhatsAppMessageTemplate>(
      `/api/v1/whatsapp-message-templates/${encodeURIComponent(templateKey)}`,
      {
        message_template: messageTemplate,
        expected_revision: expectedRevision,
      },
    );
  }

  async getOpportunityControl(scope?: RequestScope): Promise<OpportunityControl> {
    return this.read<OpportunityControl>('/api/v1/runtime-controls/opportunity', scope);
  }

  async updateOpportunityControl(
    payload: OpportunityControlActionPayload,
  ): Promise<OpportunityControl> {
    return this.post<OpportunityControl>('/api/v1/runtime-controls/opportunity', payload);
  }

  async getOpportunityBursts(scope?: RequestScope): Promise<OpportunityBurstsResponse> {
    return this.read<OpportunityBurstsResponse>('/api/v1/opportunity-bursts', scope);
  }

  async getCaptchaSamplingControl(scope?: RequestScope): Promise<CaptchaSamplingControl> {
    return this.read<CaptchaSamplingControl>(
      '/api/v1/runtime-controls/captcha-sampling',
      scope,
    );
  }

  async updateCaptchaSamplingControl(
    enabled: boolean,
    sampleLimit: number,
  ): Promise<CaptchaSamplingControl> {
    return this.post<CaptchaSamplingControl>('/api/v1/runtime-controls/captcha-sampling', {
      enabled,
      sample_limit: sampleLimit,
    });
  }

  async getCaptchaAuthorityControl(scope?: RequestScope): Promise<CaptchaAuthorityControl> {
    return this.read<CaptchaAuthorityControl>(
      '/api/v1/runtime-controls/captcha-authority',
      scope,
    );
  }

  async updateCaptchaAuthorityControl(
    mode: CaptchaAuthorityControl['mode'],
    resetCircuit = false,
  ): Promise<CaptchaAuthorityControl> {
    return this.post<CaptchaAuthorityControl>('/api/v1/runtime-controls/captcha-authority', {
      mode,
      reset_circuit: resetCircuit,
    });
  }

  async getServiceOrders(scope?: RequestScope): Promise<ServiceOrder[]> {
    const response = await this.read<ServiceOrdersResponse>('/api/v1/service-orders', scope);
    return response.service_orders;
  }

  async getServiceOrder(orderId: string): Promise<ServiceOrderDetail> {
    return firstValueFrom(
      this.http.get<ServiceOrderDetail>(`/api/v1/service-orders/${encodeURIComponent(orderId)}`),
    );
  }

  async getPostAppointmentFollowups(scope?: RequestScope): Promise<PostAppointmentPayload> {
    return this.read<PostAppointmentPayload>('/api/v1/post-appointment-followups', scope);
  }

  async reviewPostAppointment(orderId: string): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/post-appointment/review`,
      {},
    );
  }

  async getRuns(scope?: RequestScope): Promise<RunSummary[]> {
    const response = await this.read<RunsResponse>('/api/v1/runs?limit=50', scope);
    return response.runs;
  }

  async getRun(runId: string): Promise<RunDetail> {
    return firstValueFrom(this.http.get<RunDetail>(`/api/v1/runs/${encodeURIComponent(runId)}`));
  }

  async getCaptchaSummary(scope?: RequestScope): Promise<CaptchaSummary> {
    return this.read<CaptchaSummary>('/api/v1/captcha-shadow/summary', scope);
  }

  async getCaptchaEvents(
    page: number,
    pageSize: number,
    query: string,
    agreement: string,
    portalStatus: string,
    source: string,
    reviewStatus: string,
    sort: string,
    reviewScope: 'all' | 'targeted',
    scope?: RequestScope,
  ): Promise<CaptchaEventsPage> {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
      q: query,
      agreement,
      portal_status: portalStatus,
      source,
      review_status: reviewStatus,
      review_scope: reviewScope,
      sort,
    });
    return this.read<CaptchaEventsPage>(
      `/api/v1/captcha-shadow/events?${params.toString()}`,
      scope,
    );
  }

  async saveCaptchaHumanLabel(
    eventId: string,
    imageSha256: string,
    answer: string,
  ): Promise<CaptchaHumanLabelResponse> {
    return this.post<CaptchaHumanLabelResponse>(
      `/api/v1/captcha-shadow/events/${encodeURIComponent(eventId)}/human-label`,
      { answer, expected_image_sha256: imageSha256 },
    );
  }

  async getCaptchaQuality(scope?: RequestScope): Promise<CaptchaQuality> {
    return this.read<CaptchaQuality>('/api/v1/captcha-shadow/quality', scope);
  }

  async getCaptchaQualityCases(
    caseType: CaptchaQualityCaseType,
    page: number,
    pageSize: number,
    scope?: RequestScope,
  ): Promise<CaptchaQualityCasesPage> {
    const params = new URLSearchParams({
      type: caseType,
      page: String(page),
      page_size: String(pageSize),
    });
    return this.read<CaptchaQualityCasesPage>(
      `/api/v1/captcha-shadow/quality/cases?${params.toString()}`,
      scope,
    );
  }

  async downloadCaptchaDataset(scope?: RequestScope): Promise<Blob> {
    const request = this.http.get('/api/v1/captcha-shadow/dataset/export', {
      responseType: 'blob',
    });
    return scope ? scope.read(request) : firstValueFrom(request);
  }

  async getWorkerCommands(scope?: RequestScope): Promise<WorkerCommand[]> {
    const response = await this.read<WorkerCommandsResponse>(
      '/api/v1/worker/commands?limit=20',
      scope,
    );
    return response.commands;
  }

  async getManualSessions(scope?: RequestScope): Promise<ManualSession[]> {
    const response = await this.read<ManualSessionsResponse>('/api/v1/manual-sessions', scope);
    return response.manual_sessions;
  }

  async getMonthlySummary(month: string, scope?: RequestScope): Promise<MonthlySummary> {
    return this.read<MonthlySummary>(
      `/api/v1/monthly-summary?month=${encodeURIComponent(month)}`,
      scope,
    );
  }

  async getMonthlySummaryV2(month: string, scope?: RequestScope): Promise<MonthlySummaryV2> {
    return this.read<MonthlySummaryV2>(
      `/api/v2/monthly-summary?month=${encodeURIComponent(month)}`,
      scope,
    );
  }

  async getFinanceCategories(scope?: RequestScope): Promise<FinanceCategory[]> {
    const response = await this.read<{ categories: FinanceCategory[] }>(
      '/api/v1/finance/categories',
      scope,
    );
    return response.categories;
  }

  async getFinanceEntries(month: string, scope?: RequestScope): Promise<FinanceEntry[]> {
    const response = await this.read<{ entries: FinanceEntry[] }>(
      `/api/v1/finance/entries?month=${encodeURIComponent(month)}&include_voided=1`,
      scope,
    );
    return response.entries;
  }

  async getFinanceSummary(month: string, scope?: RequestScope): Promise<FinanceSummary> {
    return this.read<FinanceSummary>(
      `/api/v1/finance/summary?month=${encodeURIComponent(month)}`,
      scope,
    );
  }

  async getFinanceDataQuality(
    month: string,
    scope?: RequestScope,
  ): Promise<FinanceDataQualitySummary> {
    return this.read<FinanceDataQualitySummary>(
      `/api/v1/finance/data-quality?month=${encodeURIComponent(month)}`,
      scope,
    );
  }

  async getFinanceMonthClosure(
    month: string,
    scope?: RequestScope,
  ): Promise<FinanceMonthClosure> {
    return this.read<FinanceMonthClosure>(
      `/api/v1/finance/month-closure?month=${encodeURIComponent(month)}`,
      scope,
    );
  }

  async saveFinanceMonthClosure(
    payload: FinanceMonthClosurePayload,
  ): Promise<FinanceMonthClosure & { status: string }> {
    return this.post<FinanceMonthClosure & { status: string }>(
      '/api/v1/finance/month-closure',
      payload,
    );
  }

  async reconcileFinancePaymentAmount(
    paymentId: string,
    payload: { resolution_type: PaymentResolutionType; reason: string; reconciled_by: string },
  ): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>(
      `/api/v1/finance/payments/${encodeURIComponent(paymentId)}/reconcile-amount`,
      payload,
    );
  }

  async createFinanceEntry(payload: FinanceEntryPayload): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>('/api/v1/finance/entries', payload);
  }

  async updateFinanceEntry(
    entryId: string,
    payload: FinanceEntryPayload,
  ): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>(
      `/api/v1/finance/entries/${encodeURIComponent(entryId)}/edit`,
      payload,
    );
  }

  async voidFinanceEntry(entryId: string, reason: string): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>(
      `/api/v1/finance/entries/${encodeURIComponent(entryId)}/void`,
      { reason },
    );
  }

  async updateServiceOrderContact(
    orderId: string,
    payload: ContactUpdatePayload,
  ): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/contact`,
      payload,
    );
  }

  async updateServiceOrderCredentials(
    orderId: string,
    payload: CredentialsUpdatePayload,
  ): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/credentials`,
      payload,
    );
  }

  async updateServiceOrderPriority(
    orderId: string,
    payload: PriorityUpdatePayload,
  ): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/priority`,
      payload,
    );
  }

  async updateServiceOrderRestrictions(
    orderId: string,
    payload: ReservationRestrictionsUpdatePayload,
  ): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/restrictions`,
      payload,
    );
  }

  async runServiceOrderAction(
    orderId: string,
    action: 'pause' | 'activate' | 'no-charge' | 'done',
  ): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/${action}`,
      {},
    );
  }

  async closeServiceOrder(
    orderId: string,
    payload: CloseServiceOrderPayload,
  ): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/close`,
      payload,
    );
  }

  async markPaymentPaid(orderId: string, payload: PaymentPaidPayload): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/payment/paid`,
      payload,
    );
  }

  async recordPartialPayment(
    orderId: string,
    payload: PaymentPaidPayload,
  ): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/payment/partial`,
      payload,
    );
  }

  async prepareWhatsAppTest(recipientPhone: string): Promise<WhatsAppMessagePackage> {
    return this.post<WhatsAppMessagePackage>('/api/v1/whatsapp-messages/test/prepare', {
      recipient_phone: recipientPhone,
    });
  }

  async prepareWhatsAppFollowUpTest(recipientPhone: string): Promise<WhatsAppFollowUpPackage> {
    return this.post<WhatsAppFollowUpPackage>('/api/v1/whatsapp-followup-messages/test/prepare', {
      recipient_phone: recipientPhone,
    });
  }

  async prepareOrderWhatsApp(
    orderId: string,
    allowResend = false,
  ): Promise<WhatsAppMessagePackage> {
    return this.post<WhatsAppMessagePackage>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/whatsapp/prepare`,
      { allow_resend: allowResend },
    );
  }

  async preparePostPaymentWhatsApp(
    orderId: string,
    allowResend = false,
  ): Promise<WhatsAppFollowUpPackage> {
    return this.post<WhatsAppFollowUpPackage>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/whatsapp-followup/prepare`,
      { allow_resend: allowResend },
    );
  }

  async getWhatsAppReview(
    orderId: string,
    kind: 'whatsapp' | 'whatsapp-followup',
  ): Promise<WhatsAppReviewPayload> {
    return this.read<WhatsAppReviewPayload>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/${kind}/review`,
    );
  }

  async resolveWhatsAppReview(
    jobKey: string,
    resolution: WhatsAppReviewResolution,
    note: string | null,
  ): Promise<WhatsAppReviewResponse> {
    return this.post<WhatsAppReviewResponse>(
      `/api/v1/whatsapp-automation-jobs/${encodeURIComponent(jobKey)}/resolve`,
      { resolution, note },
    );
  }

  async markWhatsAppSent(messageId: string): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>(
      `/api/v1/whatsapp-messages/${encodeURIComponent(messageId)}/sent`,
      {},
    );
  }

  async markWhatsAppFollowUpSent(messageId: string): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>(
      `/api/v1/whatsapp-followup-messages/${encodeURIComponent(messageId)}/sent`,
      {},
    );
  }

  async prepareWhatsAppFollowUpWebDraft(messageId: string): Promise<WhatsAppWebDraftResponse> {
    return this.post<WhatsAppWebDraftResponse>(
      `/api/v1/whatsapp-followup-messages/${encodeURIComponent(messageId)}/web/prepare`,
      {},
    );
  }

  async validateWhatsAppWebSession(): Promise<WhatsAppWebDraftResponse> {
    return this.post<WhatsAppWebDraftResponse>('/api/v1/whatsapp-web/session/validate', {});
  }

  async prepareWhatsAppWebDraft(
    messageId: string,
    draftKind: 'confirmation' | 'payment' | 'album',
    autoSend = false,
  ): Promise<WhatsAppWebDraftResponse> {
    return this.post<WhatsAppWebDraftResponse>(
      `/api/v1/whatsapp-messages/${encodeURIComponent(messageId)}/web/prepare`,
      { draft_kind: draftKind, auto_send: autoSend },
    );
  }

  async getWhatsAppAttachment(url: string): Promise<Blob> {
    return firstValueFrom(this.http.get(url, { responseType: 'blob' }));
  }

  async createServiceOrder(payload: CreateServiceOrderPayload): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>('/api/v1/service-orders', payload);
  }

  async revalidateServiceOrder(orderId: string): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/validate`,
      {},
    );
  }

  async restartWorker(releaseSafeBackoffs = false): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>('/api/v1/worker/restart', {
      release_safe_backoffs: releaseSafeBackoffs,
    });
  }

  async openManualSession(
    orderId: string,
    mode: ManualSessionMode = 'appointment',
  ): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>('/api/v1/manual-session/open', {
      order_id: orderId,
      mode,
    });
  }

  async closeManualSession(sessionId: string): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>('/api/v1/manual-session/close', {
      session_id: sessionId,
    });
  }

  async splitServiceOrderPrograms(
    orderId: string,
    keepParentActive: boolean,
  ): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/split-programs`,
      {
        keep_parent_active: keepParentActive,
      },
    );
  }

  private async post<T>(url: string, payload: unknown): Promise<T> {
    return firstValueFrom(this.http.post<T>(url, payload));
  }

  private async put<T>(url: string, payload: unknown): Promise<T> {
    return firstValueFrom(this.http.put<T>(url, payload));
  }

  private async read<T>(url: string, scope?: RequestScope): Promise<T> {
    const request = this.http.get<T>(url);
    return scope ? scope.read(request) : firstValueFrom(request);
  }
}

export function apiErrorMessage(error: unknown): string {
  if (error instanceof HttpErrorResponse) {
    if (error.status === 0) {
      return 'No se pudo conectar con la API local.';
    }
    const message =
      typeof error.error?.message === 'string' ? error.error.message : 'Respuesta no esperada.';
    const fieldErrors = error.error?.field_errors;
    if (fieldErrors && typeof fieldErrors === 'object') {
      const labels: Record<string, string> = {
        document_number: 'Usuario o documento',
        document_type: 'Tipo de documento',
        password: 'Contraseña',
        contact_name: 'Persona de contacto',
        contact_source: 'Fuente',
        contact_whatsapp: 'WhatsApp',
        message_template: 'Mensaje',
        expected_revision: 'Revisión',
      };
      const details = Object.entries(fieldErrors)
        .map(([field, value]) => `${labels[field] ?? field}: ${String(value)}`)
        .join(' ');
      return `${error.status} ${details || message}`;
    }
    return `${error.status} ${message}`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'Error desconocido.';
}
