import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';

export interface HealthPayload {
  status: string;
  message: string;
  worker_running: boolean;
  reason: string;
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

export interface ServiceOrder {
  order_id: string;
  applicant_id: string;
  applicant_name: string | null;
  document_number_masked: string;
  contact_name: string | null;
  contact_whatsapp_masked: string | null;
  contact_source: string | null;
  priority: number;
  charge_required: boolean;
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
  created_at: string;
  updated_at: string;
}

export interface ServiceOrderDetail extends ServiceOrder {
  document_number: string;
  contact_whatsapp: string | null;
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
  status: string;
  started_at: string;
  updated_at: string;
  close_requested: boolean;
}

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
  by_category: Array<{
    category_code: string;
    category_name: string;
    recognized_cost: number;
  }>;
}

export interface ApiActionResponse {
  status: string;
  message?: string;
  command_id?: string;
  command?: string;
  session_id?: string;
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
  contact_name?: string | null;
  contact_source?: string | null;
}

export interface PriorityUpdatePayload {
  priority: number;
}

export interface ReservationRestrictionsUpdatePayload {
  minimum_reservation_hour: number | null;
  minimum_reservation_date: string | null;
  maximum_reservation_date: string | null;
  allowed_weekdays: number[] | null;
}

export interface PaymentPaidPayload {
  amount_paid: string;
  amount_agreed?: string | null;
}

export interface WhatsAppMessagePackage {
  message_id: string;
  order_id: string | null;
  test_mode: boolean;
  status: 'prepared' | 'sent';
  recipient_phone: string;
  recipient_phone_masked: string | null;
  greeting: string;
  evidence_caption: string;
  payment_message: string;
  whatsapp_url: string;
  attachment_url: string;
  payment_attachment_url: string;
  prepared_at: string;
  sent_at: string | null;
}

export interface WhatsAppWebDraftResponse {
  status: 'login_required' | 'draft_ready' | 'web_unavailable';
  message: string;
  message_id: string | null;
  manual_send_required: true;
  sent: false;
  draft_mode?: 'caption' | 'queued_text' | 'album';
}

export interface CloseServiceOrderPayload {
  closure_reason: string;
  closure_note?: string | null;
}

export interface CreateServiceOrderPayload {
  document_number: string;
  password: string;
  contact_name: string;
  contact_source: string;
  priority?: number;
  contact_whatsapp?: string | null;
  applicant_name?: string | null;
  charge_required?: boolean;
  minimum_reservation_hour?: number | null;
  minimum_reservation_date?: string | null;
  maximum_reservation_date?: string | null;
  allowed_weekdays?: number[] | null;
  parent_order_id?: string | null;
  program_expediente?: string | null;
  program_plate?: string | null;
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

  async getHealth(): Promise<HealthPayload> {
    return firstValueFrom(this.http.get<HealthPayload>('/health'));
  }

  async getWorker(): Promise<WorkerStatus> {
    return firstValueFrom(this.http.get<WorkerStatus>('/api/v1/worker'));
  }

  async getServiceOrders(): Promise<ServiceOrder[]> {
    const response = await firstValueFrom(this.http.get<ServiceOrdersResponse>('/api/v1/service-orders'));
    return response.service_orders;
  }

  async getServiceOrder(orderId: string): Promise<ServiceOrderDetail> {
    return firstValueFrom(
      this.http.get<ServiceOrderDetail>(
        `/api/v1/service-orders/${encodeURIComponent(orderId)}`,
      ),
    );
  }

  async getRuns(): Promise<RunSummary[]> {
    const response = await firstValueFrom(this.http.get<RunsResponse>('/api/v1/runs?limit=50'));
    return response.runs;
  }

  async getRun(runId: string): Promise<RunDetail> {
    return firstValueFrom(
      this.http.get<RunDetail>(`/api/v1/runs/${encodeURIComponent(runId)}`),
    );
  }

  async getWorkerCommands(): Promise<WorkerCommand[]> {
    const response = await firstValueFrom(
      this.http.get<WorkerCommandsResponse>('/api/v1/worker/commands?limit=20'),
    );
    return response.commands;
  }

  async getManualSessions(): Promise<ManualSession[]> {
    const response = await firstValueFrom(
      this.http.get<ManualSessionsResponse>('/api/v1/manual-sessions'),
    );
    return response.manual_sessions;
  }

  async getMonthlySummary(month: string): Promise<MonthlySummary> {
    return firstValueFrom(
      this.http.get<MonthlySummary>(
        `/api/v1/monthly-summary?month=${encodeURIComponent(month)}`,
      ),
    );
  }

  async getFinanceCategories(): Promise<FinanceCategory[]> {
    const response = await firstValueFrom(
      this.http.get<{ categories: FinanceCategory[] }>('/api/v1/finance/categories'),
    );
    return response.categories;
  }

  async getFinanceEntries(month: string): Promise<FinanceEntry[]> {
    const response = await firstValueFrom(
      this.http.get<{ entries: FinanceEntry[] }>(
        `/api/v1/finance/entries?month=${encodeURIComponent(month)}&include_voided=1`,
      ),
    );
    return response.entries;
  }

  async getFinanceSummary(month: string): Promise<FinanceSummary> {
    return firstValueFrom(
      this.http.get<FinanceSummary>(
        `/api/v1/finance/summary?month=${encodeURIComponent(month)}`,
      ),
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

  async markPaymentPaid(
    orderId: string,
    payload: PaymentPaidPayload,
  ): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/payment/paid`,
      payload,
    );
  }

  async prepareWhatsAppTest(recipientPhone: string): Promise<WhatsAppMessagePackage> {
    return this.post<WhatsAppMessagePackage>('/api/v1/whatsapp-messages/test/prepare', {
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

  async markWhatsAppSent(messageId: string): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>(
      `/api/v1/whatsapp-messages/${encodeURIComponent(messageId)}/sent`,
      {},
    );
  }

  async prepareWhatsAppWebDraft(
    messageId: string,
    draftKind: 'confirmation' | 'payment' | 'album',
  ): Promise<WhatsAppWebDraftResponse> {
    return this.post<WhatsAppWebDraftResponse>(
      `/api/v1/whatsapp-messages/${encodeURIComponent(messageId)}/web/prepare`,
      { draft_kind: draftKind },
    );
  }

  async getWhatsAppAttachment(url: string): Promise<Blob> {
    return firstValueFrom(this.http.get(url, { responseType: 'blob' }));
  }

  async createServiceOrder(payload: CreateServiceOrderPayload): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>('/api/v1/service-orders', payload);
  }

  async restartWorker(): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>('/api/v1/worker/restart', {});
  }

  async openManualSession(orderId: string): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>('/api/v1/manual-session/open', {
      order_id: orderId,
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
        password: 'Contraseña',
        contact_name: 'Persona de contacto',
        contact_source: 'Fuente',
        contact_whatsapp: 'WhatsApp',
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
