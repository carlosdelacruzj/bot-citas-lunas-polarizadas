import { Injectable, inject } from '@angular/core';
import type { RequestScope } from '../../request-cancellation';
import { ApiTransport } from '../shared/api-transport';
import type {
  CaptchaAuthorityControl,
  CaptchaEventsPage,
  CaptchaHumanLabelResponse,
  CaptchaQuality,
  CaptchaQualityCaseType,
  CaptchaQualityCasesPage,
  CaptchaSamplingControl,
  CaptchaSummary,
} from './captchas.contracts';

@Injectable({ providedIn: 'root' })
export class CaptchasApiClient {
  private readonly transport = inject(ApiTransport);

  async getCaptchaSamplingControl(scope?: RequestScope): Promise<CaptchaSamplingControl> {
    return this.transport.read<CaptchaSamplingControl>(
      '/api/v1/runtime-controls/captcha-sampling',
      scope,
    );
  }

  async updateCaptchaSamplingControl(
    enabled: boolean,
    sampleLimit: number,
  ): Promise<CaptchaSamplingControl> {
    return this.transport.post<CaptchaSamplingControl>('/api/v1/runtime-controls/captcha-sampling', {
      enabled,
      sample_limit: sampleLimit,
    });
  }

  async getCaptchaAuthorityControl(scope?: RequestScope): Promise<CaptchaAuthorityControl> {
    return this.transport.read<CaptchaAuthorityControl>(
      '/api/v1/runtime-controls/captcha-authority',
      scope,
    );
  }

  async updateCaptchaAuthorityControl(
    mode: CaptchaAuthorityControl['mode'],
    resetCircuit = false,
  ): Promise<CaptchaAuthorityControl> {
    return this.transport.post<CaptchaAuthorityControl>('/api/v1/runtime-controls/captcha-authority', {
      mode,
      reset_circuit: resetCircuit,
    });
  }

  async getCaptchaSummary(scope?: RequestScope): Promise<CaptchaSummary> {
    return this.transport.read<CaptchaSummary>('/api/v1/captcha-shadow/summary', scope);
  }

  async getCaptchaEvents(
    page: number,
    pageSize: number,
    query: string,
    agreement: string,
    portalStatus: string,
    source: string,
    reviewStatus: string,
    sort: string,
    reviewScope: 'all' | 'targeted',
    scope?: RequestScope,
  ): Promise<CaptchaEventsPage> {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
      q: query,
      agreement,
      portal_status: portalStatus,
      source,
      review_status: reviewStatus,
      review_scope: reviewScope,
      sort,
    });
    return this.transport.read<CaptchaEventsPage>(
      `/api/v1/captcha-shadow/events?${params.toString()}`,
      scope,
    );
  }

  async saveCaptchaHumanLabel(
    eventId: string,
    imageSha256: string,
    answer: string,
  ): Promise<CaptchaHumanLabelResponse> {
    return this.transport.post<CaptchaHumanLabelResponse>(
      `/api/v1/captcha-shadow/events/${encodeURIComponent(eventId)}/human-label`,
      { answer, expected_image_sha256: imageSha256 },
    );
  }

  async getCaptchaQuality(scope?: RequestScope): Promise<CaptchaQuality> {
    return this.transport.read<CaptchaQuality>('/api/v1/captcha-shadow/quality', scope);
  }

  async getCaptchaQualityCases(
    caseType: CaptchaQualityCaseType,
    page: number,
    pageSize: number,
    scope?: RequestScope,
  ): Promise<CaptchaQualityCasesPage> {
    const params = new URLSearchParams({
      type: caseType,
      page: String(page),
      page_size: String(pageSize),
    });
    return this.transport.read<CaptchaQualityCasesPage>(
      `/api/v1/captcha-shadow/quality/cases?${params.toString()}`,
      scope,
    );
  }

  async downloadCaptchaDataset(scope?: RequestScope): Promise<Blob> {
    return this.transport.blob('/api/v1/captcha-shadow/dataset/export', scope);
  }
}
