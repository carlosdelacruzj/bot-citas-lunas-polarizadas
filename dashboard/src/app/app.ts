import { Component, computed, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  ApiActionResponse,
  AppointmentApiService,
  ContactUpdatePayload,
  CreateServiceOrderPayload,
  HealthPayload,
  PaymentPaidPayload,
  RunSummary,
  ServiceOrder,
  WorkerCommand,
  WorkerStatus,
  apiErrorMessage,
} from './appointment-api.service';

type LoadState = 'idle' | 'loading' | 'ready' | 'error';
type PendingAction = {
  title: string;
  message: string;
  execute: () => Promise<ApiActionResponse>;
};

@Component({
  selector: 'app-root',
  imports: [FormsModule],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  private readonly api = inject(AppointmentApiService);

  protected readonly apiToken = signal('');
  protected readonly orderFilter = signal('');
  protected readonly runStatusFilter = signal('');
  protected readonly health = signal<HealthPayload | null>(null);
  protected readonly worker = signal<WorkerStatus | null>(null);
  protected readonly orders = signal<ServiceOrder[]>([]);
  protected readonly runs = signal<RunSummary[]>([]);
  protected readonly workerCommands = signal<WorkerCommand[]>([]);
  protected readonly loadState = signal<LoadState>('idle');
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly successMessage = signal<string | null>(null);
  protected readonly copiedLabel = signal<string | null>(null);
  protected readonly selectedOrderId = signal('');
  protected readonly contactName = signal('');
  protected readonly contactWhatsapp = signal('');
  protected readonly contactSource = signal('whatsapp');
  protected readonly paymentAmountPaid = signal('');
  protected readonly paymentAmountAgreed = signal('');
  protected readonly newDocumentNumber = signal('');
  protected readonly newPassword = signal('');
  protected readonly newApplicantName = signal('');
  protected readonly newContactName = signal('');
  protected readonly newContactWhatsapp = signal('');
  protected readonly newPriority = signal(0);
  protected readonly newChargeRequired = signal(true);
  protected readonly newParentOrderId = signal('');
  protected readonly newProgramExpediente = signal('');
  protected readonly newProgramPlate = signal('');
  protected readonly newMinimumReservationHour = signal('');
  protected readonly newMinimumReservationDate = signal('');
  protected readonly newAllowedWeekdays = signal('');
  protected readonly splitKeepParentActive = signal(false);
  protected readonly actionBusy = signal(false);
  protected readonly pendingAction = signal<PendingAction | null>(null);

  protected readonly hasToken = computed(() => this.apiToken().trim().length > 0);
  protected readonly selectedOrder = computed(() => {
    const selected = this.selectedOrderId();
    return this.orders().find((order) => order.order_id === selected) ?? this.orders()[0] ?? null;
  });
  protected readonly currentOrder = computed(() => {
    const currentOrderId = this.worker()?.current_order_id;
    return this.orders().find((order) => order.order_id === currentOrderId) ?? null;
  });
  protected readonly filteredOrders = computed(() => {
    const filter = this.orderFilter().trim().toLowerCase();
    if (!filter) {
      return this.orders();
    }
    return this.orders().filter((order) =>
      [
        order.order_id,
        order.applicant_name,
        order.document_number_masked,
        order.contact_name,
        order.status,
        order.reservation_status,
        order.payment_status,
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(filter)),
    );
  });
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

  constructor() {
    void this.refreshHealth();

    effect(() => {
      this.apiToken();
      this.errorMessage.set(null);
      this.successMessage.set(null);
      this.worker.set(null);
      this.orders.set([]);
      this.runs.set([]);
      this.workerCommands.set([]);
      this.loadState.set('idle');
    });
  }

  protected async refreshAll(): Promise<void> {
    await this.refreshHealth();
    if (!this.hasToken()) {
      return;
    }

    this.loadState.set('loading');
    this.errorMessage.set(null);

    try {
      const token = this.apiToken().trim();
      const [worker, orders, runs, workerCommands] = await Promise.all([
        this.api.getWorker(token),
        this.api.getServiceOrders(token),
        this.api.getRuns(token),
        this.api.getWorkerCommands(token),
      ]);
      this.worker.set(worker);
      this.orders.set(orders);
      this.runs.set(runs);
      this.workerCommands.set(workerCommands);
      if (!this.selectedOrderId() && orders.length > 0) {
        this.selectedOrderId.set(orders[0].order_id);
      }
      this.loadState.set('ready');
    } catch (error) {
      this.loadState.set('error');
      this.errorMessage.set(this.readError(error));
    }
  }

  protected requestContactUpdate(): void {
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
      execute: () => this.api.updateServiceOrderContact(this.requiredToken(), order.order_id, payload),
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
    this.setPendingAction({
      title,
      message: `${title} para ${order.order_id}.`,
      execute: () => this.api.runServiceOrderAction(this.requiredToken(), order.order_id, action),
    });
  }

  protected requestMarkPaid(): void {
    const order = this.requireSelectedOrder();
    if (!order) {
      return;
    }
    const payload: PaymentPaidPayload = {
      amount_paid: this.paymentAmountPaid().trim(),
      amount_agreed: this.optionalText(this.paymentAmountAgreed()),
    };
    if (!payload.amount_paid) {
      this.errorMessage.set('Ingresa el monto pagado.');
      return;
    }
    this.setPendingAction({
      title: 'Marcar pagado',
      message: `Registrar pago de ${payload.amount_paid} para ${order.order_id}.`,
      execute: () => this.api.markPaymentPaid(this.requiredToken(), order.order_id, payload),
    });
  }

  protected requestCreateOrder(): void {
    const payload: CreateServiceOrderPayload = {
      document_number: this.newDocumentNumber().trim(),
      password: this.newPassword(),
      priority: Number(this.newPriority()) || 0,
      contact_whatsapp: this.optionalText(this.newContactWhatsapp()),
      contact_name: this.optionalText(this.newContactName()),
      contact_source: 'whatsapp',
      applicant_name: this.optionalText(this.newApplicantName()),
      charge_required: this.newChargeRequired(),
      minimum_reservation_hour: this.optionalNumber(this.newMinimumReservationHour()),
      minimum_reservation_date: this.optionalText(this.newMinimumReservationDate()),
      allowed_weekdays: this.optionalWeekdays(this.newAllowedWeekdays()),
      parent_order_id: this.optionalText(this.newParentOrderId()),
      program_expediente: this.optionalText(this.newProgramExpediente()),
      program_plate: this.optionalText(this.newProgramPlate()),
    };
    if (!payload.document_number || !payload.password) {
      this.errorMessage.set('Documento y password son obligatorios para crear orden.');
      return;
    }
    this.setPendingAction({
      title: 'Crear orden nueva',
      message: `Crear orden para documento ${payload.document_number}.`,
      execute: () => this.api.createServiceOrder(this.requiredToken(), payload),
    });
  }

  protected requestRestartWorker(): void {
    this.setPendingAction({
      title: 'Restart worker',
      message: 'Solicitar reinicio controlado del worker.',
      execute: () => this.api.restartWorker(this.requiredToken()),
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
      execute: () => this.api.openManualSession(this.requiredToken(), order.order_id),
    });
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
          this.requiredToken(),
          order.order_id,
          this.splitKeepParentActive(),
        ),
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
      await this.refreshAll();
    } catch (error) {
      this.errorMessage.set(this.readError(error));
    } finally {
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

  protected statusTone(value: string | boolean | null | undefined): string {
    if (value === true || value === 'ok' || value === 'confirmed' || value === 'paid') {
      return 'good';
    }
    if (value === false || value === 'degraded' || value === 'error' || value === 'rejected') {
      return 'bad';
    }
    if (value === 'outside_hot_window' || value === 'paused' || value === 'pending') {
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
    if (!this.hasToken()) {
      this.errorMessage.set('Ingresa el API token antes de ejecutar acciones.');
      return;
    }
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

  private requiredToken(): string {
    const token = this.apiToken().trim();
    if (!token) {
      throw new Error('API token requerido.');
    }
    return token;
  }

  private optionalText(value: string): string | null {
    const trimmed = value.trim();
    return trimmed || null;
  }

  private optionalNumber(value: string): number | null {
    const trimmed = value.trim();
    if (!trimmed) {
      return null;
    }
    return Number(trimmed);
  }

  private optionalWeekdays(value: string): number[] | null {
    const trimmed = value.trim();
    if (!trimmed) {
      return null;
    }
    return trimmed
      .split(',')
      .map((item) => Number(item.trim()))
      .filter((item) => Number.isInteger(item));
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
}
