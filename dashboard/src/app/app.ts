import {
  Component,
  HostListener,
  OnDestroy,
  WritableSignal,
  computed,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import Swal from 'sweetalert2';

import {
  ApiActionResponse,
  AppointmentApiService,
  CloseServiceOrderPayload,
  ContactUpdatePayload,
  CreateServiceOrderPayload,
  FinanceCategory,
  FinanceDataQuality,
  FinanceEntry,
  FinanceEntryKind,
  FinanceEntryPayload,
  FinanceSummary,
  HealthPayload,
  ManualSession,
  MonthlySummary,
  PaymentPaidPayload,
  PriorityUpdatePayload,
  ReservationRestrictionsUpdatePayload,
  RunDetail,
  RunSummary,
  ServiceOrder,
  ServiceOrderDetail,
  WorkerCommand,
  WorkerStatus,
  WhatsAppMessagePackage,
  WhatsAppWebDraftResponse,
  apiErrorMessage,
} from './appointment-api.service';
import { formatPeruDate, formatPeruDateTime, formatPeruTime } from './peru-date-time';

type LoadState = 'idle' | 'loading' | 'ready' | 'error';
type ViewKey = 'summary' | 'finance' | 'orders' | 'runs';
type ModalKind =
  | 'edit-order'
  | 'order-actions'
  | 'create-order'
  | 'worker-restart'
  | 'finance-entry'
  | 'whatsapp'
  | null;
type OrderQuickFilter =
  | 'all'
  | 'ready'
  | 'payment_pending'
  | 'confirmed'
  | 'archived'
  | 'closed_no_charge'
  | 'restricted';
type OrderSortKey =
  | 'queue'
  | 'priority'
  | 'created_at'
  | 'updated_at'
  | 'status'
  | 'reservation'
  | 'payment'
  | 'closure'
  | 'applicant';
type ClosureReason =
  | 'completed_by_us'
  | 'family_no_charge'
  | 'client_withdrew'
  | 'external_slot'
  | 'duplicate'
  | 'not_serviceable';
type SortDirection = 'asc' | 'desc';
type PendingAction = {
  title: string;
  message: string;
  execute: () => Promise<ApiActionResponse>;
  containsSecret?: boolean;
  onSuccess?: (response: ApiActionResponse) => void;
  onSettled?: () => void;
};
type OrderNextAction = {
  key: 'manual-session' | 'activate' | 'payment' | 'review' | 'none';
  label: string;
  description: string;
  disabled: boolean;
};

const AUTO_REFRESH_INTERVAL_MS = 15_000;
const WEEKDAY_NAMES = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];
const SPANISH_LIST_FORMAT = new Intl.ListFormat('es-PE', {
  style: 'long',
  type: 'conjunction',
});
const INITIAL_MONTH = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Lima',
  year: 'numeric',
  month: '2-digit',
}).format(new Date());
const INITIAL_DATE = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Lima',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
}).format(new Date());

@Component({
  selector: 'app-root',
  imports: [FormsModule],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App implements OnDestroy {
  protected readonly formatDate = formatPeruDate;
  protected readonly formatDateTime = formatPeruDateTime;
  protected readonly formatTime = formatPeruTime;
  private readonly api = inject(AppointmentApiService);
  private readonly autoRefreshTimer = window.setInterval(() => {
    void this.refreshFromTimer();
  }, AUTO_REFRESH_INTERVAL_MS);
  private readonly activeManualSessionIds = new Set<string>();
  private lastFocusedElement: HTMLElement | null = null;

  protected readonly activeView = signal<ViewKey>('orders');
  protected readonly activeModal = signal<ModalKind>(null);
  protected readonly autoRefreshEnabled = signal(true);
  protected readonly formDirty = signal(false);
  protected readonly lastUpdatedAt = signal<string | null>(null);
  protected readonly orderFilter = signal('');
  protected readonly orderQuickFilter = signal<OrderQuickFilter>('all');
  protected readonly orderSortKey = signal<OrderSortKey>('queue');
  protected readonly orderSortDirection = signal<SortDirection>('desc');
  protected readonly runStatusFilter = signal('');
  protected readonly health = signal<HealthPayload | null>(null);
  protected readonly worker = signal<WorkerStatus | null>(null);
  protected readonly orders = signal<ServiceOrder[]>([]);
  protected readonly runs = signal<RunSummary[]>([]);
  protected readonly selectedRunId = signal('');
  protected readonly selectedRunDetail = signal<RunDetail | null>(null);
  protected readonly runDetailState = signal<LoadState>('idle');
  protected readonly runDetailError = signal<string | null>(null);
  protected readonly workerCommands = signal<WorkerCommand[]>([]);
  protected readonly manualSessions = signal<ManualSession[]>([]);
  protected readonly selectedMonth = signal(INITIAL_MONTH);
  protected readonly monthlySummary = signal<MonthlySummary | null>(null);
  protected readonly monthlyLoading = signal(false);
  protected readonly financeCategories = signal<FinanceCategory[]>([]);
  protected readonly financeEntries = signal<FinanceEntry[]>([]);
  protected readonly financeSummary = signal<FinanceSummary | null>(null);
  protected readonly financeLoading = signal(false);
  protected readonly editingFinanceEntryId = signal('');
  protected readonly financeOccurredOn = signal(INITIAL_DATE);
  protected readonly financeEntryKind = signal<FinanceEntryKind>('expense');
  protected readonly financeCategoryCode = signal('marketing');
  protected readonly financeVendor = signal('');
  protected readonly financeDescription = signal('');
  protected readonly financeAmountOriginal = signal('');
  protected readonly financeCurrency = signal('PEN');
  protected readonly financeExchangeRatePen = signal('');
  protected readonly financeQuantity = signal('');
  protected readonly financeUnit = signal('');
  protected readonly financeChannel = signal('');
  protected readonly financeCampaign = signal('');
  protected readonly financeOrderId = signal('');
  protected readonly financeEvidenceReference = signal('');
  protected readonly financeNotes = signal('');
  protected readonly financeDataQuality = signal<FinanceDataQuality>('actual');
  protected readonly loadState = signal<LoadState>('idle');
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly successMessage = signal<string | null>(null);
  protected readonly copiedLabel = signal<string | null>(null);
  protected readonly selectedOrderId = signal('');
  protected readonly orderPanelOpen = signal(false);
  protected readonly selectedOrderDetail = signal<ServiceOrderDetail | null>(null);
  protected readonly orderDetailLoading = signal(false);
  protected readonly contactName = signal('');
  protected readonly contactWhatsapp = signal('');
  protected readonly contactSource = signal('whatsapp');
  protected readonly orderPriority = signal(0);
  protected readonly orderMinimumReservationHour = signal('');
  protected readonly orderMinimumReservationDate = signal('');
  protected readonly orderMaximumReservationDate = signal('');
  protected readonly orderAllowedWeekdays = signal<number[]>([]);
  protected readonly paymentAmountPaid = signal('');
  protected readonly paymentAmountAgreed = signal('');
  protected readonly newDocumentNumber = signal('');
  protected readonly newPassword = signal('');
  protected readonly newContactName = signal('');
  protected readonly newContactWhatsapp = signal('');
  protected readonly newContactSource = signal('');
  protected readonly newMinimumReservationDate = signal('');
  protected readonly newMaximumReservationDate = signal('');
  protected readonly newAllowedWeekdays = signal<number[]>([]);
  protected readonly splitKeepParentActive = signal(false);
  protected readonly closureReason = signal<ClosureReason>('client_withdrew');
  protected readonly closureNote = signal('');
  protected readonly actionBusy = signal(false);
  protected readonly pendingAction = signal<PendingAction | null>(null);
  protected readonly whatsappPackage = signal<WhatsAppMessagePackage | null>(null);
  protected readonly whatsappPackageLoading = signal(false);
  protected readonly whatsappTestRecipient = signal('');
  protected readonly whatsappTestMode = signal(false);
  protected readonly whatsappWebBusy = signal(false);
  protected readonly whatsappWebResult = signal<WhatsAppWebDraftResponse | null>(null);
  protected readonly whatsappManualFallbackOpen = signal(false);

  protected readonly selectedOrder = computed(() => {
    const selected = this.selectedOrderId();
    return this.orders().find((order) => order.order_id === selected) ?? this.orders()[0] ?? null;
  });
  protected readonly currentOrder = computed(() => {
    const currentOrderId = this.worker()?.current_order_id;
    return this.orders().find((order) => order.order_id === currentOrderId) ?? null;
  });
  protected readonly modalOrder = computed(() => this.selectedOrder());
  protected readonly filteredOrders = computed(() => {
    const filter = this.orderFilter().trim().toLowerCase();
    const quickFilter = this.orderQuickFilter();
    const filtered = this.orders().filter((order) => {
      const matchesText =
        !filter ||
        [
          order.order_id,
          order.applicant_name,
          order.document_number_masked,
          order.contact_name,
          order.contact_source,
          order.contact_whatsapp_masked,
          order.status,
          order.reservation_status,
          order.payment_status,
          order.closure_reason,
          order.closure_note,
          order.program_expediente,
          order.program_plate,
          order.parent_order_id,
        ]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(filter));
      return matchesText && this.matchesOrderQuickFilter(order, quickFilter);
    });
    return this.sortOrders(filtered);
  });
  protected readonly orderQuickFilters = computed(() => [
    { key: 'all' as const, label: 'Todas', count: this.orders().length },
    { key: 'ready' as const, label: 'Ready', count: this.countOrders('ready') },
    {
      key: 'payment_pending' as const,
      label: 'Pagos pendientes',
      count: this.countOrders('payment_pending'),
    },
    { key: 'confirmed' as const, label: 'Confirmadas', count: this.countOrders('confirmed') },
    { key: 'archived' as const, label: 'Archivadas', count: this.countOrders('archived') },
    {
      key: 'closed_no_charge' as const,
      label: 'Cerradas sin cobro',
      count: this.countOrders('closed_no_charge'),
    },
    {
      key: 'restricted' as const,
      label: 'Con restricciones',
      count: this.countOrders('restricted'),
    },
  ]);
  protected readonly filteredRuns = computed(() => {
    const status = this.runStatusFilter().trim();
    if (!status) {
      return this.runs();
    }
    return this.runs().filter((run) => run.status === status);
  });
  protected readonly runStatuses = computed(() =>
    Array.from(
      new Set(
        this.runs()
          .map((run) => run.status)
          .filter(Boolean),
      ),
    ).sort(),
  );
  protected readonly readyOrders = computed(
    () => this.orders().filter((order) => order.status === 'ready').length,
  );
  protected readonly pendingPaymentOrders = computed(
    () => this.orders().filter((order) => order.payment_status === 'pending').length,
  );
  protected readonly confirmedOrders = computed(
    () => this.orders().filter((order) => order.reservation_status === 'confirmed').length,
  );
  protected readonly failedRuns = computed(
    () => this.runs().filter((run) => this.statusTone(run.status) === 'bad').length,
  );
  protected readonly selectedOrderRuns = computed(() => {
    const orderId = this.selectedOrder()?.order_id;
    if (!orderId) {
      return [];
    }
    return this.runs().filter((run) => run.order_id === orderId);
  });
  protected readonly selectedOrderChildren = computed(() => {
    const orderId = this.selectedOrder()?.order_id;
    return orderId ? this.orders().filter((order) => order.parent_order_id === orderId) : [];
  });
  protected readonly orderNextAction = computed<OrderNextAction>(() => {
    const order = this.selectedOrder();
    if (!order) {
      return {
        key: 'none',
        label: 'Selecciona una orden',
        description: 'Elige una fila para ver el siguiente paso operativo.',
        disabled: true,
      };
    }
    if (this.isClosedOrder(order)) {
      return {
        key: 'none',
        label: 'Sin acciones pendientes',
        description: `La orden esta cerrada como ${this.closureDisplay(order)}.`,
        disabled: true,
      };
    }
    if (order.payment_status === 'pending') {
      return {
        key: 'payment',
        label: 'Registrar pago',
        description: 'La reserva esta lista y el cobro sigue pendiente.',
        disabled: false,
      };
    }
    if (order.status === 'paused') {
      const blocked = this.hasActiveChildOrders(order);
      return {
        key: 'activate',
        label: blocked ? 'Padre bloqueado por subordenes' : 'Activar orden',
        description: blocked
          ? 'Gestiona primero las subordenes activas.'
          : 'La orden esta pausada y puede volver a la cola.',
        disabled: blocked,
      };
    }
    if (order.status === 'ready') {
      return {
        key: 'manual-session',
        label: 'Abrir sesion manual',
        description: 'La orden esta lista para una revision manual independiente.',
        disabled: this.actionBusy(),
      };
    }
    return {
      key: 'review',
      label: 'Revisar acciones',
      description: `Revisa las opciones compatibles con el estado ${order.status}.`,
      disabled: false,
    };
  });
  protected readonly selectedRun = computed(() => this.selectedRunDetail());
  protected readonly selectedOrderWhatsappPlaceholder = computed(
    () => this.selectedOrder()?.contact_whatsapp_masked ?? 'sin WhatsApp registrado',
  );
  protected readonly selectedOrderWhatsapp = computed(() => {
    const order = this.selectedOrder();
    const detail = this.selectedOrderDetail();
    if (order && detail?.order_id === order.order_id) {
      return detail.contact_whatsapp ?? 'sin WhatsApp';
    }
    return order?.contact_whatsapp_masked ?? 'sin WhatsApp';
  });
  protected readonly autoRefreshPaused = computed(
    () =>
      !this.autoRefreshEnabled() || this.formDirty() || this.actionBusy() || !!this.pendingAction(),
  );

  constructor() {
    void this.refreshAll();
  }

  ngOnDestroy(): void {
    window.clearInterval(this.autoRefreshTimer);
    this.closeTrackedManualSessionsWithBeacon();
  }

  @HostListener('window:beforeunload')
  protected handleBeforeUnload(): void {
    this.closeTrackedManualSessionsWithBeacon();
  }

  @HostListener('document:keydown.escape')
  protected handleEscape(): void {
    if (this.actionBusy()) {
      return;
    }
    if (this.pendingAction()) {
      Swal.close();
      return;
    }
    if (this.activeModal()) {
      this.closeModal();
      return;
    }
    if (this.orderPanelOpen()) {
      this.closeOrderPanel();
    }
  }

  protected async refreshAll(): Promise<void> {
    await this.refreshHealth();
    this.loadState.set('loading');
    this.errorMessage.set(null);

    try {
      const [
        worker,
        orders,
        runs,
        workerCommands,
        manualSessions,
        monthlySummary,
        financeCategories,
        financeEntries,
        financeSummary,
      ] =
        await Promise.all([
        this.api.getWorker(),
        this.api.getServiceOrders(),
        this.api.getRuns(),
        this.api.getWorkerCommands(),
        this.api.getManualSessions(),
        this.api.getMonthlySummary(this.selectedMonth()),
        this.api.getFinanceCategories(),
        this.api.getFinanceEntries(this.selectedMonth()),
        this.api.getFinanceSummary(this.selectedMonth()),
      ]);
      this.worker.set(worker);
      this.orders.set(orders);
      this.runs.set(runs);
      this.workerCommands.set(workerCommands);
      this.manualSessions.set(manualSessions);
      this.monthlySummary.set(monthlySummary);
      this.financeCategories.set(financeCategories);
      this.financeEntries.set(financeEntries);
      this.financeSummary.set(financeSummary);
      this.keepValidSelection(orders);
      this.hydrateSelectedOrderForms();
      if (this.orderPanelOpen() && this.selectedOrderId() && !this.selectedOrderDetail()) {
        void this.loadSelectedOrderDetail(this.selectedOrderId());
      }
      this.lastUpdatedAt.set(this.formatClock(new Date()));
      this.loadState.set('ready');
    } catch (error) {
      this.loadState.set('error');
      this.errorMessage.set(this.readError(error));
    }
  }

  protected async refreshNow(): Promise<void> {
    this.formDirty.set(false);
    await this.refreshAll();
  }

  protected async changeMonth(month: string): Promise<void> {
    if (!/^\d{4}-\d{2}$/.test(month) || this.monthlyLoading()) {
      return;
    }
    this.selectedMonth.set(month);
    this.monthlyLoading.set(true);
    this.financeLoading.set(true);
    this.errorMessage.set(null);
    try {
      const [summary, entries, financeSummary] = await Promise.all([
        this.api.getMonthlySummary(month),
        this.api.getFinanceEntries(month),
        this.api.getFinanceSummary(month),
      ]);
      this.monthlySummary.set(summary);
      this.financeEntries.set(entries);
      this.financeSummary.set(financeSummary);
    } catch (error) {
      this.errorMessage.set(this.readError(error));
    } finally {
      this.monthlyLoading.set(false);
      this.financeLoading.set(false);
    }
  }

  protected openNewFinanceEntry(): void {
    this.clearFinanceForm();
    this.openModal('finance-entry');
  }

  protected openEditFinanceEntry(entry: FinanceEntry): void {
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
    this.openModal('finance-entry');
  }

  protected requestSaveFinanceEntry(): void {
    const payload = this.financeFormPayload();
    if (!payload) {
      return;
    }
    const entryId = this.editingFinanceEntryId();
    this.setPendingAction({
      title: entryId ? 'Actualizar movimiento' : 'Registrar movimiento',
      message: entryId
        ? `Actualizar ${entryId}. El historial conservara la fecha de modificacion.`
        : `Registrar ${payload.description} por ${payload.amount_original} ${payload.currency}.`,
      execute: () =>
        entryId
          ? this.api.updateFinanceEntry(entryId, payload)
          : this.api.createFinanceEntry(payload),
      onSuccess: () => {
        this.activeModal.set(null);
        this.clearFinanceForm();
      },
    });
  }

  protected requestVoidFinanceEntry(entry: FinanceEntry): void {
    if (entry.status !== 'active') {
      return;
    }
    void Swal.fire({
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
      this.actionBusy.set(true);
      try {
        await this.api.voidFinanceEntry(entry.entry_id, String(result.value).trim());
        await this.refreshAll();
        await this.showToast('Movimiento anulado');
      } catch (error) {
        this.errorMessage.set(this.readError(error));
      } finally {
        this.actionBusy.set(false);
      }
    });
  }

  protected financeKindLabel(kind: FinanceEntryKind): string {
    const labels: Record<FinanceEntryKind, string> = {
      expense: 'Gasto directo',
      prepaid_topup: 'Recarga prepagada',
      prepaid_consumption: 'Consumo prepagado',
      refund: 'Reembolso',
    };
    return labels[kind];
  }

  protected formatOriginalMoney(entry: FinanceEntry): string {
    return `${entry.currency} ${entry.amount_original.toFixed(entry.currency === 'PEN' ? 2 : 4)}`;
  }

  protected formatMoney(value: number): string {
    return new Intl.NumberFormat('es-PE', {
      style: 'currency',
      currency: 'PEN',
      minimumFractionDigits: 2,
    }).format(value);
  }

  protected formatPercent(value: number): string {
    return new Intl.NumberFormat('es-PE', {
      style: 'percent',
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    }).format(value);
  }

  protected hasReservationRestrictions(order: ServiceOrder): boolean {
    return Boolean(
      order.minimum_reservation_date ||
      order.maximum_reservation_date ||
      order.minimum_reservation_hour !== null ||
      (order.allowed_weekdays && order.allowed_weekdays.length > 0),
    );
  }

  protected restrictionDaysLabel(order: ServiceOrder): string {
    const days = Array.from(
      new Set((order.allowed_weekdays ?? []).filter((day) => day >= 1 && day <= 7)),
    ).sort((left, right) => left - right);
    if (!days.length) {
      return 'Cualquier día';
    }
    if (days.length === 7) {
      return 'Todos los días';
    }
    const isContinuous = days.every((day, index) => index === 0 || day === days[index - 1] + 1);
    if (isContinuous && days.length >= 3) {
      return this.capitalize(`${WEEKDAY_NAMES[days[0] - 1]} a ${WEEKDAY_NAMES[days.at(-1)! - 1]}`);
    }
    return this.capitalize(
      SPANISH_LIST_FORMAT.format(days.map((day) => WEEKDAY_NAMES[day - 1])),
    );
  }

  protected restrictionTimingLabel(order: ServiceOrder): string {
    const limits: string[] = [];
    if (order.minimum_reservation_date) {
      limits.push(`A partir del ${this.formatDate(order.minimum_reservation_date)}`);
    }
    if (order.maximum_reservation_date) {
      limits.push(`Hasta el ${this.formatDate(order.maximum_reservation_date)}`);
    }
    if (order.minimum_reservation_hour !== null) {
      limits.push(`Desde las ${this.formatTime(order.minimum_reservation_hour)}`);
    }
    return limits.length ? limits.join(' · ') : 'Sin límite de fecha u hora';
  }

  protected revenueComparison(summary: MonthlySummary): string {
    const previous = summary.previous.revenue_collected;
    if (!previous) {
      return summary.metrics.revenue_collected > 0 ? 'Sin cobros en el mes anterior' : 'Sin cambio';
    }
    const change = summary.metrics.revenue_collected / previous - 1;
    return `${change >= 0 ? '+' : ''}${this.formatPercent(change)} frente al mes anterior`;
  }

  protected revenueComparisonTone(summary: MonthlySummary): string {
    return summary.metrics.revenue_collected >= summary.previous.revenue_collected ? 'good' : 'bad';
  }

  protected dailyRevenueWidth(summary: MonthlySummary, amount: number): number {
    const maximum = Math.max(...summary.daily_revenue.map((item) => item.amount), 0);
    return maximum ? Math.max((amount / maximum) * 100, 3) : 0;
  }

  protected sourceRevenueWidth(summary: MonthlySummary, amount: number): number {
    const maximum = Math.max(...summary.sources.map((item) => item.revenue_collected), 0);
    return maximum ? Math.max((amount / maximum) * 100, 3) : 0;
  }

  protected openOrderFromSummary(orderId: string): void {
    this.activeView.set('orders');
    this.selectOrder(orderId);
  }

  protected selectOrder(orderId: string, loadDetail = true): void {
    if (!this.orderPanelOpen()) {
      this.captureFocus();
    }
    this.selectedOrderId.set(orderId);
    this.orderPanelOpen.set(true);
    this.selectedOrderDetail.set(null);
    this.formDirty.set(false);
    this.hydrateSelectedOrderForms();
    if (loadDetail) {
      void this.loadSelectedOrderDetail(orderId);
    }
    window.setTimeout(() => {
      document.querySelector<HTMLElement>('[data-order-panel]')?.focus();
    });
  }

  protected closeOrderPanel(): void {
    if (this.activeModal() || this.actionBusy()) {
      return;
    }
    this.orderPanelOpen.set(false);
    this.selectedOrderDetail.set(null);
    this.formDirty.set(false);
    this.restoreFocus();
  }

  protected async selectRun(runId: string): Promise<void> {
    this.selectedRunId.set(runId);
    this.selectedRunDetail.set(null);
    this.runDetailError.set(null);
    this.runDetailState.set('loading');
    try {
      const run = await this.api.getRun(runId);
      if (this.selectedRunId() !== run.run_id) {
        return;
      }
      this.selectedRunDetail.set(run);
      this.runDetailState.set('ready');
    } catch (error) {
      if (this.selectedRunId() !== runId) {
        return;
      }
      this.runDetailState.set('error');
      this.runDetailError.set(this.readError(error));
    }
  }

  protected closeRunDetail(): void {
    this.selectedRunId.set('');
    this.selectedRunDetail.set(null);
    this.runDetailError.set(null);
    this.runDetailState.set('idle');
  }

  protected runResultLabel(run: RunSummary): string {
    if (run.reservation_confirmed) {
      return 'Reserva confirmada';
    }
    if (run.reservation_attempted) {
      return 'Intento sin confirmacion';
    }
    return 'Sin intento de reserva';
  }

  protected runEvidencePaths(run: RunDetail): string[] {
    if (run.screenshot_paths?.length) {
      return run.screenshot_paths;
    }
    return run.screenshot_path ? [run.screenshot_path] : [];
  }

  protected async openEditOrder(order: ServiceOrder): Promise<void> {
    this.selectOrder(order.order_id, false);
    this.openModal('edit-order');
    await this.loadSelectedOrderDetail(order.order_id);
  }

  protected openOrderActions(order: ServiceOrder): void {
    this.selectOrder(order.order_id);
    this.openModal('order-actions');
  }

  protected openCreateOrder(): void {
    this.openModal('create-order');
  }

  protected openWhatsAppTest(): void {
    this.whatsappPackage.set(null);
    this.whatsappTestRecipient.set('');
    this.whatsappTestMode.set(true);
    this.whatsappWebResult.set(null);
    this.whatsappManualFallbackOpen.set(false);
    this.openModal('whatsapp');
  }

  protected async prepareWhatsAppTest(): Promise<void> {
    const recipient = this.whatsappTestRecipient().trim();
    if (!recipient) {
      this.errorMessage.set('Ingresa tu WhatsApp con codigo de pais, por ejemplo +51987654321.');
      return;
    }
    const message = await this.loadWhatsAppPackage(() => this.api.prepareWhatsAppTest(recipient));
    await this.prepareWhatsAppWebDraft(message);
  }

  protected async openOrderWhatsApp(order: ServiceOrder, allowResend = false): Promise<void> {
    this.whatsappPackage.set(null);
    this.whatsappTestMode.set(false);
    this.whatsappWebResult.set(null);
    this.whatsappManualFallbackOpen.set(false);
    this.openModal('whatsapp');
    try {
      const message = await this.loadWhatsAppPackage(() =>
        this.api.prepareOrderWhatsApp(order.order_id, allowResend),
      );
      await this.prepareWhatsAppWebDraft(message);
    } catch {
      if (!allowResend && order.whatsapp_message_status === 'sent') {
        const result = await Swal.fire({
          icon: 'warning',
          title: 'Mensaje ya enviado',
          text: 'Esta orden ya tiene un envio confirmado. ¿Deseas preparar un reenvio?',
          showCancelButton: true,
          confirmButtonText: 'Preparar reenvio',
          cancelButtonText: 'Cancelar',
        });
        if (result.isConfirmed) {
          await this.openOrderWhatsApp(order, true);
        }
      }
    }
  }

  protected canPrepareOrderWhatsApp(order: ServiceOrder): boolean {
    const baseEligible = (
      order.status === 'reserved_payment_pending' &&
      order.reservation_status === 'confirmed' &&
      order.payment_status === 'pending' &&
      !!order.amount_agreed &&
      order.charge_required
    );
    if (!baseEligible) {
      return false;
    }
    const detail = this.selectedOrderDetail();
    if (!detail || detail.order_id !== order.order_id) {
      return false;
    }
    return /^\+\d{8,15}$/.test(detail.contact_whatsapp ?? '');
  }

  protected whatsappPreparationHint(order: ServiceOrder): string {
    if (
      order.status !== 'reserved_payment_pending' ||
      order.reservation_status !== 'confirmed' ||
      order.payment_status !== 'pending' ||
      !order.amount_agreed ||
      !order.charge_required
    ) {
      return 'Requiere reserva confirmada, pago pendiente y monto acordado.';
    }
    const detail = this.selectedOrderDetail();
    if (!detail || detail.order_id !== order.order_id) {
      return 'Cargando contacto protegido...';
    }
    if (!/^\+\d{8,15}$/.test(detail.contact_whatsapp ?? '')) {
      return 'Corrige el WhatsApp al formato internacional, por ejemplo +51987654321.';
    }
    return order.whatsapp_message_status === 'sent'
      ? 'Ya fue enviado; la siguiente accion preparara un reenvio explicito.'
      : 'Listo para preparar saludo, constancia y cobro.';
  }

  protected async copyWhatsAppText(text: string, label: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(text);
      this.markCopied(label);
      await this.showToast('Texto copiado');
    } catch {
      this.errorMessage.set('El navegador no permitio copiar. Selecciona el texto manualmente.');
    }
  }

  protected async copyWhatsAppAttachment(): Promise<void> {
    const message = this.whatsappPackage();
    if (!message) {
      return;
    }
    try {
      const blob = await this.api.getWhatsAppAttachment(message.attachment_url);
      const png = blob.type === 'image/png' ? blob : new Blob([blob], { type: 'image/png' });
      await navigator.clipboard.write([new ClipboardItem({ 'image/png': png })]);
      this.markCopied('constancia');
      await this.showToast('Constancia copiada. Pegala con Ctrl+V en WhatsApp.');
    } catch {
      this.errorMessage.set(
        'No se pudo copiar la imagen. Usa Descargar constancia como alternativa.',
      );
    }
  }

  protected async prepareWhatsAppWebDraft(
    preparedMessage?: WhatsAppMessagePackage,
  ): Promise<void> {
    const message = preparedMessage ?? this.whatsappPackage();
    if (!message || this.whatsappWebBusy()) {
      return;
    }
    this.whatsappWebBusy.set(true);
    this.errorMessage.set(null);
    try {
      const response = await this.api.prepareWhatsAppWebDraft(message.message_id, 'album');
      this.whatsappWebResult.set(response);
      this.whatsappManualFallbackOpen.set(response.status === 'web_unavailable');
      if (response.status === 'login_required') {
        await Swal.fire({
          icon: 'info',
          title: 'Vincula WhatsApp Web',
          text: response.message,
          confirmButtonText: 'Entendido',
        });
      } else if (response.status === 'draft_ready') {
        this.successMessage.set('WhatsApp preparado: revisa el álbum y pulsa Enviar.');
      }
    } catch (error) {
      this.errorMessage.set(this.readError(error));
      this.whatsappManualFallbackOpen.set(true);
    } finally {
      this.whatsappWebBusy.set(false);
    }
  }

  protected async confirmWhatsAppSent(): Promise<void> {
    const message = this.whatsappPackage();
    if (!message || message.status === 'sent') {
      return;
    }
    const result = await Swal.fire({
      icon: 'question',
      title: 'Confirmar envio',
      text: 'Confirma solo despues de enviar saludo, constancia y cobro en WhatsApp.',
      showCancelButton: true,
      confirmButtonText: 'Si, ya lo envie',
      cancelButtonText: 'Todavia no',
    });
    if (!result.isConfirmed) {
      return;
    }
    this.actionBusy.set(true);
    try {
      const response = await this.api.markWhatsAppSent(message.message_id);
      this.whatsappPackage.set({
        ...message,
        status: 'sent',
        sent_at: response.sent_at ?? new Date().toISOString(),
      });
      await this.refreshAll();
      await this.showToast('Envio de WhatsApp registrado');
    } catch (error) {
      this.errorMessage.set(this.readError(error));
    } finally {
      this.actionBusy.set(false);
    }
  }

  protected openWorkerRestart(): void {
    this.openModal('worker-restart');
  }

  protected closeModal(): void {
    if (this.actionBusy()) {
      return;
    }
    const modal = this.activeModal();
    this.activeModal.set(null);
    this.pendingAction.set(null);
    this.formDirty.set(false);
    this.hydrateSelectedOrderForms();
    if (modal === 'finance-entry') {
      this.clearFinanceForm();
    }
    if (modal === 'whatsapp') {
      this.whatsappPackage.set(null);
      this.whatsappTestRecipient.set('');
      this.whatsappWebResult.set(null);
      this.whatsappManualFallbackOpen.set(false);
    }
    this.restoreFocus();
  }

  protected runNextOrderAction(): void {
    const order = this.selectedOrder();
    const action = this.orderNextAction();
    if (!order || action.disabled) {
      return;
    }
    if (action.key === 'manual-session') {
      void this.openManualSessionNow(order);
    } else if (action.key === 'activate') {
      this.requestOrderAction('activate', 'Activar orden');
    } else if (action.key === 'payment') {
      void this.openEditOrder(order);
    } else if (action.key === 'review') {
      this.openOrderActions(order);
    }
  }

  protected rowPrimaryActionLabel(order: ServiceOrder): string {
    if (order.status === 'ready') {
      return 'Abrir sesión';
    }
    if (order.status === 'paused') {
      return 'Activar';
    }
    if (order.reservation_status === 'confirmed' && order.payment_status !== 'paid') {
      return 'Registrar pago';
    }
    return 'Ver detalle';
  }

  protected runRowPrimaryAction(order: ServiceOrder): void {
    if (order.status === 'ready') {
      void this.openManualSessionNow(order);
      return;
    }
    this.selectOrder(order.order_id);
    if (order.status === 'paused') {
      this.requestOrderAction('activate', 'Activar orden');
    } else if (order.reservation_status === 'confirmed' && order.payment_status !== 'paid') {
      void this.openEditOrder(order);
    }
  }

  protected setQuickPriority(priority: number): void {
    this.orderPriority.set(priority);
    this.requestPriorityUpdate();
  }

  protected priorityExplanation(order: ServiceOrder): string {
    return order.priority >= 100
      ? 'Enfoque prioritario: se atiende antes que la cola normal.'
      : 'Cola normal: mayor numero primero; empate por orden de creacion.';
  }

  protected isClosedOrder(order: ServiceOrder): boolean {
    return ['archived', 'paid'].includes(order.status) || !!order.closed_at;
  }

  protected editField<T>(field: WritableSignal<T>, value: T): void {
    field.set(value);
    this.formDirty.set(true);
  }

  protected setOrderQuickFilter(filter: OrderQuickFilter): void {
    this.orderQuickFilter.set(filter);
  }

  protected setOrderSort(key: OrderSortKey): void {
    if (this.orderSortKey() === key) {
      this.orderSortDirection.set(this.orderSortDirection() === 'asc' ? 'desc' : 'asc');
      return;
    }
    this.orderSortKey.set(key);
    this.orderSortDirection.set(this.defaultOrderSortDirection(key));
  }

  protected chooseOrderSort(key: OrderSortKey): void {
    if (this.orderSortKey() === key) {
      return;
    }
    this.orderSortKey.set(key);
    this.orderSortDirection.set(this.defaultOrderSortDirection(key));
  }

  protected toggleOrderSortDirection(): void {
    this.orderSortDirection.set(this.orderSortDirection() === 'asc' ? 'desc' : 'asc');
  }

  protected orderSortLabel(key: OrderSortKey): string {
    const labels: Record<OrderSortKey, string> = {
      priority: 'Prioridad',
      queue: 'Orden real',
      created_at: 'Creacion',
      updated_at: 'Actualizacion',
      status: 'Estado',
      reservation: 'Reserva',
      payment: 'Pago',
      closure: 'Cierre',
      applicant: 'Solicitante',
    };
    return labels[key];
  }

  protected sortIndicator(key: OrderSortKey): string {
    if (this.orderSortKey() !== key) {
      return '';
    }
    return this.orderSortDirection() === 'asc' ? 'ASC' : 'DESC';
  }

  protected requestContactUpdate(): void {
    if (this.orderDetailLoading()) {
      this.errorMessage.set('Espera a que cargue el detalle protegido de la orden.');
      return;
    }
    const order = this.requireSelectedOrder();
    if (!order) {
      return;
    }
    const payload: ContactUpdatePayload = {
      contact_name: this.optionalText(this.contactName()),
      contact_whatsapp: this.optionalText(this.contactWhatsapp()),
      contact_source: this.optionalText(this.contactSource()),
    };
    if (!payload.contact_name && !payload.contact_whatsapp) {
      this.errorMessage.set('Ingresa nombre o WhatsApp para actualizar contacto.');
      return;
    }
    this.setPendingAction({
      title: 'Actualizar contacto',
      message: `Actualizar contacto de ${order.order_id}.`,
      execute: () => this.api.updateServiceOrderContact(order.order_id, payload),
      onSuccess: () => {
        this.activeModal.set(null);
        this.selectedOrderDetail.set(null);
      },
    });
  }

  protected requestPriorityUpdate(): void {
    const order = this.requireSelectedOrder();
    if (!order) {
      return;
    }
    const priority = Number(this.orderPriority());
    if (!Number.isInteger(priority) || priority < 0) {
      this.errorMessage.set('La prioridad debe ser un numero entero igual o mayor que 0.');
      return;
    }
    const payload: PriorityUpdatePayload = { priority };
    const entersFocusedMode = order.priority < 100 && priority >= 100;
    const leavesFocusedMode = order.priority >= 100 && priority < 100;
    const effect = entersFocusedMode
      ? ' Activara enfoque y desplazara una orden de la cola normal.'
      : leavesFocusedMode
        ? ' La orden volvera a la cola normal.'
        : ' Se aplicara en la siguiente seleccion de la cola.';
    this.setPendingAction({
      title: 'Actualizar prioridad',
      message: `Cambiar prioridad de ${order.order_id} de ${order.priority} a ${priority}.${effect}`,
      execute: () => this.api.updateServiceOrderPriority(order.order_id, payload),
      onSettled: () => this.orderPriority.set(this.selectedOrder()?.priority ?? priority),
    });
  }

  protected requestReservationRestrictionsUpdate(): void {
    const order = this.requireSelectedOrder();
    if (!order) {
      return;
    }
    const minimumHourText = String(this.orderMinimumReservationHour()).trim();
    const minimumHour = minimumHourText === '' ? null : Number(minimumHourText);
    if (minimumHour !== null && (!Number.isInteger(minimumHour) || minimumHour < 0 || minimumHour > 23)) {
      this.errorMessage.set('La hora mínima debe ser un número entero entre 0 y 23.');
      return;
    }
    const payload: ReservationRestrictionsUpdatePayload = {
      minimum_reservation_hour: minimumHour,
      minimum_reservation_date: this.optionalText(this.orderMinimumReservationDate()),
      maximum_reservation_date: this.optionalText(this.orderMaximumReservationDate()),
      allowed_weekdays:
        this.orderAllowedWeekdays().length > 0 ? this.orderAllowedWeekdays() : null,
    };
    if (
      payload.minimum_reservation_date &&
      payload.maximum_reservation_date &&
      payload.maximum_reservation_date < payload.minimum_reservation_date
    ) {
      this.errorMessage.set('La fecha final no puede ser anterior a la fecha inicial.');
      return;
    }
    this.setPendingAction({
      title: 'Actualizar restricciones',
      message: `Guardar las restricciones de reserva de ${order.order_id}. Los campos vacíos quitarán esa restricción.`,
      execute: () => this.api.updateServiceOrderRestrictions(order.order_id, payload),
    });
  }

  protected requestOrderAction(
    action: 'pause' | 'activate' | 'no-charge' | 'done',
    title: string,
  ): void {
    const order = this.requireSelectedOrder();
    if (!order) {
      return;
    }
    if (action === 'activate' && this.hasActiveChildOrders(order)) {
      this.errorMessage.set('No se puede activar una orden padre con subordenes activas.');
      return;
    }
    this.setPendingAction({
      title,
      message: `${title} para ${order.order_id}.`,
      execute: () => this.api.runServiceOrderAction(order.order_id, action),
      onSuccess: () => this.activeModal.set(null),
    });
  }

  protected requestCloseOrder(): void {
    const order = this.requireSelectedOrder();
    if (!order) {
      return;
    }
    const payload: CloseServiceOrderPayload = {
      closure_reason: this.closureReason(),
      closure_note: this.optionalText(this.closureNote()),
    };
    this.setPendingAction({
      title: this.closureReasonLabel(payload.closure_reason),
      message: `${this.closureReasonLabel(payload.closure_reason)} para ${order.order_id}.`,
      execute: () => this.api.closeServiceOrder(order.order_id, payload),
      onSuccess: () => this.activeModal.set(null),
    });
  }

  protected setClosureReason(value: string): void {
    const allowed: ClosureReason[] = [
      'completed_by_us',
      'family_no_charge',
      'client_withdrew',
      'external_slot',
      'duplicate',
      'not_serviceable',
    ];
    const reason = allowed.includes(value as ClosureReason)
      ? (value as ClosureReason)
      : 'client_withdrew';
    this.editField(this.closureReason, reason);
  }

  protected requestMarkPaid(): void {
    const order = this.requireSelectedOrder();
    if (!order) {
      return;
    }
    const payload: PaymentPaidPayload = {
      amount_paid: String(this.paymentAmountPaid() ?? '').trim(),
      amount_agreed: this.optionalText(String(this.paymentAmountAgreed() ?? '')),
    };
    if (!payload.amount_paid) {
      this.errorMessage.set('Ingresa el monto pagado.');
      return;
    }
    this.setPendingAction({
      title: 'Marcar pagado',
      message: `Registrar pago de ${payload.amount_paid} para ${order.order_id}.`,
      execute: () => this.api.markPaymentPaid(order.order_id, payload),
      onSuccess: () => this.activeModal.set(null),
    });
  }

  protected requestCreateOrder(): void {
    const payload: CreateServiceOrderPayload = {
      document_number: this.newDocumentNumber().trim(),
      password: this.newPassword(),
      contact_whatsapp: this.optionalText(this.newContactWhatsapp()),
      contact_name: this.newContactName().trim(),
      contact_source: this.newContactSource(),
      minimum_reservation_date: this.optionalText(this.newMinimumReservationDate()),
      maximum_reservation_date: this.optionalText(this.newMaximumReservationDate()),
      allowed_weekdays: this.newAllowedWeekdays().length > 0 ? this.newAllowedWeekdays() : null,
    };
    if (
      payload.minimum_reservation_date &&
      payload.maximum_reservation_date &&
      payload.maximum_reservation_date < payload.minimum_reservation_date
    ) {
      this.errorMessage.set('La fecha final no puede ser anterior a la fecha inicial.');
      return;
    }
    if (
      !payload.document_number ||
      !payload.password ||
      !payload.contact_name ||
      !payload.contact_source
    ) {
      this.errorMessage.set('Usuario, contrasena, contacto y fuente son obligatorios.');
      return;
    }
    this.setPendingAction({
      title: 'Crear orden nueva',
      message: `Crear orden para documento ${payload.document_number}.`,
      execute: () => this.api.createServiceOrder(payload),
      containsSecret: true,
      onSuccess: () => {
        this.clearCreateOrderForm();
        this.activeModal.set(null);
      },
      onSettled: () => this.newPassword.set(''),
    });
  }

  protected requestRestartWorker(): void {
    this.setPendingAction({
      title: 'Restart worker',
      message: 'Solicitar reinicio controlado del worker.',
      execute: () => this.api.restartWorker(),
      onSuccess: () => this.activeModal.set(null),
    });
  }

  protected requestManualSession(): void {
    const order = this.requireSelectedOrder();
    if (!order) {
      return;
    }
    this.setPendingAction({
      title: 'Abrir sesion manual',
      message: `Abrir navegador visible para ${order.order_id}.`,
      execute: () => this.api.openManualSession(order.order_id),
      onSuccess: (response) => {
        if (response.session_id) {
          this.activeManualSessionIds.add(response.session_id);
        }
        this.activeModal.set(null);
      },
    });
  }

  protected async openManualSessionNow(order: ServiceOrder): Promise<void> {
    if (this.actionBusy()) {
      return;
    }
    this.actionBusy.set(true);
    this.errorMessage.set(null);
    this.successMessage.set(null);
    try {
      const response = await this.api.openManualSession(order.order_id);
      if (response.session_id) {
        this.activeManualSessionIds.add(response.session_id);
      }
      await this.refreshAll();
      await this.showToast('Sesión manual abierta');
    } catch (error) {
      this.errorMessage.set(this.readError(error));
    } finally {
      this.actionBusy.set(false);
    }
  }

  protected async closeManualSession(session: ManualSession): Promise<void> {
    if (this.actionBusy()) {
      return;
    }
    this.actionBusy.set(true);
    this.errorMessage.set(null);
    this.successMessage.set(null);
    try {
      await this.api.closeManualSession(session.session_id);
      this.activeManualSessionIds.delete(session.session_id);
      this.manualSessions.update((sessions) =>
        sessions.filter((item) => item.session_id !== session.session_id),
      );
      await this.showToast('Cierre solicitado');
    } catch (error) {
      this.errorMessage.set(this.readError(error));
    } finally {
      this.actionBusy.set(false);
    }
  }

  protected requestSplitPrograms(): void {
    const order = this.requireSelectedOrder();
    if (!order) {
      return;
    }
    this.setPendingAction({
      title: 'Dividir tramites',
      message: `Crear subordenes pendientes desde ${order.order_id}.`,
      execute: () =>
        this.api.splitServiceOrderPrograms(order.order_id, this.splitKeepParentActive()),
      onSuccess: () => this.activeModal.set(null),
    });
  }

  protected async refreshHealth(): Promise<void> {
    try {
      this.health.set(await this.api.getHealth());
    } catch (error) {
      this.health.set(null);
      this.errorMessage.set(this.readError(error));
    }
  }

  protected async copyDashboardSnapshot(): Promise<void> {
    const snapshot = {
      health: this.health(),
      worker: this.sanitizeWorker(this.worker()),
      current_order: this.currentOrder(),
      service_orders: this.filteredOrders().map((order) => this.sanitizeOrder(order)),
      runs: this.filteredRuns().map((run) => this.sanitizeRun(run)),
      worker_commands: this.workerCommands().map((command) => this.sanitizeWorkerCommand(command)),
    };
    await navigator.clipboard.writeText(JSON.stringify(snapshot, null, 2));
    this.markCopied('snapshot');
  }

  protected phaseLabel(phase: string | null | undefined): string {
    if (!phase) {
      return 'sin fase';
    }
    return phase.replaceAll('_', ' ');
  }

  protected generalObserverActive(): boolean {
    const worker = this.worker();
    return Boolean(
      worker &&
      !worker.current_order_id &&
      worker.phase?.startsWith('monitoring_observer'),
    );
  }

  protected currentWorkLabel(): string {
    if (this.worker()?.current_order_id) {
      return this.worker()!.current_order_id!;
    }
    if (this.generalObserverActive()) {
      return 'Observador general activo';
    }
    return 'Sin orden activa';
  }

  protected orderLabel(order: ServiceOrder | null): string {
    if (!order) {
      return 'Sin orden seleccionada';
    }
    return `${order.order_id} | ${order.applicant_name ?? order.document_number_masked}`;
  }

  protected formatNullable(value: string | number | boolean | null | undefined): string {
    if (value === null || value === undefined || value === '') {
      return 'sin dato';
    }
    return String(value);
  }

  protected paymentLabel(order: ServiceOrder): string {
    if (!order.charge_required) {
      return 'sin cobro';
    }
    return order.payment_status ?? 'sin pago';
  }

  protected paymentAmountLabel(order: ServiceOrder): string {
    if (!order.charge_required) {
      return '';
    }
    return order.amount_paid ?? order.amount_agreed ?? '';
  }

  protected closureReasonLabel(reason: string | null | undefined): string {
    const labels: Record<ClosureReason, string> = {
      completed_by_us: 'Realizado por nosotros',
      family_no_charge: 'Familiar sin cobro',
      client_withdrew: 'Cliente retirado',
      external_slot: 'Cupo por tercero',
      duplicate: 'Duplicado',
      not_serviceable: 'No gestionable',
    };
    if (!reason) {
      return 'sin cierre';
    }
    return labels[reason as ClosureReason] ?? reason.replaceAll('_', ' ');
  }

  protected closureDisplay(order: ServiceOrder): string {
    if (order.closure_reason) {
      return this.closureReasonLabel(order.closure_reason);
    }
    if (order.status === 'archived') {
      return 'Archivado sin razon';
    }
    if (order.status === 'paid') {
      return 'Realizado por nosotros';
    }
    return 'abierto';
  }

  protected manualSessionOrderLabel(session: ManualSession): string {
    const order = this.orders().find((item) => item.order_id === session.order_id);
    if (!order) {
      return session.order_id;
    }
    return `${session.order_id} | ${order.applicant_name ?? order.document_number_masked}`;
  }

  protected hasActiveChildOrders(order: ServiceOrder): boolean {
    return this.orders().some(
      (item) =>
        item.parent_order_id === order.order_id &&
        ['ready', 'paused', 'reserved_payment_pending'].includes(item.status),
    );
  }

  protected statusTone(value: string | boolean | null | undefined): string {
    if (
      value === true ||
      value === 'ok' ||
      value === 'confirmed' ||
      value === 'paid' ||
      value === 'sent' ||
      value === 'ready'
    ) {
      return 'good';
    }
    if (value === false || value === 'degraded' || value === 'error' || value === 'rejected') {
      return 'bad';
    }
    if (
      value === 'outside_hot_window' ||
      value === 'paused' ||
      value === 'pending' ||
      value === 'prepared' ||
      value === 'opening' ||
      value === 'closing' ||
      value === 'family_no_charge'
    ) {
      return 'warn';
    }
    return 'neutral';
  }

  private sanitizeWorker(worker: WorkerStatus | null): Partial<WorkerStatus> | null {
    if (!worker) {
      return null;
    }
    const {
      owner_token: _ownerToken,
      lease_expires_at: _leaseExpiresAt,
      availability_signature: _availabilitySignature,
      ...publicWorker
    } = worker;
    return publicWorker;
  }

  private sanitizeOrder(order: ServiceOrder): ServiceOrder {
    return { ...order };
  }

  private sanitizeRun(run: RunSummary): Partial<RunSummary> {
    const {
      details: _details,
      screenshot_path: _screenshotPath,
      screenshot_paths: _screenshotPaths,
      ...publicRun
    } = run;
    return publicRun;
  }

  private sanitizeWorkerCommand(command: WorkerCommand): WorkerCommand {
    return { ...command };
  }

  private markCopied(label: string): void {
    this.copiedLabel.set(label);
    window.setTimeout(() => {
      if (this.copiedLabel() === label) {
        this.copiedLabel.set(null);
      }
    }, 1600);
  }

  private readError(error: unknown): string {
    return apiErrorMessage(error);
  }

  private async setPendingAction(action: PendingAction): Promise<void> {
    this.errorMessage.set(null);
    this.successMessage.set(null);
    this.captureFocus();
    this.pendingAction.set(action);
    const result = await Swal.fire({
      title: action.title,
      text: action.message,
      icon: action.title.toLowerCase().includes('cerrar') ? 'warning' : 'question',
      showCancelButton: true,
      confirmButtonText: 'Sí, continuar',
      cancelButtonText: 'Cancelar',
      reverseButtons: true,
      focusCancel: true,
      allowOutsideClick: !this.actionBusy(),
    });
    if (!result.isConfirmed) {
      this.pendingAction.set(null);
      action.onSettled?.();
      this.restoreFocus();
      return;
    }
    this.actionBusy.set(true);
    try {
      const response = await action.execute();
      this.successMessage.set(`${action.title}: completado.`);
      this.pendingAction.set(null);
      this.formDirty.set(false);
      action.onSuccess?.(response);
      await this.refreshAll();
      await Swal.fire({
        toast: true,
        position: 'top-end',
        icon: 'success',
        title: 'Cambio guardado',
        showConfirmButton: false,
        timer: 2200,
        timerProgressBar: true,
      });
    } catch (error) {
      const message = this.readError(error);
      this.errorMessage.set(message);
      await Swal.fire({ icon: 'error', title: 'No se pudo completar', text: message });
    } finally {
      action.onSettled?.();
      this.pendingAction.set(null);
      this.actionBusy.set(false);
      this.restoreFocus();
    }
  }

  private async showToast(title: string): Promise<void> {
    await Swal.fire({
      toast: true,
      position: 'top-end',
      icon: 'success',
      title,
      showConfirmButton: false,
      timer: 2200,
      timerProgressBar: true,
    });
  }

  private async loadWhatsAppPackage(
    load: () => Promise<WhatsAppMessagePackage>,
  ): Promise<WhatsAppMessagePackage> {
    this.whatsappPackageLoading.set(true);
    this.errorMessage.set(null);
    try {
      const message = await load();
      this.whatsappPackage.set(message);
      return message;
    } catch (error) {
      this.errorMessage.set(this.readError(error));
      throw error;
    } finally {
      this.whatsappPackageLoading.set(false);
    }
  }

  private openModal(modal: Exclude<ModalKind, null>): void {
    this.captureFocus();
    this.activeModal.set(modal);
    this.focusModal();
  }

  private captureFocus(): void {
    const activeElement = document.activeElement;
    this.lastFocusedElement = activeElement instanceof HTMLElement ? activeElement : null;
  }

  private focusModal(): void {
    window.setTimeout(() => {
      document.querySelector<HTMLElement>('[data-modal-initial-focus]')?.focus();
    });
  }

  private restoreFocus(): void {
    const target = this.lastFocusedElement;
    this.lastFocusedElement = null;
    window.setTimeout(() => {
      if (target?.isConnected) {
        target.focus();
        return;
      }
      document
        .querySelector<HTMLElement>(`[data-order-row="${CSS.escape(this.selectedOrderId())}"]`)
        ?.focus();
    });
  }

  private requireSelectedOrder(): ServiceOrder | null {
    const order = this.selectedOrder();
    if (!order) {
      this.errorMessage.set('Carga y selecciona una orden primero.');
      return null;
    }
    return order;
  }

  private async loadSelectedOrderDetail(orderId: string): Promise<void> {
    this.orderDetailLoading.set(true);
    this.errorMessage.set(null);
    try {
      const detail = await this.api.getServiceOrder(orderId);
      if (this.selectedOrderId() !== detail.order_id) {
        return;
      }
      this.selectedOrderDetail.set(detail);
      this.hydrateSelectedOrderForms(detail);
    } catch (error) {
      this.errorMessage.set(this.readError(error));
    } finally {
      if (this.selectedOrderId() === orderId) {
        this.orderDetailLoading.set(false);
      }
    }
  }

  private async refreshFromTimer(): Promise<void> {
    if (this.autoRefreshPaused()) {
      return;
    }
    await this.refreshAll();
  }

  private keepValidSelection(orders: ServiceOrder[]): void {
    const selected = this.selectedOrderId();
    if (selected && orders.some((order) => order.order_id === selected)) {
      return;
    }
    this.selectedOrderId.set(orders[0]?.order_id ?? '');
  }

  private countOrders(filter: OrderQuickFilter): number {
    return this.orders().filter((order) => this.matchesOrderQuickFilter(order, filter)).length;
  }

  private matchesOrderQuickFilter(order: ServiceOrder, filter: OrderQuickFilter): boolean {
    if (filter === 'all') {
      return true;
    }
    if (filter === 'ready') {
      return order.status === 'ready';
    }
    if (filter === 'payment_pending') {
      return order.payment_status === 'pending';
    }
    if (filter === 'confirmed') {
      return order.reservation_status === 'confirmed';
    }
    if (filter === 'archived') {
      return order.status === 'archived';
    }
    if (filter === 'closed_no_charge') {
      return order.status === 'archived' && !order.charge_required;
    }
    return this.hasReservationRestrictions(order);
  }

  private sortOrders(orders: ServiceOrder[]): ServiceOrder[] {
    const direction = this.orderSortDirection() === 'asc' ? 1 : -1;
    const key = this.orderSortKey();
    return [...orders].sort((left, right) => {
      if (key === 'queue') {
        return this.compareQueueOrder(left, right) * direction;
      }
      const leftValue = this.orderSortValue(left, key);
      const rightValue = this.orderSortValue(right, key);
      const compared =
        typeof leftValue === 'number' && typeof rightValue === 'number'
          ? leftValue - rightValue
          : String(leftValue).localeCompare(String(rightValue), 'es', { numeric: true });
      if (compared !== 0) {
        return compared * direction;
      }
      return left.order_id.localeCompare(right.order_id, 'es', { numeric: true });
    });
  }

  private orderSortValue(order: ServiceOrder, key: OrderSortKey): string | number {
    if (key === 'queue') {
      return order.priority;
    }
    if (key === 'priority') {
      return order.priority;
    }
    if (key === 'created_at') {
      return Date.parse(order.created_at) || 0;
    }
    if (key === 'updated_at') {
      return Date.parse(order.updated_at) || 0;
    }
    if (key === 'status') {
      return order.status;
    }
    if (key === 'reservation') {
      return `${order.reservation_date ?? ''} ${order.reservation_hour ?? ''}`;
    }
    if (key === 'payment') {
      return order.payment_status ?? '';
    }
    if (key === 'closure') {
      return order.closure_reason ?? '';
    }
    return order.applicant_name ?? order.document_number_masked ?? '';
  }

  private compareQueueOrder(left: ServiceOrder, right: ServiceOrder): number {
    const priorityCompare = right.priority - left.priority;
    if (priorityCompare !== 0) {
      return priorityCompare;
    }
    const createdCompare = (Date.parse(left.created_at) || 0) - (Date.parse(right.created_at) || 0);
    if (createdCompare !== 0) {
      return createdCompare;
    }
    return left.order_id.localeCompare(right.order_id, 'es', { numeric: true });
  }

  private defaultOrderSortDirection(key: OrderSortKey): SortDirection {
    return key === 'applicant' || key === 'status' || key === 'queue' ? 'asc' : 'desc';
  }

  private hydrateSelectedOrderForms(detail: ServiceOrderDetail | null = null): void {
    if (this.formDirty()) {
      return;
    }
    const order = this.selectedOrder();
    if (!order) {
      return;
    }
    this.contactName.set(order.contact_name ?? '');
    this.contactWhatsapp.set(detail?.contact_whatsapp ?? '');
    this.contactSource.set(order.contact_source ?? 'whatsapp');
    this.orderPriority.set(order.priority);
    this.orderMinimumReservationHour.set(
      order.minimum_reservation_hour === null ? '' : String(order.minimum_reservation_hour),
    );
    this.orderMinimumReservationDate.set(order.minimum_reservation_date ?? '');
    this.orderMaximumReservationDate.set(order.maximum_reservation_date ?? '');
    this.orderAllowedWeekdays.set([...(order.allowed_weekdays ?? [])]);
    this.paymentAmountPaid.set(order.amount_paid ?? '');
    this.paymentAmountAgreed.set(order.amount_agreed ?? '');
    this.closureReason.set((order.closure_reason as ClosureReason | null) ?? 'client_withdrew');
    this.closureNote.set(order.closure_note ?? '');
  }

  private clearCreateOrderForm(): void {
    this.newDocumentNumber.set('');
    this.newPassword.set('');
    this.newContactName.set('');
    this.newContactWhatsapp.set('');
    this.newContactSource.set('');
    this.newMinimumReservationDate.set('');
    this.newMaximumReservationDate.set('');
    this.newAllowedWeekdays.set([]);
  }

  private financeFormPayload(): FinanceEntryPayload | null {
    const amountOriginal = String(this.financeAmountOriginal() ?? '').trim();
    const exchangeRate = String(this.financeExchangeRatePen() ?? '').trim();
    const quantity = String(this.financeQuantity() ?? '').trim();
    const amount = Number(amountOriginal);
    if (!this.financeOccurredOn() || !this.financeDescription().trim()) {
      this.errorMessage.set('Fecha y descripcion son obligatorias.');
      return null;
    }
    if (!Number.isFinite(amount) || amount <= 0) {
      this.errorMessage.set('El importe debe ser mayor que cero.');
      return null;
    }
    if (
      this.financeCurrency() !== 'PEN' &&
      exchangeRate &&
      (!Number.isFinite(Number(exchangeRate)) || Number(exchangeRate) <= 0)
    ) {
      this.errorMessage.set('El tipo de cambio debe ser mayor que cero.');
      return null;
    }
    return {
      occurred_on: this.financeOccurredOn(),
      entry_kind: this.financeEntryKind(),
      category_code: this.financeCategoryCode(),
      vendor: this.optionalText(this.financeVendor()),
      description: this.financeDescription().trim(),
      amount_original: amountOriginal,
      currency: this.financeCurrency().trim().toUpperCase(),
      exchange_rate_pen:
        this.financeCurrency() === 'PEN' ? null : this.optionalText(exchangeRate),
      quantity: this.optionalText(quantity),
      unit: this.optionalText(this.financeUnit()),
      channel: this.optionalText(this.financeChannel()),
      campaign: this.optionalText(this.financeCampaign()),
      order_id: this.optionalText(this.financeOrderId()),
      evidence_reference: this.optionalText(this.financeEvidenceReference()),
      notes: this.optionalText(this.financeNotes()),
      data_quality: this.financeDataQuality(),
    };
  }

  private clearFinanceForm(): void {
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
    this.formDirty.set(false);
  }

  private formatClock(date: Date): string {
    return date.toLocaleTimeString('es-PE', {
      timeZone: 'America/Lima',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hourCycle: 'h23',
    });
  }

  private capitalize(value: string): string {
    return value ? `${value.charAt(0).toUpperCase()}${value.slice(1)}` : value;
  }

  private optionalText(value: string): string | null {
    const trimmed = value.trim();
    return trimmed || null;
  }

  private closeTrackedManualSessionsWithBeacon(): void {
    if (!this.activeManualSessionIds.size) {
      return;
    }
    for (const sessionId of this.activeManualSessionIds) {
      const body = JSON.stringify({ session_id: sessionId });
      const sent = navigator.sendBeacon?.(
        '/api/v1/manual-session/close',
        new Blob([body], { type: 'application/json' }),
      );
      if (!sent) {
        void this.api.closeManualSession(sessionId).catch(() => undefined);
      }
    }
    this.activeManualSessionIds.clear();
  }
}
