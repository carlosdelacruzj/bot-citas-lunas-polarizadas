import { Injectable, inject } from '@angular/core';
import type { RequestScope } from '../../request-cancellation';
import { ApiTransport } from '../shared/api-transport';
import type { ApiActionResponse } from '../shared/shared.contracts';
import type {
  FinanceCategory,
  FinanceDataQualitySummary,
  FinanceEntry,
  FinanceEntryPayload,
  FinanceMonthClosure,
  FinanceMonthClosurePayload,
  FinanceSummary,
  MonthlySummaryV2,
  PaymentPaidPayload,
  PaymentResolutionType,
} from './finance.contracts';

@Injectable({ providedIn: 'root' })
export class FinanceApiClient {
  private readonly transport = inject(ApiTransport);

  async getMonthlySummaryV2(month: string, scope?: RequestScope): Promise<MonthlySummaryV2> {
    return this.transport.read<MonthlySummaryV2>(
      `/api/v2/monthly-summary?month=${encodeURIComponent(month)}`,
      scope,
    );
  }

  async getFinanceCategories(scope?: RequestScope): Promise<FinanceCategory[]> {
    const response = await this.transport.read<{ categories: FinanceCategory[] }>(
      '/api/v1/finance/categories',
      scope,
    );
    return response.categories;
  }

  async getFinanceEntries(month: string, scope?: RequestScope): Promise<FinanceEntry[]> {
    const response = await this.transport.read<{ entries: FinanceEntry[] }>(
      `/api/v1/finance/entries?month=${encodeURIComponent(month)}&include_voided=1`,
      scope,
    );
    return response.entries;
  }

  async getFinanceSummary(month: string, scope?: RequestScope): Promise<FinanceSummary> {
    return this.transport.read<FinanceSummary>(
      `/api/v1/finance/summary?month=${encodeURIComponent(month)}`,
      scope,
    );
  }

  async getFinanceDataQuality(
    month: string,
    scope?: RequestScope,
  ): Promise<FinanceDataQualitySummary> {
    return this.transport.read<FinanceDataQualitySummary>(
      `/api/v1/finance/data-quality?month=${encodeURIComponent(month)}`,
      scope,
    );
  }

  async getFinanceMonthClosure(
    month: string,
    scope?: RequestScope,
  ): Promise<FinanceMonthClosure> {
    return this.transport.read<FinanceMonthClosure>(
      `/api/v1/finance/month-closure?month=${encodeURIComponent(month)}`,
      scope,
    );
  }

  async saveFinanceMonthClosure(
    payload: FinanceMonthClosurePayload,
  ): Promise<FinanceMonthClosure & { status: string }> {
    return this.transport.post<FinanceMonthClosure & { status: string }>(
      '/api/v1/finance/month-closure',
      payload,
    );
  }

  async reconcileFinancePaymentAmount(
    paymentId: string,
    payload: { resolution_type: PaymentResolutionType; reason: string },
  ): Promise<ApiActionResponse> {
    return this.transport.post<ApiActionResponse>(
      `/api/v1/finance/payments/${encodeURIComponent(paymentId)}/reconcile-amount`,
      payload,
    );
  }

  async createFinanceEntry(payload: FinanceEntryPayload): Promise<ApiActionResponse> {
    return this.transport.post<ApiActionResponse>('/api/v1/finance/entries', payload);
  }

  async updateFinanceEntry(
    entryId: string,
    payload: FinanceEntryPayload,
  ): Promise<ApiActionResponse> {
    return this.transport.post<ApiActionResponse>(
      `/api/v1/finance/entries/${encodeURIComponent(entryId)}/edit`,
      payload,
    );
  }

  async voidFinanceEntry(entryId: string, reason: string): Promise<ApiActionResponse> {
    return this.transport.post<ApiActionResponse>(
      `/api/v1/finance/entries/${encodeURIComponent(entryId)}/void`,
      { reason },
    );
  }

  async markPaymentPaid(orderId: string, payload: PaymentPaidPayload): Promise<ApiActionResponse> {
    return this.transport.post<ApiActionResponse>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/payment/paid`,
      payload,
    );
  }

  async recordPartialPayment(
    orderId: string,
    payload: PaymentPaidPayload,
  ): Promise<ApiActionResponse> {
    return this.transport.post<ApiActionResponse>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/payment/partial`,
      payload,
    );
  }
}
