import { Injectable, Injector, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import {
  AppointmentApiService,
  FinanceCategory,
  FinanceDataQuality,
  FinanceDataQualitySummary,
  FinanceEntry,
  FinanceEntryKind,
  FinanceEntryPayload,
  FinanceMonthClosure,
  FinanceSummary,
  MetricPeriod,
  MonthlySummaryV2,
  PaymentResolutionType,
  ServiceOrder,
} from '../../appointment-api.service';
import { INITIAL_DATE, INITIAL_MONTH } from '../../dashboard-domain.contracts';
import { DASHBOARD_FINANCE_ORDERS, DASHBOARD_FINANCE_SHELL } from '../../dashboard-domain.ports';
import { RequestScope } from '../../request-cancellation';
import { buildPaymentPayload } from '../../sensitive-form-payloads';

@Injectable()
export class FinanceFacade {
  private readonly injector = inject(Injector);
  private readonly api = inject(AppointmentApiService);
  private readonly router = inject(Router);
  
  public readonly selectedMonth = signal(INITIAL_MONTH);

  public readonly monthlySummary = signal<MonthlySummaryV2 | null>(null);

  public readonly monthlyLoading = signal(false);

  public readonly financeCategories = signal<FinanceCategory[]>([]);

  public readonly financeEntries = signal<FinanceEntry[]>([]);

  public readonly financeSummary = signal<FinanceSummary | null>(null);

  public readonly financeQuality = signal<FinanceDataQualitySummary | null>(null);

  public readonly financeMonthClosure = signal<FinanceMonthClosure | null>(null);

  public readonly financeLoading = signal(false);

  public readonly financeClosureOpeningBalance = signal('');

  public readonly financeClosureClosingBalance = signal('');

  public readonly financeClosureNotes = signal('');

  public readonly financeMismatchPaymentId = signal('');

  public readonly financeMismatchResolution = signal<PaymentResolutionType>('discount');

  public readonly financeMismatchReason = signal('');

  public readonly editingFinanceEntryId = signal('');

  public readonly financeOccurredOn = signal(INITIAL_DATE);

  public readonly financeEntryKind = signal<FinanceEntryKind>('expense');

  public readonly financeCategoryCode = signal('marketing');

  public readonly financeVendor = signal('');

  public readonly financeDescription = signal('');

  public readonly financeAmountOriginal = signal('');

  public readonly financeCurrency = signal('PEN');

  public readonly financeExchangeRatePen = signal('');

  public readonly financeQuantity = signal('');

  public readonly financeUnit = signal('');

  public readonly financeChannel = signal('');

  public readonly financeCampaign = signal('');

  public readonly financeOrderId = signal('');

  public readonly financeEvidenceReference = signal('');

  public readonly financeNotes = signal('');

  public readonly financeDataQuality = signal<FinanceDataQuality>('actual');

  public readonly paymentAmountPaid = signal('');

  public readonly paymentAmountAgreed = signal('');

  public async changeMonth(month: string): Promise<void> {
    if (!/^\d{4}-\d{2}$/.test(month) || this.monthlyLoading() || this.financeLoading()) {
      return;
    }
    this.selectedMonth.set(month);
    const view = this.shell.activeView();
    this.monthlyLoading.set(view === 'summary');
    this.financeLoading.set(view === 'finance');
    this.shell.errorMessage.set(null);
    try {
      if (view === 'summary') {
        this.monthlySummary.set(await this.api.getMonthlySummaryV2(month));
      } else {
        const [entries, financeSummary, financeQuality, financeMonthClosure, monthlySummary] = await Promise.all([
          this.api.getFinanceEntries(month),
          this.api.getFinanceSummary(month),
          this.api.getFinanceDataQuality(month),
          this.api.getFinanceMonthClosure(month),
          this.api.getMonthlySummaryV2(month),
        ]);
        this.financeEntries.set(entries);
        this.financeSummary.set(financeSummary);
        this.financeQuality.set(financeQuality);
        this.applyFinanceMonthClosure(financeMonthClosure);
        this.monthlySummary.set(monthlySummary);
      }
    } catch (error) {
      this.shell.errorMessage.set(this.shell.readError(error));
    } finally {
      this.monthlyLoading.set(false);
      this.financeLoading.set(false);
    }
    if (['summary', 'finance'].includes(view)) {
      void this.router.navigate([], {
        queryParams: { month },
        queryParamsHandling: 'merge',
        replaceUrl: true,
      });
    }
  }

  public openNewFinanceEntry(): void {
    this.clearFinanceForm();
    this.shell.openModal('finance-entry');
  }

  public openEditFinanceEntry(entry: FinanceEntry): void {
    if (entry.status !== 'active') {
      return;
    }
    this.editingFinanceEntryId.set(entry.entry_id);
    this.financeOccurredOn.set(entry.occurred_on);
    this.financeEntryKind.set(entry.entry_kind);
    this.financeCategoryCode.set(entry.category_code);
    this.financeVendor.set(entry.vendor ?? '');
    this.financeDescription.set(entry.description);
    this.financeAmountOriginal.set(String(entry.amount_original));
    this.financeCurrency.set(entry.currency);
    this.financeExchangeRatePen.set(
      entry.currency === 'PEN' ? '' : String(entry.exchange_rate_pen ?? ''),
    );
    this.financeQuantity.set(String(entry.quantity ?? ''));
    this.financeUnit.set(entry.unit ?? '');
    this.financeChannel.set(entry.channel ?? '');
    this.financeCampaign.set(entry.campaign ?? '');
    this.financeOrderId.set(entry.order_id ?? '');
    this.financeEvidenceReference.set(entry.evidence_reference ?? '');
    this.financeNotes.set(entry.notes ?? '');
    this.financeDataQuality.set(entry.data_quality);
    this.shell.openModal('finance-entry');
  }

  public openEditFinanceEntryById(entryId: string): void {
    const entry = this.financeEntries().find((item) => item.entry_id === entryId);
    if (entry) {
      this.openEditFinanceEntry(entry);
    }
  }

  public requestSaveFinanceEntry(): void {
    const payload = this.financeFormPayload();
    if (!payload) {
      return;
    }
    const entryId = this.editingFinanceEntryId();
    this.shell.setPendingAction({
      title: entryId ? 'Actualizar movimiento' : 'Registrar movimiento',
      message: entryId
        ? `Actualizar ${entryId}. El historial conservara la fecha de modificacion.`
        : `Registrar ${payload.description} por ${payload.amount_original} ${payload.currency}.`,
      execute: () =>
        entryId
          ? this.api.updateFinanceEntry(entryId, payload)
          : this.api.createFinanceEntry(payload),
      onSuccess: () => {
        this.shell.activeModal.set(null);
        this.clearFinanceForm();
      },
    });
  }

  public async requestVoidFinanceEntry(entry: FinanceEntry): Promise<void> {
    if (entry.status !== 'active') {
      return;
    }
    void (await this.shell.getSweetAlert()).fire({
      title: 'Anular movimiento',
      text: 'Escribe el motivo. El registro se conservara para auditoria y dejara de calcularse.',
      input: 'text',
      inputLabel: 'Motivo de anulacion',
      inputValidator: (value) =>
        value.trim().length >= 3 ? undefined : 'Ingresa al menos 3 caracteres.',
      showCancelButton: true,
      confirmButtonText: 'Anular',
      cancelButtonText: 'Cancelar',
      confirmButtonColor: '#b42318',
    }).then(async (result) => {
      if (!result.isConfirmed || !result.value) {
        return;
      }
      this.shell.actionBusy.set(true);
      try {
        await this.api.voidFinanceEntry(entry.entry_id, String(result.value).trim());
        await this.shell.refreshAll();
        this.shell.showToast('Movimiento anulado');
      } catch (error) {
        this.shell.errorMessage.set(this.shell.readError(error));
      } finally {
        this.shell.actionBusy.set(false);
      }
    });
  }

  public financeKindLabel(kind: FinanceEntryKind): string {
    const labels: Record<FinanceEntryKind, string> = {
      expense: 'Gasto directo',
      prepaid_topup: 'Recarga prepagada',
      prepaid_consumption: 'Consumo prepagado',
      refund: 'Reembolso',
    };
    return labels[kind];
  }

  public financeConversionComplete(summary: FinanceSummary): boolean {
    return summary.conversion_complete;
  }

  public formatOriginalMoney(entry: FinanceEntry): string {
    return `${entry.currency} ${entry.amount_original.toFixed(entry.currency === 'PEN' ? 2 : 4)}`;
  }

  public startFinanceMismatchResolution(paymentId: string): void {
    this.financeMismatchPaymentId.set(paymentId);
    this.financeMismatchResolution.set('discount');
    this.financeMismatchReason.set('');
  }

  public cancelFinanceMismatchResolution(): void {
    this.financeMismatchPaymentId.set('');
    this.financeMismatchReason.set('');
  }

  public requestReconcileFinancePayment(paymentId: string): void {
    const reason = this.financeMismatchReason().trim();
    if (reason.length < 3) {
      this.shell.errorMessage.set('Indica una causa de al menos 3 caracteres.');
      return;
    }
    const resolution = this.financeMismatchResolution();
    void this.shell.setPendingAction({
      title: 'Conciliar diferencia de pago',
      message: `Registrar ${this.financeResolutionLabel(resolution).toLowerCase()} como causa explícita. El importe original no se reescribe.`,
      execute: () =>
        this.api.reconcileFinancePaymentAmount(paymentId, {
          resolution_type: resolution,
          reason,
        }),
      successMessage: 'Diferencia de pago conciliada',
      onSuccess: () => this.cancelFinanceMismatchResolution(),
    });
  }

  public financeResolutionLabel(resolution: PaymentResolutionType): string {
    return {
      discount: 'Descuento',
      waiver: 'Condonación',
      correction: 'Corrección',
    }[resolution];
  }

  public requestSaveFinanceMonthClosure(status: 'draft' | 'reconciled'): void {
    const opening = String(this.financeClosureOpeningBalance() ?? '').trim();
    const closing = String(this.financeClosureClosingBalance() ?? '').trim();
    if (status === 'reconciled' && (!opening || !closing)) {
      this.shell.errorMessage.set('Para conciliar, completa saldo inicial y saldo final.');
      return;
    }
    void this.shell.setPendingAction({
      title: status === 'reconciled' ? 'Cerrar mes financiero' : 'Guardar borrador de cierre',
      message:
        status === 'reconciled'
          ? 'El cierre solo se guardará si no quedan movimientos pendientes, conversiones faltantes ni diferencias de pago sin conciliar.'
          : 'Se guardarán los saldos y notas sin declarar el mes conciliado.',
      execute: () =>
        this.api.saveFinanceMonthClosure({
          month: this.selectedMonth(),
          opening_prepaid_balance: opening || null,
          closing_prepaid_balance: closing || null,
          status,
          notes: this.financeClosureNotes().trim() || null,
        }),
      successMessage: status === 'reconciled' ? 'Mes financiero conciliado' : 'Borrador de cierre guardado',
    });
  }

  public financeClosureCanReconcile(): boolean {
    const closure = this.financeMonthClosure();
    const quality = this.financeQuality();
    return Boolean(
      closure &&
        quality &&
        this.financeSelectedMonthIsClosed() &&
        closure.movements.pending_entries === 0 &&
        closure.movements.unconverted_entries === 0 &&
        quality.unreconciled_paid_amount_mismatch_count === 0,
    );
  }

  public financeSelectedMonthIsClosed(): boolean {
    return this.selectedMonth() < INITIAL_MONTH;
  }

  public missingAcquisitionSourceOrders(): number {
    return (
      this.monthlySummary()?.cohort_metrics.sources.find((source) => source.source === 'sin_fuente')
        ?.orders_created ?? 0
    );
  }

  public financeReviewIssueCount(): number {
    const quality = this.financeQuality();
    if (!quality) {
      return 0;
    }
    return (
      quality.unreconciled_paid_amount_mismatch_count +
      quality.unconverted_entries.length +
      quality.data_quality.estimated.entry_count +
      quality.data_quality.pending.entry_count +
      (this.monthlySummary()?.current_attention_snapshot.missing_contact_count ?? 0) +
      this.missingAcquisitionSourceOrders()
    );
  }

  public metricPeriodLabel(period: MetricPeriod): string {
    if (period.coverage_end_exclusive <= period.start) {
      return 'Sin cobertura todavía';
    }
    const start = this.shell.formatDate(period.start);
    const end = new Date(`${period.coverage_end_exclusive}T12:00:00`);
    end.setDate(end.getDate() - 1);
    return `${start} – ${this.shell.formatDate(end.toISOString().slice(0, 10))}`;
  }

  public selectedMonthLabel(): string {
    const [year, month] = this.selectedMonth().split('-').map(Number);
    return new Intl.DateTimeFormat('es-PE', { month: 'long', year: 'numeric' }).format(
      new Date(year, month - 1, 1),
    );
  }

  public monthlyRevenueComparison(
    comparison: NonNullable<MonthlySummaryV2['comparisons']['same_day_window']>,
  ): string {
    return this.revenueDeltaLabel(
      comparison.selected.metrics.revenue_collected,
      comparison.previous.metrics.revenue_collected,
    );
  }

  public closedMonthRevenueComparison(summary: MonthlySummaryV2): string {
    return this.revenueDeltaLabel(
      summary.comparisons.closed_months.selected.metrics.revenue_collected,
      summary.comparisons.closed_months.previous.metrics.revenue_collected,
    );
  }

  public dailyRevenueWidth(summary: MonthlySummaryV2, amount: number): number {
    const maximum = Math.max(
      ...summary.period_metrics.daily_revenue.map((item) => item.amount),
      0,
    );
    return maximum ? Math.max((amount / maximum) * 100, 3) : 0;
  }

  private revenueDeltaLabel(current: number, previous: number): string {
    if (!previous) {
      return current > 0 ? `${this.shell.formatMoney(current)} · sin cobros comparables previos` : 'Sin cobros en ambos rangos';
    }
    const change = current / previous - 1;
    return `${this.shell.formatMoney(current)} · ${change >= 0 ? '+' : ''}${this.shell.formatPercent(change)}`;
  }

  public async openPayment(order: ServiceOrder): Promise<void> {
    this.orders.selectOrder(order.order_id, false);
    const standardAmount = this.orders.standardPackageAmount() ?? '';
    const agreedAmount = order.amount_agreed ?? order.reservation_price ?? standardAmount;
    this.paymentAmountAgreed.set(agreedAmount);
    this.paymentAmountPaid.set(agreedAmount);
    this.shell.openModal('payment');
    await this.orders.loadSelectedOrderDetail(order.order_id);
    const refreshed = this.orders.selectedOrderDetail();
    if (refreshed?.order_id === order.order_id) {
      const refreshedAmount =
        refreshed.amount_agreed ?? refreshed.reservation_price ?? standardAmount;
      this.paymentAmountAgreed.set(refreshedAmount);
      this.paymentAmountPaid.set(refreshedAmount);
    }
  }

  public setQuickPaymentAmount(amount: string): void {
    this.shell.editField(this.paymentAmountPaid, amount);
  }

  public requestMarkPaid(): void {
    const order = this.orders.requireSelectedOrder();
    if (!order) {
      return;
    }
    const result = buildPaymentPayload(this.paymentAmountPaid(), this.paymentAmountAgreed(), {
      expected_payment_status: order.payment_status,
      expected_amount_agreed: order.amount_agreed,
      expected_amount_paid: order.amount_paid ?? '0.00',
    });
    if (!result.payload) {
      this.shell.errorMessage.set(result.error);
      return;
    }
    const payload = result.payload;
    const paid = Number(payload.amount_paid);
    const agreed = Number(payload.amount_agreed);
    const isPartial = Number.isFinite(agreed) && paid < agreed;
    this.shell.setPendingAction({
      title: isPartial ? 'Registrar abono' : 'Confirmar pago completo',
      message: isPartial
        ? `Guardar total acumulado de S/${payload.amount_paid} para ${order.order_id}. El saldo seguirá pendiente.`
        : `Cerrar como pagado con S/${payload.amount_paid} para ${order.order_id} e iniciar el postpago.`,
      execute: () => isPartial
        ? this.api.recordPartialPayment(order.order_id, payload)
        : this.api.markPaymentPaid(order.order_id, payload),
      successMessage: isPartial
        ? 'Abono registrado; el saldo permanece pendiente'
        : 'Pago completo registrado; envío automático en proceso',
      onSuccess: () => this.shell.activeModal.set(null),
    });
  }

  public paymentLabel(order: ServiceOrder): string {
    if (!order.charge_required) {
      return 'Sin cobro';
    }
    return this.shell.statusLabel(order.payment_status, 'Sin pago');
  }

  public paymentAmountLabel(order: ServiceOrder): string {
    if (!order.charge_required) {
      return '';
    }
    if (order.payment_status === 'pending' && order.amount_agreed) {
      const agreed = Number(order.amount_agreed);
      const paid = Number(order.amount_paid ?? 0);
      if (Number.isFinite(agreed) && Number.isFinite(paid)) {
        return Math.max(agreed - paid, 0).toFixed(2);
      }
    }
    return order.amount_paid ?? order.amount_agreed ?? '';
  }

  private financeFormPayload(): FinanceEntryPayload | null {
    const amountOriginal = String(this.financeAmountOriginal() ?? '').trim();
    const exchangeRate = String(this.financeExchangeRatePen() ?? '').trim();
    const quantity = String(this.financeQuantity() ?? '').trim();
    const amount = Number(amountOriginal);
    if (!this.financeOccurredOn() || !this.financeDescription().trim()) {
      this.shell.errorMessage.set('Fecha y descripcion son obligatorias.');
      return null;
    }
    if (!Number.isFinite(amount) || amount <= 0) {
      this.shell.errorMessage.set('El importe debe ser mayor que cero.');
      return null;
    }
    if (
      this.financeCurrency() !== 'PEN' &&
      exchangeRate &&
      (!Number.isFinite(Number(exchangeRate)) || Number(exchangeRate) <= 0)
    ) {
      this.shell.errorMessage.set('El tipo de cambio debe ser mayor que cero.');
      return null;
    }
    return {
      occurred_on: this.financeOccurredOn(),
      entry_kind: this.financeEntryKind(),
      category_code: this.financeCategoryCode(),
      vendor: this.shell.optionalText(this.financeVendor()),
      description: this.financeDescription().trim(),
      amount_original: amountOriginal,
      currency: this.financeCurrency().trim().toUpperCase(),
      exchange_rate_pen: this.financeCurrency() === 'PEN' ? null : this.shell.optionalText(exchangeRate),
      quantity: this.shell.optionalText(quantity),
      unit: this.shell.optionalText(this.financeUnit()),
      channel: this.shell.optionalText(this.financeChannel()),
      campaign: this.shell.optionalText(this.financeCampaign()),
      order_id: this.shell.optionalText(this.financeOrderId()),
      evidence_reference: this.shell.optionalText(this.financeEvidenceReference()),
      notes: this.shell.optionalText(this.financeNotes()),
      data_quality: this.financeDataQuality(),
    };
  }

  public clearFinanceForm(): void {
    this.editingFinanceEntryId.set('');
    this.financeOccurredOn.set(INITIAL_DATE);
    this.financeEntryKind.set('expense');
    this.financeCategoryCode.set('marketing');
    this.financeVendor.set('');
    this.financeDescription.set('');
    this.financeAmountOriginal.set('');
    this.financeCurrency.set('PEN');
    this.financeExchangeRatePen.set('');
    this.financeQuantity.set('');
    this.financeUnit.set('');
    this.financeChannel.set('');
    this.financeCampaign.set('');
    this.financeOrderId.set('');
    this.financeEvidenceReference.set('');
    this.financeNotes.set('');
    this.financeDataQuality.set('actual');
    this.shell.formDirty.set(false);
  }

  private applyFinanceMonthClosure(payload: FinanceMonthClosure): void {
    this.financeMonthClosure.set(payload);
    this.financeClosureOpeningBalance.set(
      payload.closure?.opening_prepaid_balance === null ||
        payload.closure?.opening_prepaid_balance === undefined
        ? ''
        : String(payload.closure.opening_prepaid_balance),
    );
    this.financeClosureClosingBalance.set(
      payload.closure?.closing_prepaid_balance === null ||
        payload.closure?.closing_prepaid_balance === undefined
        ? ''
        : String(payload.closure.closing_prepaid_balance),
    );
    this.financeClosureNotes.set(payload.closure?.notes ?? '');
  }

  public async loadFinanceView(scope: RequestScope): Promise<void> {
      const categoriesRequest = this.financeCategories().length
        ? Promise.resolve(this.financeCategories())
        : this.api.getFinanceCategories(scope);
      const [
        financeCategories,
        financeEntries,
        financeSummary,
        financeQuality,
        financeMonthClosure,
        monthlySummary,
      ] = await Promise.all([
        categoriesRequest,
        this.api.getFinanceEntries(this.selectedMonth(), scope),
        this.api.getFinanceSummary(this.selectedMonth(), scope),
        this.api.getFinanceDataQuality(this.selectedMonth(), scope),
        this.api.getFinanceMonthClosure(this.selectedMonth(), scope),
        this.api.getMonthlySummaryV2(this.selectedMonth(), scope),
      ]);
      this.financeCategories.set(financeCategories);
      this.financeEntries.set(financeEntries);
      this.financeSummary.set(financeSummary);
      this.financeQuality.set(financeQuality);
      this.applyFinanceMonthClosure(financeMonthClosure);
      this.monthlySummary.set(monthlySummary);
      return;
    }

  private get shell() { return this.injector.get(DASHBOARD_FINANCE_SHELL); }

  private get orders() { return this.injector.get(DASHBOARD_FINANCE_ORDERS); }
}
