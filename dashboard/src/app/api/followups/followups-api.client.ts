import { Injectable, inject } from '@angular/core';
import type { RequestScope } from '../../request-cancellation';
import { ApiTransport } from '../shared/api-transport';
import type { ApiActionResponse } from '../shared/shared.contracts';
import type {
  AppointmentReminderStatus,
  PostAppointmentPayload,
  PostAppointmentQuery,
} from './followups.contracts';

@Injectable({ providedIn: 'root' })
export class FollowupsApiClient {
  private readonly transport = inject(ApiTransport);

  async getAppointmentReminders(scope?: RequestScope): Promise<AppointmentReminderStatus> {
    return this.transport.read<AppointmentReminderStatus>('/api/v1/appointment-reminders', scope);
  }

  async updateAppointmentReminders(payload: {
    mode: AppointmentReminderStatus['control']['mode'];
    lead_days: AppointmentReminderStatus['control']['lead_days'];
    expected_revision: number;
  }): Promise<AppointmentReminderStatus> {
    return this.transport.post<AppointmentReminderStatus>('/api/v1/appointment-reminders', payload);
  }

  async getPostAppointmentFollowups(
    query: PostAppointmentQuery,
    scope?: RequestScope,
  ): Promise<PostAppointmentPayload> {
    const params = new URLSearchParams({
      filter: query.filter,
      search: query.search,
      sort: query.sort,
      direction: query.direction,
      limit: String(query.limit),
      offset: String(query.offset),
      include_upcoming: String(query.include_upcoming),
    });
    return this.transport.read<PostAppointmentPayload>(
      `/api/v1/post-appointment-followups?${params.toString()}`,
      scope,
    );
  }

  async reviewPostAppointment(orderId: string): Promise<ApiActionResponse> {
    return this.transport.post<ApiActionResponse>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/post-appointment/review`,
      {},
    );
  }
}
