import { Injectable, inject } from '@angular/core';
import type { RequestScope } from '../../request-cancellation';
import { ApiTransport } from '../shared/api-transport';
import type { ApiActionResponse } from '../shared/shared.contracts';
import type {
  HealthPayload,
  OperatorInboxPayload,
  OpportunityBurstsResponse,
  OpportunityControl,
  OpportunityControlActionPayload,
  RunDetail,
  RunSummary,
  RunsResponse,
  WorkerCommand,
  WorkerCommandsResponse,
  WorkerStatus,
} from './operations.contracts';

@Injectable({ providedIn: 'root' })
export class OperationsApiClient {
  private readonly transport = inject(ApiTransport);

  async getHealth(scope?: RequestScope): Promise<HealthPayload> {
    return this.transport.read<HealthPayload>('/health', scope);
  }

  async getWorker(scope?: RequestScope): Promise<WorkerStatus> {
    return this.transport.read<WorkerStatus>('/api/v1/worker', scope);
  }

  async getOpportunityControl(scope?: RequestScope): Promise<OpportunityControl> {
    return this.transport.read<OpportunityControl>('/api/v1/runtime-controls/opportunity', scope);
  }

  async updateOpportunityControl(
    payload: OpportunityControlActionPayload,
  ): Promise<OpportunityControl> {
    return this.transport.post<OpportunityControl>('/api/v1/runtime-controls/opportunity', payload);
  }

  async getOpportunityBursts(scope?: RequestScope): Promise<OpportunityBurstsResponse> {
    return this.transport.read<OpportunityBurstsResponse>('/api/v1/opportunity-bursts', scope);
  }

  async getOperatorInbox(scope?: RequestScope): Promise<OperatorInboxPayload> {
    return this.transport.read<OperatorInboxPayload>('/api/v1/operator-inbox', scope);
  }

  async getRuns(scope?: RequestScope): Promise<RunSummary[]> {
    const response = await this.transport.read<RunsResponse>('/api/v1/runs?limit=50', scope);
    return response.runs;
  }

  async getRun(runId: string, scope?: RequestScope): Promise<RunDetail> {
    return this.transport.read<RunDetail>(`/api/v1/runs/${encodeURIComponent(runId)}`, scope);
  }

  async getWorkerCommands(scope?: RequestScope): Promise<WorkerCommand[]> {
    const response = await this.transport.read<WorkerCommandsResponse>(
      '/api/v1/worker/commands?limit=20',
      scope,
    );
    return response.commands;
  }

  async restartWorker(releaseSafeBackoffs = false): Promise<ApiActionResponse> {
    return this.transport.post<ApiActionResponse>('/api/v1/worker/restart', {
      release_safe_backoffs: releaseSafeBackoffs,
    });
  }

  async pauseWorker(): Promise<ApiActionResponse> {
    return this.transport.post<ApiActionResponse>('/api/v1/worker/pause', {});
  }

  async resumeWorker(): Promise<ApiActionResponse> {
    return this.transport.post<ApiActionResponse>('/api/v1/worker/resume', {});
  }
}
