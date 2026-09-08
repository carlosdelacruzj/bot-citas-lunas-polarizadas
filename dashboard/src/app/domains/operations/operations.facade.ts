import { Injectable, Injector, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import {
  AppointmentApiService,
  HealthPayload,
  OperatorInboxPayload,
  OperatorInboxTask,
  OpportunityBurst,
  OpportunityControl,
  OpportunityControlAction,
  OpportunityControlTarget,
  RunDetail,
  RunSummary,
  ServiceOrder,
  ServiceOrderDetail,
  WorkerCommand,
  WorkerStatus,
} from '../../appointment-api.service';
import {
  DashboardSnapshotHealth,
  DashboardSnapshotOrder,
  DashboardSnapshotRun,
  DashboardSnapshotWorker,
  DashboardSnapshotWorkerCommand,
  InboxOrderTask,
  LoadState,
  StatusTone,
  normalizeDashboardText,
} from '../../dashboard-domain.contracts';
import {
  DASHBOARD_OPERATIONS_CAPTCHAS,
  DASHBOARD_OPERATIONS_FINANCE,
  DASHBOARD_OPERATIONS_FOLLOWUPS,
  DASHBOARD_OPERATIONS_MESSAGES,
  DASHBOARD_OPERATIONS_NAVIGATION,
  DASHBOARD_OPERATIONS_ORDERS,
  DASHBOARD_OPERATIONS_PRESENTATION,
  DASHBOARD_OPERATIONS_UI,
} from '../../dashboard-domain.ports';
import { OrdersListFacade } from '../../domains/orders/orders-list.facade';
import { RequestScope } from '../../request-cancellation';

@Injectable()
export class OperationsFacade {
  private readonly injector = inject(Injector);
  private readonly api = inject(AppointmentApiService);
  private readonly router = inject(Router);
  public readonly orderList = inject(OrdersListFacade);
  public readonly runStatusFilter = signal('');

  public readonly health = signal<HealthPayload | null>(null);

  public readonly worker = signal<WorkerStatus | null>(null);

  public readonly opportunityControl = signal<OpportunityControl | null>(null);

  public readonly opportunityBursts = signal<OpportunityBurst[]>([]);

  public readonly operatorInbox = signal<OperatorInboxPayload | null>(null);

  public readonly runs = signal<RunSummary[]>([]);

  public readonly selectedRunId = signal('');

  public readonly selectedRunDetail = signal<RunDetail | null>(null);

  public readonly runDetailState = signal<LoadState>('idle');

  public readonly runDetailError = signal<string | null>(null);

  public readonly workerCommands = signal<WorkerCommand[]>([]);

  public readonly pendingWorkerControl = computed(
    () =>
      this.workerCommands().find(
        (command) =>
          (command.command === 'pause' || command.command === 'resume') &&
          (command.status === 'pending' || command.status === 'processing'),
      ) ?? null,
  );

  public readonly releaseSafeBackoffsOnRestart = signal(false);

  public readonly latestOpportunityBurst = computed(
    () => this.opportunityBursts()[0] ?? null,
  );

  public readonly currentOrder = computed(() => {
    const currentOrderId = this.worker()?.current_order_id;
    return this.orderList.orders().find((order) => order.order_id === currentOrderId) ?? null;
  });

  public readonly filteredRuns = computed(() => {
    const status = this.runStatusFilter().trim();
    if (!status) {
      return this.runs();
    }
    return this.runs().filter((run) => run.status === status);
  });

  public readonly runStatuses = computed(() =>
    Array.from(
      new Set(
        this.runs()
          .map((run) => run.status)
          .filter(Boolean),
      ),
    ).sort(),
  );

  public readonly inboxOrderTasks = computed<InboxOrderTask[]>(() => {
    const icons: Record<OperatorInboxTask['kind'], string> = {
      preflight: '!',
      paused: 'II',
      contact: '@',
      whatsapp: 'WA',
      payment: 'S/',
      followup: 'PDF',
      review: '!',
    };
    return (this.operatorInbox()?.items ?? []).map((task) => ({
      key: task.key,
      kind: task.kind,
      action: task.action,
      orderId: task.order_id,
      applicantName: task.applicant_name,
      documentNumberMasked: task.document_number_masked,
      title: task.title,
      description: task.description,
      label: task.label,
      actionLabel: task.action_label,
      icon: icons[task.kind],
      tone: task.tone,
      updatedAt: task.updated_at,
    }));
  });

  public readonly inboxAccessCount = computed(
    () => this.inboxOrderTasks().filter((task) => task.kind === 'preflight').length,
  );

  public readonly inboxPaymentCount = computed(
    () => this.inboxOrderTasks().filter((task) => task.kind === 'payment').length,
  );

  public readonly inboxPausedCount = computed(
    () => this.inboxOrderTasks().filter((task) => task.kind === 'paused').length,
  );

  public readonly inboxMessageCount = computed(
    () =>
      this.inboxOrderTasks().filter((task) =>
        ['contact', 'whatsapp', 'followup', 'review'].includes(task.kind),
      ).length,
  );

  public readonly inboxPendingTotal = computed(
    () => this.inboxOrderTasks().length,
  );

  public readonly failedRuns = computed(
    () => this.runs().filter((run) => this.presentation.statusTone(run.status) === 'bad').length,
  );

  public readonly selectedRun = computed(() => this.selectedRunDetail());

  public openInboxCaptchaReview(): void {
    this.captchas.showCaptchaWorkspace('review');
    void this.router.navigate(['/captchas'], { queryParams: { mode: 'review' } });
  }

  public openInboxOrder(orderId: string): void {
    void this.router.navigate(['/ordenes', orderId]);
  }

  public async runInboxOrderTask(task: InboxOrderTask): Promise<void> {
    if (task.action === 'view_order') {
      this.openInboxOrder(task.orderId);
      return;
    }
    const order = await this.loadInboxTaskOrder(task.orderId);
    if (!order) {
      return;
    }
    if (task.action === 'correct_credentials') {
      await this.orders.openEditOrder(order, 'credentials');
      return;
    }
    if (task.action === 'revalidate') {
      this.orders.selectOrder(order.order_id, false);
      this.orders.requestOrderValidation(order);
      return;
    }
    if (task.action === 'edit_contact') {
      await this.orders.openEditOrder(order, 'contact');
      return;
    }
    if (task.action === 'prepare_whatsapp') {
      this.orders.selectOrder(order.order_id, false);
      await this.messages.openOrderWhatsApp(order);
      return;
    }
    if (task.action === 'register_payment') {
      await this.finance.openPayment(order);
      return;
    }
    if (
      task.action === 'review_whatsapp' ||
      task.action === 'review_post_payment_whatsapp'
    ) {
      await this.messages.openWhatsAppReview(order);
    }
  }

  private async loadInboxTaskOrder(orderId: string): Promise<ServiceOrderDetail | null> {
    this.ui.actionBusy.set(true);
    this.ui.errorMessage.set(null);
    try {
      const order = await this.api.getServiceOrder(orderId);
      this.orderList.includeOrder(order);
      return order;
    } catch (error) {
      this.ui.errorMessage.set(this.presentation.readError(error));
      return null;
    } finally {
      this.ui.actionBusy.set(false);
    }
  }

  public openOrderFromSummary(orderId: string): void {
    void this.router.navigate(['/ordenes', orderId]);
  }

  public openPaymentFromSummary(orderId: string): void {
    const order = this.orderList.orders().find((item) => item.order_id === orderId);
    if (!order) {
      this.openOrderFromSummary(orderId);
      return;
    }
    void this.router.navigate(['/ordenes', orderId]);
    void this.finance.openPayment(order);
  }

  public async selectRun(runId: string, updateRoute = true): Promise<void> {
    this.selectedRunId.set(runId);
    this.selectedRunDetail.set(null);
    this.runDetailError.set(null);
    this.runDetailState.set('loading');
    if (updateRoute && this.navigation.activeView() === 'runs') {
      void this.router.navigate(['/actividad', runId]);
    }
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
      this.runDetailError.set(this.presentation.readError(error));
    }
  }

  public closeRunDetail(updateRoute = true): void {
    this.selectedRunId.set('');
    this.selectedRunDetail.set(null);
    this.runDetailError.set(null);
    this.runDetailState.set('idle');
    if (updateRoute && this.navigation.activeView() === 'runs') {
      void this.router.navigateByUrl('/actividad');
    }
  }

  public runResultLabel(run: RunSummary): string {
    if (run.reservation_confirmed) {
      return 'Reserva confirmada';
    }
    if (run.reservation_attempted) {
      return 'Intento sin confirmacion';
    }
    return 'Sin intento de reserva';
  }

  public runEvidencePaths(run: RunDetail): string[] {
    if (run.screenshot_paths?.length) {
      return run.screenshot_paths;
    }
    return run.screenshot_path ? [run.screenshot_path] : [];
  }

  public showPendingPayments(): void {
    this.orderList.setOrderQuickFilter('payment_pending');
    void this.router.navigateByUrl('/ordenes');
  }

  public openWorkerRestart(): void {
    this.releaseSafeBackoffsOnRestart.set(false);
    this.ui.openModal('worker-restart');
  }

  public opportunityMode(target: OpportunityControlTarget) {
    return this.opportunityControl()?.[target] ?? null;
  }

  public opportunityMaxSessions(): number {
    const configured = this.opportunityControl()?.max_sessions;
    return Number.isInteger(configured) && Number(configured) >= 2
      ? Number(configured)
      : 3;
  }

  public opportunityModeLabel(mode: string | null | undefined): string {
    const normalized = normalizeDashboardText(mode);
    if (normalized === 'enabled' || normalized === 'active') {
      return 'Activo';
    }
    if (normalized === 'draining') {
      return 'Drenando';
    }
    if (normalized === 'disabled' || normalized === 'inactive') {
      return 'Desactivado';
    }
    if (normalized === 'running') {
      return 'En curso';
    }
    if (normalized === 'completed') {
      return 'Finalizada';
    }
    if (normalized === 'failed') {
      return 'Fallida';
    }
    return mode ? mode.replaceAll('_', ' ') : 'Sin confirmar';
  }

  public opportunityReasonLabel(reason: string | null | undefined): string {
    if (!reason) {
      return 'Sin motivo informado';
    }
    const normalized = normalizeDashboardText(reason);
    if (
      normalized.includes('portal_defense') ||
      normalized.includes('403') ||
      normalized.includes('429')
    ) {
      return 'Defensa del portal detectada';
    }
    if (normalized.includes('reservation_unconfirmed')) {
      return 'La reserva no pudo confirmarse';
    }
    return reason.replaceAll('_', ' ');
  }

  public opportunityModeTone(mode: string | null | undefined): StatusTone {
    const normalized = normalizeDashboardText(mode);
    if (normalized === 'enabled' || normalized === 'active') {
      return 'good';
    }
    if (normalized === 'draining') {
      return 'warn';
    }
    if (normalized === 'disabled' || normalized === 'inactive') {
      return 'neutral';
    }
    return 'bad';
  }

  public opportunityBreakerOpen(): boolean {
    return normalizeDashboardText(this.opportunityControl()?.breaker.state) === 'open';
  }

  public opportunityControlLabel(): string {
    const control = this.opportunityControl();
    if (!control) {
      return 'Estado sin confirmar';
    }
    if (this.opportunityBreakerOpen()) {
      return 'Protección activa';
    }
    if (control.pending_application) {
      return 'Pendiente de aplicar';
    }
    const modes = [control.obs006.effective_mode, control.obs007.effective_mode].map((mode) =>
      normalizeDashboardText(mode),
    );
    if (modes.includes('draining')) {
      return 'Drenando';
    }
    if (modes.every((mode) => mode === 'enabled' || mode === 'active')) {
      return 'Activo';
    }
    if (modes.every((mode) => mode === 'disabled' || mode === 'inactive')) {
      return 'Desactivado';
    }
    return 'Configuración parcial';
  }

  public opportunityControlTone(): StatusTone {
    if (!this.opportunityControl()) {
      return 'bad';
    }
    if (this.opportunityBreakerOpen() || this.opportunityControl()?.pending_application) {
      return 'warn';
    }
    const modes = [
      this.opportunityControl()!.obs006.effective_mode,
      this.opportunityControl()!.obs007.effective_mode,
    ];
    return modes.some((mode) => normalizeDashboardText(mode) === 'draining')
      ? 'warn'
      : modes.every((mode) => ['enabled', 'active'].includes(normalizeDashboardText(mode)))
        ? 'good'
        : 'neutral';
  }

  public opportunityActionLabel(target: OpportunityControlTarget): string {
    const mode = normalizeDashboardText(this.opportunityMode(target)?.effective_mode);
    if (mode === 'disabled' || mode === 'inactive') {
      return 'Activar';
    }
    return this.shouldDrainOpportunity(target) ? 'Drenar' : 'Desactivar';
  }

  public opportunityActionDisabled(target: OpportunityControlTarget): boolean {
    const control = this.opportunityControl();
    if (!control || this.ui.actionBusy() || control.pending_application) {
      return true;
    }
    const activates = ['disabled', 'inactive'].includes(
      normalizeDashboardText(control[target].effective_mode),
    );
    return activates && this.opportunityBreakerOpen();
  }

  public requestOpportunityContextAction(target: OpportunityControlTarget): void {
    const mode = normalizeDashboardText(this.opportunityMode(target)?.effective_mode);
    const action: OpportunityControlAction =
      mode === 'disabled' || mode === 'inactive'
        ? 'activate'
        : this.shouldDrainOpportunity(target)
          ? 'drain'
          : 'deactivate';
    this.requestOpportunityAction(target, action);
  }

  public requestResetOpportunityBreaker(): void {
    this.requestOpportunityAction('obs006', 'reset_breaker');
  }

  private shouldDrainOpportunity(target: OpportunityControlTarget): boolean {
    const control = this.opportunityControl();
    if (target !== 'obs006') {
      return false;
    }
    return Boolean(
      normalizeDashboardText(control?.[target].effective_mode) === 'draining' ||
      control?.active_burst,
    );
  }

  private requestOpportunityAction(
    target: OpportunityControlTarget,
    action: OpportunityControlAction,
  ): void {
    const control = this.opportunityControl();
    if (!control || this.ui.actionBusy()) {
      return;
    }
    const targetLabel = target === 'obs006'
      ? 'ráfagas de oportunidad'
      : 'reobservación de cupo perdido';
    const copy: Record<OpportunityControlAction, { title: string; message: string }> = {
      activate: {
        title: `Activar ${targetLabel}`,
        message: `Se aplicará a nuevas detecciones. El máximo seguirá siendo ${this.opportunityMaxSessions()} sesiones y no cambiarán los intervalos ni CAPTCHA.`,
      },
      deactivate: {
        title: `Desactivar ${targetLabel}`,
        message:
          'Se desactivará para nuevas detecciones. Si aparece trabajo activo, el servidor rechazará la acción y solicitará drenaje.',
      },
      drain: {
        title: `Drenar ${targetLabel}`,
        message:
          'No se admitirán trabajos nuevos. Las sesiones ya iniciadas terminarán su confirmación y el flujo secuencial continuará.',
      },
      reset_breaker: {
        title: 'Restablecer protección',
        message:
          'Se quitará el bloqueo. Volverá a regir el modo actual; si está habilitado, podrán reanudarse nuevas admisiones.',
      },
    };
    const selection = copy[action];
    this.ui.setPendingAction({
      ...selection,
      execute: async () => {
        const updated = await this.api.updateOpportunityControl({
          action,
          target,
          reason: `dashboard_${action}`,
          expected_revision: control.revision,
        });
        this.opportunityControl.set(updated);
        return {
          status: updated.status ?? 'updated',
          message: updated.message,
        };
      },
      successMessage: `${selection.title}: solicitado`,
    });
  }

  public requestRestartWorker(): void {
    const releaseSafeBackoffs = this.releaseSafeBackoffsOnRestart();
    this.ui.setPendingAction({
      title: releaseSafeBackoffs ? 'Reiniciar y reintentar' : 'Reiniciar worker',
      message: releaseSafeBackoffs
        ? 'Reiniciar el worker y quitar solo los backoffs técnicos que no llegaron a intentar una reserva.'
        : 'Solicitar reinicio controlado del worker conservando todos los backoffs.',
      execute: () => this.api.restartWorker(releaseSafeBackoffs),
      successMessage: (response) => {
        if (!releaseSafeBackoffs) {
          return 'Reinicio controlado solicitado';
        }
        const released = response.released_backoff_count ?? 0;
        const protectedCount = response.protected_backoff_count ?? 0;
        return `Reinicio solicitado: ${released} backoff(s) liberado(s), ${protectedCount} protegido(s)`;
      },
      onSuccess: () => this.ui.activeModal.set(null),
    });
  }

  public requestWorkerPauseToggle(): void {
    const paused = this.worker()?.paused === true;
    this.ui.setPendingAction({
      title: paused ? 'Reactivar búsquedas' : 'Detener búsquedas',
      message: paused
        ? 'El worker volverá a admitir revisiones y reservas. Los backoffs y estados protegidos se conservan.'
        : 'El worker dejará de admitir trabajo nuevo cuando llegue a un punto seguro. No corta una reserva en curso ni borra mediciones.',
      execute: () => (paused ? this.api.resumeWorker() : this.api.pauseWorker()),
      successMessage: paused
        ? 'Reactivación solicitada; el worker la confirmará al aplicarla'
        : 'Pausa solicitada; el worker se detendrá en un punto seguro',
    });
  }

  public async copyDashboardSnapshot(): Promise<void> {
    try {
      const workerCommands = await this.api.getWorkerCommands();
      this.workerCommands.set(workerCommands);
      const snapshot = {
        snapshot_version: 1,
        generated_at: new Date().toISOString(),
        health: this.snapshotHealth(this.health()),
        worker: this.snapshotWorker(this.worker()),
        current_order: this.snapshotOrder(this.currentOrder()),
        service_orders: this.orderList.filteredOrders().map((order) => this.snapshotOrder(order)),
        runs: this.filteredRuns().map((run) => this.snapshotRun(run)),
        worker_commands: workerCommands.map((command) => this.snapshotWorkerCommand(command)),
      };
      await navigator.clipboard.writeText(JSON.stringify(snapshot, null, 2));
      this.ui.markCopied('snapshot');
    } catch (error) {
      this.ui.errorMessage.set(this.presentation.readError(error));
    }
  }

  public phaseLabel(phase: string | null | undefined): string {
    if (!phase) {
      return 'sin fase';
    }
    return phase.replaceAll('_', ' ');
  }

  public generalObserverActive(): boolean {
    const worker = this.worker();
    return Boolean(
      worker && !worker.current_order_id && worker.phase?.startsWith('monitoring_observer'),
    );
  }

  public currentWorkLabel(): string {
    if (this.worker()?.current_order_id) {
      return this.worker()!.current_order_id!;
    }
    if (this.generalObserverActive()) {
      return 'Observador general activo';
    }
    return 'Sin orden activa';
  }

  private snapshotHealth(health: HealthPayload | null): DashboardSnapshotHealth | null {
    if (!health) {
      return null;
    }
    return {
      status: health.status,
      worker_running: health.worker_running,
      reason: health.reason,
      captcha_shadow_enabled: health.captcha_shadow_enabled,
    };
  }

  private snapshotWorker(worker: WorkerStatus | null): DashboardSnapshotWorker | null {
    if (!worker) {
      return null;
    }
    return {
      phase: worker.phase,
      paused: worker.paused,
      current_order_id: worker.current_order_id,
      session_started_at: worker.session_started_at,
      last_check_at: worker.last_check_at,
      next_check_at: worker.next_check_at,
      confirmed_reservations: worker.confirmed_reservations,
      consecutive_errors: worker.consecutive_errors,
      updated_at: worker.updated_at,
      worker_running: worker.worker_running,
      continuous_worker_enabled: worker.continuous_worker_enabled,
    };
  }

  private snapshotOrder(order: ServiceOrder | null): DashboardSnapshotOrder | null {
    if (!order) {
      return null;
    }
    return {
      order_id: order.order_id,
      priority: order.priority,
      charge_required: order.charge_required,
      service_type: order.service_type,
      status: order.status,
      reservation_status: order.reservation_status,
      payment_status: order.payment_status,
      whatsapp_message_action_state: order.whatsapp_message_action_state,
      whatsapp_followup_action_state: order.whatsapp_followup_action_state,
      parent_order_id: order.parent_order_id,
      preflight_status: order.preflight_status,
      registration_notice_status: order.registration_notice_status,
      created_at: order.created_at,
      updated_at: order.updated_at,
    };
  }

  private snapshotRun(run: RunSummary): DashboardSnapshotRun {
    return {
      run_id: run.run_id,
      order_id: run.order_id,
      status: run.status,
      exit_code: run.exit_code,
      started_at: run.started_at,
      finished_at: run.finished_at,
      duration_seconds: run.duration_seconds,
      reservation_attempted: run.reservation_attempted,
      reservation_confirmed: run.reservation_confirmed,
      screenshot_count: run.screenshot_count,
    };
  }

  private snapshotWorkerCommand(command: WorkerCommand): DashboardSnapshotWorkerCommand {
    return {
      command_id: command.command_id,
      command: command.command,
      status: command.status,
      requested_at: command.requested_at,
      claimed_at: command.claimed_at,
      processed_at: command.processed_at,
    };
  }

  public async loadInboxView(scope: RequestScope): Promise<void> {
    const inboxRequest = this.api.getOperatorInbox(scope);
    if (!this.captchas.captchaShadowEnabled()) {
      this.operatorInbox.set(await inboxRequest);
      this.captchas.captchaReviewTotal.set(0);
      return;
    }
    const [inbox, pendingCaptchas] = await Promise.all([
      inboxRequest,
      this.captchas.fetchPendingCaptchaReview(scope),
    ]);
    this.operatorInbox.set(inbox);
    if (pendingCaptchas) {
      this.captchas.captchaReviewTotal.set(pendingCaptchas.pagination.total);
    }
    return;
  }

  public async loadSummaryView(scope: RequestScope): Promise<void> {
    const [
      orders,
      runs,
      monthlySummary,
      captchaSamplingControl,
      captchaAuthorityControl,
      opportunityControl,
      opportunityBursts,
      appointmentReminderStatus,
      workerCommands,
    ] = await Promise.all([
      this.orderList.fetchOrders(scope),
      this.api.getRuns(scope),
      this.finance.fetchMonthlySummary(scope),
      this.captchas.fetchCaptchaSamplingControl(scope),
      this.captchas.fetchCaptchaAuthorityControl(scope),
      this.api.getOpportunityControl(scope),
      this.api.getOpportunityBursts(scope),
      this.followups.fetchReminderStatus(scope),
      this.api.getWorkerCommands(scope),
    ]);
    this.orders.applyOrders(orders);
    this.runs.set(runs);
    this.finance.monthlySummary.set(monthlySummary);
    this.captchas.applyCaptchaSamplingControl(captchaSamplingControl);
    this.captchas.captchaAuthorityControl.set(captchaAuthorityControl);
    this.opportunityControl.set(opportunityControl);
    this.opportunityBursts.set(opportunityBursts.bursts);
    this.followups.appointmentReminderStatus.set(appointmentReminderStatus);
    this.workerCommands.set(workerCommands);
    return;
  }

  public async loadRunsView(scope: RequestScope): Promise<void> {
    const [runs, workerCommands] = await Promise.all([
      this.api.getRuns(scope),
      this.api.getWorkerCommands(scope),
    ]);
    this.runs.set(runs);
    this.workerCommands.set(workerCommands);
    return;
  }

  public fetchOperationalHealth(scope: RequestScope) {
    return Promise.all([this.api.getHealth(scope), this.api.getWorker(scope)]);
  }

  public applyOperationalHealth(health: HealthPayload, worker: WorkerStatus): void {
    this.health.set(health);
    this.worker.set(worker);
  }

  private get presentation() { return this.injector.get(DASHBOARD_OPERATIONS_PRESENTATION); }

  private get captchas() { return this.injector.get(DASHBOARD_OPERATIONS_CAPTCHAS); }

  private get orders() { return this.injector.get(DASHBOARD_OPERATIONS_ORDERS); }

  private get messages() { return this.injector.get(DASHBOARD_OPERATIONS_MESSAGES); }

  private get finance() { return this.injector.get(DASHBOARD_OPERATIONS_FINANCE); }

  private get ui() { return this.injector.get(DASHBOARD_OPERATIONS_UI); }

  private get navigation() { return this.injector.get(DASHBOARD_OPERATIONS_NAVIGATION); }

  private get followups() { return this.injector.get(DASHBOARD_OPERATIONS_FOLLOWUPS); }
}
