import type {
  ProgramResolutionPreflightDetails,
} from '../../program-resolution/program-resolution';
import type { ExcludedDateRange } from '../../reservation-rules.model';
import type { ServicePackageKey } from '../../service-package.model';
import type { WhatsAppActionState } from '../messages/messages.contracts';
import type {
  DocumentType,
  ManualSessionMode,
  PreflightStatus,
  ServiceType,
} from '../states/states.contracts';

export interface ServiceOrder {
  order_id: string;
  applicant_id: string;
  applicant_name: string | null;
  document_number_masked: string;
  document_type: DocumentType;
  contact_name: string | null;
  contact_whatsapp_masked: string | null;
  contact_whatsapp_username_masked: string | null;
  contact_source: string | null;
  priority: number;
  charge_required: boolean;
  service_type: ServiceType;
  reservation_price: string;
  service_package: ServicePackageKey;
  official_fee_amount: string;
  initial_payment_amount: string;
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
  whatsapp_followup_action_state: WhatsAppActionState;
  parent_order_id: string | null;
  program_expediente: string | null;
  program_plate: string | null;
  closure_reason: string | null;
  closure_note: string | null;
  closed_at: string | null;
  minimum_reservation_date: string | null;
  maximum_reservation_date: string | null;
  allowed_weekdays: number[] | null;
  excluded_date_ranges: ExcludedDateRange[];
  preflight_status: PreflightStatus;
  preflight_message: string | null;
  preflight_error_type: string | null;
  registration_notice_type: string | null;
  registration_notice_status: WhatsAppActionState | null;
  registration_notice_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface ServiceOrderDetail extends ServiceOrder {
  document_number: string;
  contact_whatsapp: string | null;
  contact_whatsapp_username: string | null;
  preflight_details: ProgramResolutionPreflightDetails | Record<string, unknown> | null;
}

export interface ServiceOrdersResponse {
  service_orders: ServiceOrder[];
}

export interface ManualSessionsResponse {
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

export interface CloseServiceOrderPayload {
  closure_reason: string;
  closure_note?: string | null;
}

export interface CreateServiceOrderPayload {
  document_number: string;
  document_type: DocumentType;
  password: string;
  contact_name: string;
  contact_source: string;
  priority?: number;
  contact_whatsapp?: string | null;
  contact_whatsapp_username?: string | null;
  applicant_name?: string | null;
  charge_required?: boolean;
  service_type?: ServiceType;
  service_package?: ServicePackageKey;
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
  document_type: DocumentType;
  password: string;
}
