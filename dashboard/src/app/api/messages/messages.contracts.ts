import type { ApiActionResponse } from '../shared/shared.contracts';
import type { WhatsAppPackageStatus } from '../states/states.contracts';

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

export interface WhatsAppMessagePackage {
  message_id: string;
  order_id: string | null;
  test_mode: boolean;
  status: WhatsAppPackageStatus;
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
  confirmation_template_key: string | null;
  confirmation_template_revision: number | null;
  payment_template_key: string | null;
  payment_template_revision: number | null;
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
  status: WhatsAppPackageStatus;
  recipient_phone: string | null;
  recipient_phone_masked: string | null;
  recipient_username: string | null;
  recipient_label: string;
  steps: WhatsAppFollowUpStep[];
  combined_text: string;
  template_key: string | null;
  template_revision: number | null;
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
  template_trace: Array<{
    template_key: string;
    template_revision: number;
  }>;
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
