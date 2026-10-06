import type { FinanceClosureStatus } from '../states/states.contracts';

export interface MetricRatio {
  value: number;
  numerator: number;
  denominator: number;
}

export interface MetricPeriod {
  start: string;
  end_exclusive: string;
  coverage_end_exclusive: string;
  is_closed: boolean;
}

export interface ReceiptDateQuality {
  status: 'no_receipts' | 'exact' | 'inferred' | 'mixed';
  comparison_conclusive: boolean;
  exact_since: string | null;
  inferred_receipt_count: number;
  inferred_payment_count: number;
  inferred_amount: number;
  exact_receipt_count: number;
  exact_amount: number;
  semantics: string;
}

export interface MonthlyEventMetrics {
  orders_created: number;
  confirmed_reservation_events: number;
  orders_reserved: number;
  payments_received: number;
  distinct_payments: number;
  orders_with_receipts: number;
  payments_received_semantics: string;
  revenue_collected: number;
  receipt_date_quality: ReceiptDateQuality;
  average_ticket: MetricRatio;
  daily_revenue: Array<{ date: string; amount: number; payments: number }>;
}

export interface MonthlyPeriodMetrics extends MonthlyEventMetrics {
  period: MetricPeriod;
}

export interface MonthlySummaryV2 {
  contract_version: '2.0';
  month: string;
  as_of: string;
  period_metrics: MonthlyPeriodMetrics;
  cohort_metrics: {
    cohort: {
      created_from: string;
      created_to_exclusive: string;
      outcomes_observed_as_of: string;
    };
    orders_created: number;
    orders_ever_reserved: number;
    orders_ever_paid: number;
    revenue_ever_collected: number;
    reservation_conversion_rate: MetricRatio;
    payment_conversion_rate: MetricRatio;
    funnel: {
      validated: {
        orders_created: number;
        orders_ever_reserved: number;
        orders_ever_paid: number;
      };
      legacy_not_required: {
        orders_created: number;
        orders_ever_reserved: number;
        orders_ever_paid: number;
      };
      note: string;
    };
    sources: Array<{
      source: string;
      orders_created: number;
      order_creation_source_orders: number;
      historical_backfill_source_orders: number;
      orders_ever_reserved: number;
      orders_ever_paid: number;
      revenue_ever_collected: number;
    }>;
    source_semantics: {
      preferred: string;
      historical_backfill: string;
      historical_fallback: string;
      frozen_storage_available: boolean;
    };
  };
  current_attention_snapshot: {
    as_of: string;
    active_orders: number;
    missing_contact_count: number;
    valid_contact_rule: string;
    pending_payments: number;
    pending_amount: number;
    pending_payment_items: Array<{
      order_id: string;
      name: string;
      source: string;
      pending_amount: number;
      reservation_date: string | null;
      reservation_hour: string | null;
    }>;
    aged_active_orders: Array<{
      order_id: string;
      name: string;
      status: string;
      created_date: string;
    }>;
    list_limit: number;
  };
  comparisons: {
    same_day_window: {
      elapsed_days: number;
      selected: { period: MetricPeriod; metrics: MonthlyEventMetrics };
      previous: { period: MetricPeriod; metrics: MonthlyEventMetrics };
    } | null;
    closed_months: {
      selected: { period: MetricPeriod; metrics: MonthlyEventMetrics };
      previous: { period: MetricPeriod; metrics: MonthlyEventMetrics };
    };
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
  payments_received: number;
  distinct_payments: number;
  orders_with_receipts: number;
  payments_received_semantics: string;
  daily_revenue: Array<{ date: string; amount: number; payments: number }>;
  revenue_collected: number;
  recognized_costs: number;
  operating_margin_before_unregistered_costs: number;
  net_cash_outflow: number;
  prepaid_topups: number;
  prepaid_consumption: number;
  unconverted_entries: number;
  active_entries: number;
  conversion_complete: boolean;
  receipt_date_quality: ReceiptDateQuality;
  cost_capture_complete?: null;
  completeness_semantics?: string;
  by_category: Array<{
    category_code: string;
    category_name: string;
    recognized_cost: number;
  }>;
}

export type PaymentResolutionType = 'discount' | 'waiver' | 'correction';

export interface FinanceDataQualitySummary {
  month: string;
  receipt_date_quality: ReceiptDateQuality;
  data_quality: Record<FinanceDataQuality, {
    entry_count: number;
    amount_pen: number;
    unconverted_count: number;
  }>;
  unconverted_entries: Array<{
    entry_id: string;
    occurred_on: string;
    entry_kind: FinanceEntryKind;
    category_code: string;
    description: string;
    amount_original: number;
    currency: string;
    data_quality: FinanceDataQuality;
  }>;
  paid_amount_mismatches: Array<{
    payment_id: string;
    order_id: string;
    amount_agreed: number | null;
    amount_paid: number | null;
    difference: number | null;
    currency: string;
    paid_at: string | null;
    reconciliation: {
      resolution_type: PaymentResolutionType;
      reason: string;
      reconciled_by: string;
      reconciled_at: string;
    } | null;
  }>;
  unreconciled_paid_amount_mismatch_count: number;
}

export interface FinanceMonthClosure {
  month: string;
  closure: {
    opening_prepaid_balance: number | null;
    closing_prepaid_balance: number | null;
    status: FinanceClosureStatus;
    reconciled_at: string | null;
    reconciled_by: string | null;
    notes: string | null;
    created_at: string;
    updated_at: string;
  } | null;
  movements: {
    prepaid_topups: number;
    prepaid_consumption: number;
    refunds: number;
    prepaid_refunds: number;
    pending_entries: number;
    unconverted_entries: number;
    estimated_entries: number;
  };
  expected_closing_prepaid_balance: number | null;
  balance_difference: number | null;
}

export interface FinanceMonthClosurePayload {
  month: string;
  opening_prepaid_balance: string | null;
  closing_prepaid_balance: string | null;
  status: FinanceClosureStatus;
  notes: string | null;
}

export interface PaymentPaidPayload {
  amount_paid: string;
  amount_agreed?: string | null;
  expected_payment_status?: string | null;
  expected_amount_agreed?: string | null;
  expected_amount_paid?: string | null;
}
