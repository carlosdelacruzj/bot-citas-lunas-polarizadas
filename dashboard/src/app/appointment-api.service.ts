import { HttpClient, HttpErrorResponse, HttpHeaders } from '@angular/common/http';
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

export interface CreateServiceOrderPayload {
  document_number: string;
  password: string;
  priority?: number;
  contact_whatsapp?: string | null;
  contact_name?: string | null;
  contact_source?: string | null;
  applicant_name?: string | null;
  charge_required?: boolean;
  minimum_reservation_hour?: number | null;
  minimum_reservation_date?: string | null;
  allowed_weekdays?: number[] | null;
}

@Injectable({ providedIn: 'root' })
export class AppointmentApiService {
  private readonly http = inject(HttpClient);

  async getHealth(): Promise<HealthPayload> {
    return firstValueFrom(this.http.get<HealthPayload>('/health'));
  }

  async getWorker(token: string): Promise<WorkerStatus> {
    return firstValueFrom(this.http.get<WorkerStatus>('/api/v1/worker', this.authOptions(token)));
  }

  async getServiceOrders(token: string): Promise<ServiceOrder[]> {
    const response = await firstValueFrom(
      this.http.get<ServiceOrdersResponse>('/api/v1/service-orders', this.authOptions(token)),
    );
    return response.service_orders;
  }

  async getRuns(token: string): Promise<RunSummary[]> {
    const response = await firstValueFrom(
      this.http.get<RunsResponse>('/api/v1/runs?limit=50', this.authOptions(token)),
    );
    return response.runs;
  }

  async updateServiceOrderContact(
    token: string,
    orderId: string,
    payload: ContactUpdatePayload,
  ): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>(
      token,
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/contact`,
      payload,
    );
  }

  async runServiceOrderAction(
    token: string,
    orderId: string,
    action: 'pause' | 'activate' | 'no-charge' | 'done',
  ): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>(
      token,
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/${action}`,
      {},
    );
  }

  async markPaymentPaid(
    token: string,
    orderId: string,
    payload: PaymentPaidPayload,
  ): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>(
      token,
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/payment/paid`,
      payload,
    );
  }

  async createServiceOrder(
    token: string,
    payload: CreateServiceOrderPayload,
  ): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>(token, '/api/v1/service-orders', payload);
  }

  async restartWorker(token: string): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>(token, '/api/v1/worker/restart', {});
  }

  async openManualSession(token: string, orderId: string): Promise<ApiActionResponse> {
    return this.post<ApiActionResponse>(token, '/api/v1/manual-session/open', {
      order_id: orderId,
    });
  }

  private authOptions(token: string): { headers: HttpHeaders } {
    return {
      headers: new HttpHeaders({
        Authorization: `Bearer ${token}`,
      }),
    };
  }

  private async post<T>(token: string, url: string, payload: unknown): Promise<T> {
    return firstValueFrom(this.http.post<T>(url, payload, this.authOptions(token)));
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
