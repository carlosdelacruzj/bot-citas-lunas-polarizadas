export interface HealthPayload {
  status: string;
  message: string;
  worker_running: boolean;
  reason: string;
  captcha_shadow_enabled: boolean;
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
  max_sessions?: number;
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

export type OperatorInboxTaskKind =
  | 'preflight'
  | 'paused'
  | 'contact'
  | 'whatsapp'
  | 'payment'
  | 'followup'
  | 'review';

export type OperatorInboxTaskAction =
  | 'correct_credentials'
  | 'revalidate'
  | 'view_order'
  | 'edit_contact'
  | 'prepare_whatsapp'
  | 'register_payment'
  | 'review_whatsapp'
  | 'review_post_payment_whatsapp';

export interface OperatorInboxTask {
  key: string;
  kind: OperatorInboxTaskKind;
  order_id: string;
  applicant_name: string | null;
  document_number_masked: string;
  title: string;
  description: string;
  label: string;
  action: OperatorInboxTaskAction;
  action_label: string;
  tone: 'bad' | 'warn' | 'neutral';
  state: string;
  updated_at: string;
}

export interface OperatorInboxPayload {
  generated_at: string;
  summary: {
    total: number;
    access: number;
    paused: number;
    contact: number;
    whatsapp: number;
    payment: number;
    postpayment: number;
    messages: number;
  };
  items: OperatorInboxTask[];
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

export interface RunsResponse {
  runs: RunSummary[];
}

export interface WorkerCommandsResponse {
  commands: WorkerCommand[];
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
