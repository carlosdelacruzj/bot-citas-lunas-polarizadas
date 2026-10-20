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
