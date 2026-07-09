import { Component, computed, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  AppointmentApiService,
  HealthPayload,
  RunSummary,
  ServiceOrder,
  WorkerStatus,
  apiErrorMessage,
} from './appointment-api.service';

type LoadState = 'idle' | 'loading' | 'ready' | 'error';

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
  protected readonly loadState = signal<LoadState>('idle');
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly copiedLabel = signal<string | null>(null);

  protected readonly hasToken = computed(() => this.apiToken().trim().length > 0);
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
      this.worker.set(null);
      this.orders.set([]);
      this.runs.set([]);
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
      const [worker, orders, runs] = await Promise.all([
        this.api.getWorker(token),
        this.api.getServiceOrders(token),
        this.api.getRuns(token),
      ]);
      this.worker.set(worker);
      this.orders.set(orders);
      this.runs.set(runs);
      this.loadState.set('ready');
    } catch (error) {
      this.loadState.set('error');
      this.errorMessage.set(this.readError(error));
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
}
