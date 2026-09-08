import { Injectable, inject } from '@angular/core';
import type {
  ProgramResolutionPayload,
  ProgramResolutionResponse,
} from '../../program-resolution/program-resolution';
import type { RequestScope } from '../../request-cancellation';
import type { ServicePackageCatalog } from '../../service-package.model';
import { ApiTransport } from '../shared/api-transport';
import type { ApiActionResponse } from '../shared/shared.contracts';
import type { ManualSessionMode } from '../states/states.contracts';
import type {
  CloseServiceOrderPayload,
  ContactUpdatePayload,
  CreateServiceOrderPayload,
  CredentialsUpdatePayload,
  ManualSession,
  ManualSessionsResponse,
  PriorityUpdatePayload,
  ReservationRestrictionsUpdatePayload,
  ServiceOrder,
  ServiceOrderDetail,
  ServiceOrdersResponse,
} from './orders.contracts';

@Injectable({ providedIn: 'root' })
export class OrdersApiClient {
  private readonly transport = inject(ApiTransport);

  async getServiceOrders(scope?: RequestScope): Promise<ServiceOrder[]> {
    const response = await this.transport.read<ServiceOrdersResponse>(
      '/api/v1/service-orders?projection=dashboard',
      scope,
    );
    return response.service_orders;
  }

  async getServicePackages(scope?: RequestScope): Promise<ServicePackageCatalog> {
    return this.transport.read<ServicePackageCatalog>('/api/v1/service-packages', scope);
  }

  async getServiceOrder(orderId: string): Promise<ServiceOrderDetail> {
    return this.transport.read<ServiceOrderDetail>(`/api/v1/service-orders/${encodeURIComponent(orderId)}`);
  }

  async getManualSessions(scope?: RequestScope): Promise<ManualSession[]> {
    const response = await this.transport.read<ManualSessionsResponse>('/api/v1/manual-sessions', scope);
    return response.manual_sessions;
  }

  async updateServiceOrderContact(
    orderId: string,
    payload: ContactUpdatePayload,
  ): Promise<ApiActionResponse> {
    return this.transport.post<ApiActionResponse>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/contact`,
      payload,
    );
  }

  async updateServiceOrderCredentials(
    orderId: string,
    payload: CredentialsUpdatePayload,
  ): Promise<ApiActionResponse> {
    return this.transport.post<ApiActionResponse>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/credentials`,
      payload,
    );
  }

  async updateServiceOrderPriority(
    orderId: string,
    payload: PriorityUpdatePayload,
  ): Promise<ApiActionResponse> {
    return this.transport.post<ApiActionResponse>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/priority`,
      payload,
    );
  }

  async updateServiceOrderRestrictions(
    orderId: string,
    payload: ReservationRestrictionsUpdatePayload,
  ): Promise<ApiActionResponse> {
    return this.transport.post<ApiActionResponse>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/restrictions`,
      payload,
    );
  }

  async runServiceOrderAction(
    orderId: string,
    action: 'pause' | 'activate' | 'no-charge' | 'done',
  ): Promise<ApiActionResponse> {
    return this.transport.post<ApiActionResponse>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/${encodeURIComponent(action)}`,
      {},
    );
  }

  async closeServiceOrder(
    orderId: string,
    payload: CloseServiceOrderPayload,
  ): Promise<ApiActionResponse> {
    return this.transport.post<ApiActionResponse>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/close`,
      payload,
    );
  }

  async createServiceOrder(payload: CreateServiceOrderPayload): Promise<ApiActionResponse> {
    return this.transport.post<ApiActionResponse>('/api/v1/service-orders', payload);
  }

  async revalidateServiceOrder(orderId: string): Promise<ApiActionResponse> {
    return this.transport.post<ApiActionResponse>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/validate`,
      {},
    );
  }

  async resolveServiceOrderPrograms(
    orderId: string,
    payload: ProgramResolutionPayload,
  ): Promise<ProgramResolutionResponse> {
    return this.transport.post<ProgramResolutionResponse>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/program-resolution`,
      payload,
    );
  }

  async openManualSession(
    orderId: string,
    mode: ManualSessionMode = 'appointment',
  ): Promise<ApiActionResponse> {
    return this.transport.post<ApiActionResponse>('/api/v1/manual-session/open', {
      order_id: orderId,
      mode,
    });
  }

  async closeManualSession(sessionId: string): Promise<ApiActionResponse> {
    return this.transport.post<ApiActionResponse>('/api/v1/manual-session/close', {
      session_id: sessionId,
    });
  }
}
