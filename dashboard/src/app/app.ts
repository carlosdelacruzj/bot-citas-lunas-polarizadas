import { Component, HostListener, OnDestroy, WritableSignal, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  ApiActionResponse,
  AppointmentApiService,
  CloseServiceOrderPayload,
  ContactUpdatePayload,
  CreateServiceOrderPayload,
  HealthPayload,
  ManualSession,
  PaymentPaidPayload,
  RunSummary,
  ServiceOrder,
  ServiceOrderDetail,
  WorkerCommand,
  WorkerStatus,
  apiErrorMessage,
} from './appointment-api.service';

type LoadState = 'idle' | 'loading' | 'ready' | 'error';
type ViewKey = 'summary' | 'orders' | 'runs';
type ModalKind = 'edit-order' | 'order-actions' | 'create-order' | 'worker-restart' | null;
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

const AUTO_REFRESH_INTERVAL_MS = 15_000;

@Component({
  selector: 'app-root',
  imports: [FormsModule],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App implements OnDestroy {
  private readonly api = inject(AppointmentApiService);
  private readonly autoRefreshTimer = window.setInterval(() => {
    void this.refreshFromTimer();
  }, AUTO_REFRESH_INTERVAL_MS);
  private readonly activeManualSessionIds = new Set<string>();

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
  protected readonly workerCommands = signal<WorkerCommand[]>([]);
  protected readonly manualSessions = signal<ManualSession[]>([]);
  protected readonly loadState = signal<LoadState>('idle');
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly successMessage = signal<string | null>(null);
  protected readonly copiedLabel = signal<string | null>(null);
  protected readonly selectedOrderId = signal('');
  protected readonly selectedOrderDetail = signal<ServiceOrderDetail | null>(null);
  protected readonly orderDetailLoading = signal(false);
  protected readonly contactName = signal('');
  protected readonly contactWhatsapp = signal('');
  protected readonly contactSource = signal('whatsapp');
  protected readonly paymentAmountPaid = signal('');
  protected readonly paymentAmountAgreed = signal('');
  protected readonly newDocumentNumber = signal('');
  protected readonly newPassword = signal('');
  protected readonly newContactName = signal('');
  protected readonly newContactWhatsapp = signal('');
  protected readonly newContactSource = signal('');
  protected readonly newMinimumReservationDate = signal('');
  protected readonly newAllowedWeekdays = signal<number[]>([]);
  protected readonly splitKeepParentActive = signal(false);
  protected readonly closureReason = signal<ClosureReason>('client_withdrew');
  protected readonly closureNote = signal('');
  protected readonly actionBusy = signal(false);
  protected readonly pendingAction = signal<PendingAction | null>(null);

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
    Array.from(new Set(this.runs().map((run) => run.status).filter(Boolean))).sort(),
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
  protected readonly selectedOrderWhatsappPlaceholder = computed(
    () => this.selectedOrder()?.contact_whatsapp_masked ?? 'sin WhatsApp registrado',
  );
  protected readonly autoRefreshPaused = computed(
    () => !this.autoRefreshEnabled() || this.formDirty() || this.actionBusy() || !!this.pendingAction(),
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

  protected async refreshAll(): Promise<void> {
    await this.refreshHealth();
    this.loadState.set('loading');
    this.errorMessage.set(null);

    try {
        const [worker, orders, runs, workerCommands, manualSessions] = await Promise.all([
          this.api.getWorker(),
          this.api.getServiceOrders(),
          this.api.getRuns(),
          this.api.getWorkerCommands(),
          this.api.getManualSessions(),
        ]);
        this.worker.set(worker);
        this.orders.set(orders);
        this.runs.set(runs);
        this.workerCommands.set(workerCommands);
        this.manualSessions.set(manualSessions);
      this.keepValidSelection(orders);
      this.hydrateSelectedOrderForms();
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

  protected selectOrder(orderId: string): void {
    this.selectedOrderId.set(orderId);
    this.selectedOrderDetail.set(null);
    this.formDirty.set(false);
    this.hydrateSelectedOrderForms();
  }

  protected async openEditOrder(order: ServiceOrder): Promise<void> {
    this.selectOrder(order.order_id);
    this.activeModal.set('edit-order');
    this.orderDetailLoading.set(true);
    this.errorMessage.set(null);
    try {
      const detail = await this.api.getServiceOrder(order.order_id);
      if (this.selectedOrderId() !== detail.order_id) {
        return;
      }
      this.selectedOrderDetail.set(detail);
      this.hydrateSelectedOrderForms(detail);
    } catch (error) {
      this.errorMessage.set(this.readError(error));
    } finally {
      this.orderDetailLoading.set(false);
    }
  }

  protected openOrderActions(order: ServiceOrder): void {
    this.selectOrder(order.order_id);
    this.activeModal.set('order-actions');
  }

  protected openCreateOrder(): void {
    this.activeModal.set('create-order');
  }

  protected openWorkerRestart(): void {
    this.activeModal.set('worker-restart');
  }

  protected closeModal(): void {
    if (this.actionBusy()) {
      return;
    }
    this.activeModal.set(null);
    this.selectedOrderDetail.set(null);
    this.pendingAction.set(null);
    this.formDirty.set(false);
    this.hydrateSelectedOrderForms();
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
      allowed_weekdays:
        this.newAllowedWeekdays().length > 0 ? this.newAllowedWeekdays() : null,
    };
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
      this.successMessage.set(this.actionResponseMessage(response));
      await this.refreshAll();
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
      const response = await this.api.closeManualSession(session.session_id);
      this.activeManualSessionIds.delete(session.session_id);
      this.successMessage.set(this.actionResponseMessage(response));
      await this.refreshAll();
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
        this.api.splitServiceOrderPrograms(
          order.order_id,
          this.splitKeepParentActive(),
        ),
      onSuccess: () => this.activeModal.set(null),
    });
  }

  protected cancelPendingAction(): void {
    this.pendingAction.set(null);
  }

  protected async confirmPendingAction(): Promise<void> {
    const action = this.pendingAction();
    if (!action || this.actionBusy()) {
      return;
    }
    this.actionBusy.set(true);
    this.errorMessage.set(null);
    this.successMessage.set(null);
    try {
      const response = await action.execute();
      this.successMessage.set(this.actionResponseMessage(response));
      this.pendingAction.set(null);
      this.formDirty.set(false);
      action.onSuccess?.(response);
      await this.refreshAll();
    } catch (error) {
      this.errorMessage.set(this.readError(error));
    } finally {
      action.onSettled?.();
      if (action.containsSecret) {
        this.pendingAction.set(null);
      }
      this.actionBusy.set(false);
    }
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

  protected async copyOrder(order: ServiceOrder): Promise<void> {
    await navigator.clipboard.writeText(JSON.stringify(this.sanitizeOrder(order), null, 2));
    this.markCopied(order.order_id);
  }

  protected phaseLabel(phase: string | null | undefined): string {
    if (!phase) {
      return 'sin fase';
    }
    return phase.replaceAll('_', ' ');
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

  private setPendingAction(action: PendingAction): void {
    this.errorMessage.set(null);
    this.successMessage.set(null);
    this.pendingAction.set(action);
  }

  private requireSelectedOrder(): ServiceOrder | null {
    const order = this.selectedOrder();
    if (!order) {
      this.errorMessage.set('Carga y selecciona una orden primero.');
      return null;
    }
    return order;
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
    return Boolean(
      order.minimum_reservation_date ||
        order.minimum_reservation_hour !== null ||
        (order.allowed_weekdays && order.allowed_weekdays.length > 0),
    );
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
    this.newAllowedWeekdays.set([]);
  }

  private formatClock(date: Date): string {
    return date.toLocaleTimeString('es-PE', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  }

  private optionalText(value: string): string | null {
    const trimmed = value.trim();
    return trimmed || null;
  }

  private actionResponseMessage(response: ApiActionResponse): string {
    const parts = [response.status];
    if (response.command) {
      parts.push(response.command);
    }
    if (response.command_id) {
      parts.push(response.command_id);
    }
    if (response.session_id) {
      parts.push(response.session_id);
    }
    if (response.order_id) {
      parts.push(response.order_id);
    }
    return parts.join(' | ');
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
