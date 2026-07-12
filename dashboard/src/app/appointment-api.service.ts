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
  document_number: string;
  document_number_masked: string;
  contact_name: string | null;
  contact_whatsapp: string | null;
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
  parent_order_id: string | null;
  program_expediente: string | null;
  program_plate: string | null;
  closure_reason: string | null;
  closure_note: string | null;
  closed_at: string | null;
  minimum_reservation_hour: number | null;
  minimum_reservation_date: string | null;
  allowed_weekdays: number[] | null;
  created_at: string;
  updated_at: string;
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
}

export interface ContactUpdatePayload {
  contact_whatsapp?: string | null;
  contact_name?: string | null;
  contact_source?: string | null;
}

export interface PaymentPaidPayload {
  amount_paid: string;
  amount_agreed?: string | null;
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

  async getRuns(): Promise<RunSummary[]> {
    const response = await firstValueFrom(this.http.get<RunsResponse>('/api/v1/runs?limit=50'));
    return response.runs;
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

  async updateServiceOrderContact(
    orderId: string,
    payload: ContactUpdatePayload,
  ): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/contact`,
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
    return `${error.status} ${message}`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'Error desconocido.';
}
