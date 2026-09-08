import {
  Component,
  HostListener,
  Injector,
  OnDestroy,
  ViewEncapsulation,
  WritableSignal,
  computed,
  effect,
  forwardRef,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { NavigationEnd, Router, RouterLink, RouterOutlet } from '@angular/router';
import { Subscription, filter } from 'rxjs';
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
  apiErrorMessage,
} from './appointment-api.service';
import {
  CaptchaWorkspaceMode,
  DashboardSnapshotHealth,
  DashboardSnapshotOrder,
  DashboardSnapshotRun,
  DashboardSnapshotWorker,
  DashboardSnapshotWorkerCommand,
  ERROR_MESSAGE_DURATION_MS,
  InboxOrderTask,
  LoadState,
  ModalKind,
  PendingAction,
  STATUS_PRESENTATIONS,
  StatusTone,
  VIEW_LABELS,
  ViewKey,
  normalizeDashboardText,
} from './dashboard-domain.contracts';
import {
  DASHBOARD_CAPTCHAS_SHELL,
  DASHBOARD_CAPTCHAS_VIEW_CAPTCHAS,
  DASHBOARD_CAPTCHAS_VIEW_SHELL,
  DASHBOARD_CREATE_ORDER_MODAL_ORDERS,
  DASHBOARD_CREATE_ORDER_MODAL_SHELL,
  DASHBOARD_EDIT_ORDER_MODAL_FINANCE,
  DASHBOARD_EDIT_ORDER_MODAL_ORDERS,
  DASHBOARD_EDIT_ORDER_MODAL_SHELL,
  DASHBOARD_FINANCE_ENTRY_MODAL_FINANCE,
  DASHBOARD_FINANCE_ENTRY_MODAL_ORDERLIST,
  DASHBOARD_FINANCE_ENTRY_MODAL_SHELL,
  DASHBOARD_FINANCE_ORDERS,
  DASHBOARD_FINANCE_SHELL,
  DASHBOARD_FINANCE_VIEW_FINANCE,
  DASHBOARD_FINANCE_VIEW_SHELL,
  DASHBOARD_FOLLOWUPS_SHELL,
  DASHBOARD_FOLLOWUPS_VIEW_FOLLOWUPS,
  DASHBOARD_FOLLOWUPS_VIEW_SHELL,
  DASHBOARD_INBOX_VIEW_CAPTCHAS,
  DASHBOARD_INBOX_VIEW_SHELL,
  DASHBOARD_MESSAGES_ORDERS,
  DASHBOARD_MESSAGES_SHELL,
  DASHBOARD_MESSAGE_TEMPLATES_VIEW_MESSAGES,
  DASHBOARD_MESSAGE_TEMPLATES_VIEW_SHELL,
  DASHBOARD_ORDERS_FINANCE,
  DASHBOARD_ORDERS_MESSAGES,
  DASHBOARD_ORDERS_SHELL,
  DASHBOARD_ORDERS_VIEW_FINANCE,
  DASHBOARD_ORDERS_VIEW_MESSAGES,
  DASHBOARD_ORDERS_VIEW_ORDERLIST,
  DASHBOARD_ORDERS_VIEW_ORDERS,
  DASHBOARD_ORDERS_VIEW_SHELL,
  DASHBOARD_ORDER_ACTIONS_MODAL_ORDERS,
  DASHBOARD_ORDER_ACTIONS_MODAL_SHELL,
  DASHBOARD_PAYMENT_MODAL_FINANCE,
  DASHBOARD_PAYMENT_MODAL_ORDERS,
  DASHBOARD_PAYMENT_MODAL_SHELL,
  DASHBOARD_PROGRAM_RESOLUTION_PANEL_ORDERS,
  DASHBOARD_PROGRAM_RESOLUTION_PANEL_SHELL,
  DASHBOARD_RUNS_VIEW_SHELL,
  DASHBOARD_SHELL_CAPTCHAS,
  DASHBOARD_SHELL_FINANCE,
  DASHBOARD_SHELL_FOLLOWUPS,
  DASHBOARD_SHELL_MESSAGES,
  DASHBOARD_SHELL_ORDERS,
  DASHBOARD_SUMMARY_VIEW_CAPTCHAS,
  DASHBOARD_SUMMARY_VIEW_FINANCE,
  DASHBOARD_SUMMARY_VIEW_FOLLOWUPS,
  DASHBOARD_SUMMARY_VIEW_ORDERLIST,
  DASHBOARD_SUMMARY_VIEW_SHELL,
  DASHBOARD_WHATSAPP_MODAL_MESSAGES,
  DASHBOARD_WHATSAPP_MODAL_SHELL,
  DASHBOARD_WORKER_RESTART_MODAL_SHELL,
} from './dashboard-domain.ports';
import {
  CaptchaRefreshMode,
  dashboardDataExpired,
  dashboardRefreshInterval,
} from './dashboard-refresh.policy';
import { DASHBOARD_VIEW_FACADE } from './dashboard-view.facade';
import { CaptchasFacade } from './domains/captchas/captchas.facade';
import { FinanceFacade } from './domains/finance/finance.facade';
import { FollowupsFacade } from './domains/followups/followups.facade';
import { MessagesFacade } from './domains/messages/messages.facade';
import { OrdersListFacade } from './domains/orders/orders-list.facade';
import { OrdersFacade } from './domains/orders/orders.facade';
import { CreateOrderModalComponent } from './modals/create-order-modal.component';
import { EditOrderModalComponent } from './modals/edit-order-modal.component';
import { FinanceEntryModalComponent } from './modals/finance-entry-modal.component';
import { OrderActionsModalComponent } from './modals/order-actions-modal.component';
import { PaymentModalComponent } from './modals/payment-modal.component';
import { WhatsappModalComponent } from './modals/whatsapp-modal.component';
import { WorkerRestartModalComponent } from './modals/worker-restart-modal.component';
import { formatPeruDate, formatPeruDateTime, formatPeruTime } from './peru-date-time';
import { RequestScope, isRequestCancelled } from './request-cancellation';
import { ViewStateComponent, ViewStateKind } from './view-state/view-state.component';

@Component({
  selector: 'app-root',
  imports: [
    FormsModule,
    ViewStateComponent,
    RouterOutlet,
    RouterLink,
    WhatsappModalComponent,
    PaymentModalComponent,
    EditOrderModalComponent,
    OrderActionsModalComponent,
    CreateOrderModalComponent,
    FinanceEntryModalComponent,
    WorkerRestartModalComponent,
  ],
  providers: [OrdersListFacade, OrdersFacade, FinanceFacade, MessagesFacade, FollowupsFacade, CaptchasFacade, { provide: DASHBOARD_VIEW_FACADE, useExisting: forwardRef(() => App) },
    { provide: DASHBOARD_ORDERS_MESSAGES, useExisting: MessagesFacade },
    { provide: DASHBOARD_ORDERS_SHELL, useExisting: forwardRef(() => App) },
    { provide: DASHBOARD_ORDERS_FINANCE, useExisting: FinanceFacade },
    { provide: DASHBOARD_FINANCE_SHELL, useExisting: forwardRef(() => App) },
    { provide: DASHBOARD_FINANCE_ORDERS, useExisting: OrdersFacade },
    { provide: DASHBOARD_MESSAGES_SHELL, useExisting: forwardRef(() => App) },
    { provide: DASHBOARD_MESSAGES_ORDERS, useExisting: OrdersFacade },
    { provide: DASHBOARD_FOLLOWUPS_SHELL, useExisting: forwardRef(() => App) },
    { provide: DASHBOARD_CAPTCHAS_SHELL, useExisting: forwardRef(() => App) },
    { provide: DASHBOARD_CREATE_ORDER_MODAL_SHELL, useExisting: forwardRef(() => App) },
    { provide: DASHBOARD_CREATE_ORDER_MODAL_ORDERS, useExisting: OrdersFacade },
    { provide: DASHBOARD_EDIT_ORDER_MODAL_SHELL, useExisting: forwardRef(() => App) },
    { provide: DASHBOARD_EDIT_ORDER_MODAL_ORDERS, useExisting: OrdersFacade },
    { provide: DASHBOARD_EDIT_ORDER_MODAL_FINANCE, useExisting: FinanceFacade },
    { provide: DASHBOARD_FINANCE_ENTRY_MODAL_SHELL, useExisting: forwardRef(() => App) },
    { provide: DASHBOARD_FINANCE_ENTRY_MODAL_FINANCE, useExisting: FinanceFacade },
    { provide: DASHBOARD_FINANCE_ENTRY_MODAL_ORDERLIST, useExisting: OrdersListFacade },
    { provide: DASHBOARD_ORDER_ACTIONS_MODAL_SHELL, useExisting: forwardRef(() => App) },
    { provide: DASHBOARD_ORDER_ACTIONS_MODAL_ORDERS, useExisting: OrdersFacade },
    { provide: DASHBOARD_PAYMENT_MODAL_SHELL, useExisting: forwardRef(() => App) },
    { provide: DASHBOARD_PAYMENT_MODAL_ORDERS, useExisting: OrdersFacade },
    { provide: DASHBOARD_PAYMENT_MODAL_FINANCE, useExisting: FinanceFacade },
    { provide: DASHBOARD_WHATSAPP_MODAL_SHELL, useExisting: forwardRef(() => App) },
    { provide: DASHBOARD_WHATSAPP_MODAL_MESSAGES, useExisting: MessagesFacade },
    { provide: DASHBOARD_WORKER_RESTART_MODAL_SHELL, useExisting: forwardRef(() => App) },
    { provide: DASHBOARD_PROGRAM_RESOLUTION_PANEL_ORDERS, useExisting: OrdersFacade },
    { provide: DASHBOARD_PROGRAM_RESOLUTION_PANEL_SHELL, useExisting: forwardRef(() => App) },
    { provide: DASHBOARD_CAPTCHAS_VIEW_CAPTCHAS, useExisting: CaptchasFacade },
    { provide: DASHBOARD_CAPTCHAS_VIEW_SHELL, useExisting: forwardRef(() => App) },
    { provide: DASHBOARD_FINANCE_VIEW_FINANCE, useExisting: FinanceFacade },
    { provide: DASHBOARD_FINANCE_VIEW_SHELL, useExisting: forwardRef(() => App) },
    { provide: DASHBOARD_FOLLOWUPS_VIEW_FOLLOWUPS, useExisting: FollowupsFacade },
    { provide: DASHBOARD_FOLLOWUPS_VIEW_SHELL, useExisting: forwardRef(() => App) },
    { provide: DASHBOARD_INBOX_VIEW_SHELL, useExisting: forwardRef(() => App) },
    { provide: DASHBOARD_INBOX_VIEW_CAPTCHAS, useExisting: CaptchasFacade },
    { provide: DASHBOARD_MESSAGE_TEMPLATES_VIEW_MESSAGES, useExisting: MessagesFacade },
    { provide: DASHBOARD_MESSAGE_TEMPLATES_VIEW_SHELL, useExisting: forwardRef(() => App) },
    { provide: DASHBOARD_ORDERS_VIEW_MESSAGES, useExisting: MessagesFacade },
    { provide: DASHBOARD_ORDERS_VIEW_ORDERS, useExisting: OrdersFacade },
    { provide: DASHBOARD_ORDERS_VIEW_SHELL, useExisting: forwardRef(() => App) },
    { provide: DASHBOARD_ORDERS_VIEW_FINANCE, useExisting: FinanceFacade },
    { provide: DASHBOARD_ORDERS_VIEW_ORDERLIST, useExisting: OrdersListFacade },
    { provide: DASHBOARD_RUNS_VIEW_SHELL, useExisting: forwardRef(() => App) },
    { provide: DASHBOARD_SUMMARY_VIEW_FINANCE, useExisting: FinanceFacade },
    { provide: DASHBOARD_SUMMARY_VIEW_FOLLOWUPS, useExisting: FollowupsFacade },
    { provide: DASHBOARD_SUMMARY_VIEW_SHELL, useExisting: forwardRef(() => App) },
    { provide: DASHBOARD_SUMMARY_VIEW_ORDERLIST, useExisting: OrdersListFacade },
    { provide: DASHBOARD_SUMMARY_VIEW_CAPTCHAS, useExisting: CaptchasFacade },
    { provide: DASHBOARD_SHELL_FINANCE, useExisting: FinanceFacade },
    { provide: DASHBOARD_SHELL_MESSAGES, useExisting: MessagesFacade },
    { provide: DASHBOARD_SHELL_FOLLOWUPS, useExisting: FollowupsFacade },
    { provide: DASHBOARD_SHELL_CAPTCHAS, useExisting: CaptchasFacade },
    { provide: DASHBOARD_SHELL_ORDERS, useExisting: OrdersFacade }
  ],
  templateUrl: './app.html',
  styleUrl: './app.css',
  encapsulation: ViewEncapsulation.None,
})
export class App implements OnDestroy {
  private readonly injector = inject(Injector);
  private readonly api = inject(AppointmentApiService);
  private readonly router = inject(Router);
  public readonly orderList = inject(OrdersListFacade);
  public readonly formatDate = formatPeruDate;

  public readonly formatDateTime = formatPeruDateTime;

  public readonly formatTime = formatPeruTime;

  private autoRefreshTimer: number | null = null;

  private readonly loadedViews = new Set<ViewKey>();

  private readonly lastSuccessfulViewUpdate = new Map<ViewKey, number>();

  private refreshInFlight: Promise<void> | null = null;

  private refreshingView: ViewKey | null = null;

  private currentRefreshScope: RequestScope | null = null;

  private refreshGeneration = 0;

  private routerSubscription: Subscription | null = null;

  private sweetAlertPromise: Promise<typeof import('sweetalert2').default> | null = null;

  private errorMessageTimer: number | null = null;

  private lastFocusedElement: HTMLElement | null = null;

  public readonly activeView = signal<ViewKey>('summary');

  public readonly sidebarCollapsed = signal(
    window.localStorage.getItem('appointment-dashboard-sidebar-collapsed') === 'true',
  );

  public readonly mobileMenuOpen = signal(false);

  public readonly activeModal = signal<ModalKind>(null);

  public readonly autoRefreshEnabled = signal(true);

  public readonly pageHidden = signal(document.visibilityState === 'hidden');

  public readonly formDirty = signal(false);

  public readonly lastUpdatedAt = signal<string | null>(null);

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

  public readonly loadState = signal<LoadState>('idle');

  public readonly viewLoadError = signal<string | null>(null);

  public readonly refreshingViewState = signal<ViewKey | null>(null);

  public readonly errorMessage = signal<string | null>(null);

  public readonly copiedLabel = signal<string | null>(null);

  public readonly actionBusy = signal(false);

  public readonly pendingAction = signal<PendingAction | null>(null);

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
    () => this.runs().filter((run) => this.statusTone(run.status) === 'bad').length,
  );

  public readonly selectedRun = computed(() => this.selectedRunDetail());

  public readonly autoRefreshPaused = computed(
    () =>
      !this.autoRefreshEnabled() || this.formDirty() || this.actionBusy() || !!this.pendingAction(),
  );

  public readonly activeViewLabel = computed(() => VIEW_LABELS[this.activeView()].label);

  public readonly activeViewGroup = computed(() => VIEW_LABELS[this.activeView()].group);

  public readonly hasActiveViewData = computed(() => {
    const view = this.activeView();
    const state = this.loadState();
    if (view === 'summary') {
      return this.finance.monthlySummary() !== null;
    }
    if (view === 'finance') {
      return this.finance.financeSummary() !== null;
    }
    if (view === 'messageTemplates') {
      return this.messages.whatsappMessageTemplates().length > 0 || state === 'ready';
    }
    if (view === 'orders') {
      return this.orderList.orders().length > 0 || state === 'ready';
    }
    if (view === 'runs') {
      return this.runs().length > 0 || this.workerCommands().length > 0 || state === 'ready';
    }
    if (view === 'followups') {
      return this.followups.postAppointmentPayload() !== null;
    }
    if (view === 'captchas') {
      return this.captchas.captchaSummary() !== null;
    }
    return this.orderList.orders().length > 0 || state === 'ready';
  });

  public readonly activeViewState = computed<ViewStateKind | null>(() => {
    const state = this.loadState();
    const hasData = this.hasActiveViewData();
    if (state === 'loading' && !hasData) {
      return 'loading';
    }
    if (state === 'error') {
      return hasData ? 'stale' : 'error';
    }
    return null;
  });

  constructor() {
    effect(() => {
      const message = this.errorMessage();
      if (this.errorMessageTimer !== null) {
        window.clearTimeout(this.errorMessageTimer);
        this.errorMessageTimer = null;
      }
      if (message) {
        this.errorMessageTimer = window.setTimeout(() => {
          this.errorMessage.set(null);
          this.errorMessageTimer = null;
        }, ERROR_MESSAGE_DURATION_MS);
      }
    });
    this.routerSubscription = this.router.events
      .pipe(filter((event): event is NavigationEnd => event instanceof NavigationEnd))
      .subscribe((event) => void this.activateRoute(event.urlAfterRedirects));
  }

  ngOnDestroy(): void {
    this.clearRefreshTimer();
    if (this.followups.postAppointmentSearchTimer !== null) {
      window.clearTimeout(this.followups.postAppointmentSearchTimer);
    }
    this.followups.postAppointmentRequestScope?.cancel();
    this.currentRefreshScope?.cancel();
    this.captchas.captchaLoadScope?.cancel();
    this.captchas.captchaQualityCaseScope?.cancel();
    this.routerSubscription?.unsubscribe();
    if (this.captchas.captchaReviewMessageTimer !== null) {
      window.clearTimeout(this.captchas.captchaReviewMessageTimer);
    }
    if (this.errorMessageTimer !== null) {
      window.clearTimeout(this.errorMessageTimer);
    }
    this.orders.closeTrackedManualSessionsWithBeacon();
  }

  @HostListener('document:visibilitychange')
  public handleVisibilityChange(): void {
    const hidden = document.visibilityState === 'hidden';
    this.pageHidden.set(hidden);
    if (hidden) {
      this.clearRefreshTimer();
      this.currentRefreshScope?.cancel();
      return;
    }
    const view = this.activeView();
    const interval = this.activeRefreshInterval();
    if (dashboardDataExpired(this.lastSuccessfulViewUpdate.get(view) ?? null, interval)) {
      void this.refreshView(view, false);
      return;
    }
    this.scheduleNextRefresh();
  }

  @HostListener('document:keydown.escape')
  public handleEscape(): void {
    if (this.actionBusy()) {
      return;
    }
    if (this.pendingAction()) {
      void this.getSweetAlert().then((sweetAlert) => sweetAlert.close());
      return;
    }
    if (this.mobileMenuOpen()) {
      this.mobileMenuOpen.set(false);
      return;
    }
    if (this.activeModal()) {
      this.closeModal();
      return;
    }
    if (this.orders.orderPanelOpen()) {
      this.orders.closeOrderPanel();
    }
  }

  public async refreshAll(): Promise<void> {
    await this.refreshView(this.activeView(), true);
  }

  public async refreshNow(): Promise<void> {
    this.formDirty.set(false);
    await this.refreshAll();
  }

  private async activateRoute(url: string): Promise<void> {
    const tree = this.router.parseUrl(url);
    const segments = tree.root.children['primary']?.segments.map((segment) => segment.path) ?? [];
    const section = segments[0] ?? 'resumen';
    const viewBySection: Record<string, ViewKey> = {
      pendientes: 'inbox',
      resumen: 'summary',
      ordenes: 'orders',
      actividad: 'runs',
      'post-cita': 'followups',
      seguimiento: 'followups',
      finanzas: 'finance',
      mensajes: 'messageTemplates',
      captchas: 'captchas',
    };
    const view = viewBySection[section] ?? 'summary';
    const previousView = this.activeView();
    let queryChanged = false;
    const month = tree.queryParams['month'];
    if (
      ['summary', 'finance'].includes(view) &&
      /^\d{4}-\d{2}$/.test(month ?? '') &&
      month !== this.finance.selectedMonth()
    ) {
      this.finance.selectedMonth.set(month);
      queryChanged = true;
    }
    const captchaMode = tree.queryParams['mode'];
    if (
      view === 'captchas' &&
      ['review', 'history', 'quality'].includes(captchaMode) &&
      captchaMode !== this.captchas.captchaWorkspaceMode()
    ) {
      this.captchas.captchaWorkspaceMode.set(captchaMode as CaptchaWorkspaceMode);
      queryChanged = true;
    }
    this.activeView.set(view);
    this.mobileMenuOpen.set(false);

    const needsRefresh = previousView !== view || !this.loadedViews.has(view) || queryChanged;
    if (needsRefresh) {
      await this.refreshView(view, !this.loadedViews.has(view));
    } else if (this.refreshingView === view && this.refreshInFlight) {
      await this.refreshInFlight;
    } else {
      this.scheduleNextRefresh();
    }

    if (view === 'orders') {
      const orderId = segments[1];
      if (orderId) {
        if (!this.orderList.orders().some((order) => order.order_id === orderId)) {
          this.errorMessage.set(`La orden ${orderId} no existe o ya no está disponible.`);
          await this.router.navigateByUrl('/ordenes', { replaceUrl: true });
          return;
        }
        if (this.orders.selectedOrderId() !== orderId || !this.orders.orderPanelOpen()) {
          this.orders.selectOrder(orderId, true, false);
        }
      } else if (this.orders.orderPanelOpen()) {
        this.orders.closeOrderPanel(false);
      }
    }
    if (view === 'runs') {
      const runId = segments[1];
      if (runId) {
        if (this.selectedRunId() !== runId) {
          void this.selectRun(runId, false);
        }
      } else if (this.selectedRunId()) {
        this.closeRunDetail(false);
      }
    }
  }

  private async refreshView(view: ViewKey, showLoading: boolean): Promise<void> {
    this.clearRefreshTimer();
    this.currentRefreshScope?.cancel();
    const scope = new RequestScope();
    const generation = ++this.refreshGeneration;
    this.currentRefreshScope = scope;
    const refresh = this.performViewRefresh(view, showLoading, scope, generation);
    this.refreshInFlight = refresh;
    this.refreshingView = view;
    try {
      await refresh;
    } finally {
      if (this.refreshInFlight === refresh) {
        this.refreshInFlight = null;
        this.refreshingView = null;
        this.currentRefreshScope = null;
        this.scheduleNextRefresh();
      }
    }
  }

  private async performViewRefresh(
    view: ViewKey,
    showLoading: boolean,
    scope: RequestScope,
    generation: number,
  ): Promise<void> {
    this.refreshingViewState.set(view);
    if (showLoading) {
      this.loadState.set('loading');
    }
    this.errorMessage.set(null);
    this.viewLoadError.set(null);
    try {
      if (view === 'inbox' || view === 'captchas') {
        await this.refreshCommonData(scope);
        if (view === 'captchas' && !this.captchas.captchaShadowEnabled()) {
          await this.router.navigate(['/resumen'], { replaceUrl: true });
          return;
        }
        await this.refreshViewData(view, showLoading, scope);
      } else {
        await Promise.all([
          this.refreshCommonData(scope),
          this.refreshViewData(view, showLoading, scope),
        ]);
      }
      if (generation !== this.refreshGeneration) {
        return;
      }
      this.loadedViews.add(view);
      this.lastUpdatedAt.set(this.formatClock(new Date()));
      this.lastSuccessfulViewUpdate.set(view, Date.now());
      this.loadState.set('ready');
    } catch (error) {
      if (isRequestCancelled(error) || generation !== this.refreshGeneration) {
        return;
      }
      const message = this.readError(error);
      this.loadState.set('error');
      this.viewLoadError.set(message);
      this.errorMessage.set(message);
    } finally {
      if (generation === this.refreshGeneration && this.refreshingViewState() === view) {
        this.refreshingViewState.set(null);
      }
    }
  }

  private async refreshCommonData(scope: RequestScope): Promise<void> {
    const currentCatalog = this.orders.servicePackageCatalog();
    const catalogRequest = currentCatalog
      ? Promise.resolve(currentCatalog)
      : this.api.getServicePackages(scope);
    const [health, worker, manualSessions, servicePackageCatalog] = await Promise.all([
      this.api.getHealth(scope),
      this.api.getWorker(scope),
      this.api.getManualSessions(scope),
      catalogRequest,
    ]);
    this.health.set(health);
    this.worker.set(worker);
    this.orders.manualSessions.set(manualSessions);
    this.orders.servicePackageCatalog.set(servicePackageCatalog);
  }

  private async refreshViewData(view: ViewKey, showLoading: boolean, scope: RequestScope): Promise<void> {
 if (view === 'inbox') { await this.loadInboxView(scope); return; }
if (view === 'summary') { await this.loadSummaryView(scope); return; }
if (view === 'finance') { await this.finance.loadFinanceView(scope); return; }
if (view === 'messageTemplates') { await this.messages.loadMessagesView(scope); return; }
if (view === 'orders') { await this.orders.loadOrdersView(scope); return; }
if (view === 'runs') { await this.loadRunsView(scope); return; }
if (view === 'followups') { await this.followups.loadFollowupsView(scope); return; }
 await this.captchas.loadCaptchaData(showLoading || this.captchas.captchaState() === 'idle', scope);
}

  public toggleSidebar(): void {
    const collapsed = !this.sidebarCollapsed();
    this.sidebarCollapsed.set(collapsed);
    window.localStorage.setItem('appointment-dashboard-sidebar-collapsed', String(collapsed));
  }

  public formatMoney(value: number): string {
    return new Intl.NumberFormat('es-PE', {
      style: 'currency',
      currency: 'PEN',
      minimumFractionDigits: 2,
    }).format(value);
  }

  public formatPercent(value: number): string {
    return new Intl.NumberFormat('es-PE', {
      style: 'percent',
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    }).format(value);
  }

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
    this.actionBusy.set(true);
    this.errorMessage.set(null);
    try {
      const order = await this.api.getServiceOrder(orderId);
      this.orderList.includeOrder(order);
      return order;
    } catch (error) {
      this.errorMessage.set(this.readError(error));
      return null;
    } finally {
      this.actionBusy.set(false);
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
    if (updateRoute && this.activeView() === 'runs') {
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
      this.runDetailError.set(this.readError(error));
    }
  }

  public closeRunDetail(updateRoute = true): void {
    this.selectedRunId.set('');
    this.selectedRunDetail.set(null);
    this.runDetailError.set(null);
    this.runDetailState.set('idle');
    if (updateRoute && this.activeView() === 'runs') {
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
    this.openModal('worker-restart');
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
    if (!control || this.actionBusy() || control.pending_application) {
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
    if (!control || this.actionBusy()) {
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
    this.setPendingAction({
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

  public closeModal(): void {
    if (this.actionBusy()) {
      return;
    }
    const modal = this.activeModal();
    this.activeModal.set(null);
    this.pendingAction.set(null);
    this.formDirty.set(false);
    this.orders.hydrateSelectedOrderForms();
    if (modal === 'create-order') {
      this.orders.clearCreateOrderForm();
    }
    if (modal === 'finance-entry') {
      this.finance.clearFinanceForm();
    }
    if (modal === 'whatsapp') {
      this.messages.whatsappPackage.set(null);
      this.messages.whatsappFollowUpPackage.set(null);
      this.messages.whatsappTestRecipient.set('');
      this.messages.whatsappTestMode.set(false);
      this.messages.whatsappFollowUpMode.set(false);
      this.messages.whatsappReviewMode.set(false);
      this.messages.whatsappReview.set(null);
      this.messages.whatsappReviewNote.set('');
      this.messages.whatsappWebResult.set(null);
      this.messages.whatsappManualFallbackOpen.set(false);
    }
    this.restoreFocus();
  }

  public editField<T>(field: WritableSignal<T>, value: T): void {
    field.set(value);
    this.formDirty.set(true);
  }

  public requestRestartWorker(): void {
    const releaseSafeBackoffs = this.releaseSafeBackoffsOnRestart();
    this.setPendingAction({
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
      onSuccess: () => this.activeModal.set(null),
    });
  }

  public requestWorkerPauseToggle(): void {
    const paused = this.worker()?.paused === true;
    this.setPendingAction({
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
      this.markCopied('snapshot');
    } catch (error) {
      this.errorMessage.set(this.readError(error));
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

  public statusLabel(
    value: string | boolean | null | undefined,
    fallback = 'Sin estado',
  ): string {
    if (value === null || value === undefined || value === '') {
      return fallback;
    }
    if (typeof value === 'boolean') {
      return value ? 'Activo' : 'Inactivo';
    }
    const normalized = value.trim().toLowerCase();
    return (
      STATUS_PRESENTATIONS[normalized]?.label ?? this.capitalize(normalized.replaceAll('_', ' '))
    );
  }

  public statusTone(value: string | boolean | null | undefined): StatusTone {
    if (typeof value === 'boolean') {
      return value ? 'good' : 'bad';
    }
    if (!value) {
      return 'neutral';
    }
    return STATUS_PRESENTATIONS[value.trim().toLowerCase()]?.tone ?? 'neutral';
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

  public markCopied(label: string): void {
    this.copiedLabel.set(label);
    window.setTimeout(() => {
      if (this.copiedLabel() === label) {
        this.copiedLabel.set(null);
      }
    }, 1600);
  }

  public readError(error: unknown): string {
    return apiErrorMessage(error);
  }

  public async setPendingAction(action: PendingAction): Promise<void> {
    this.errorMessage.set(null);
    this.captureFocus();
    this.pendingAction.set(action);
    const result = await (await this.getSweetAlert()).fire({
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
      this.pendingAction.set(null);
      this.formDirty.set(false);
      action.onSuccess?.(response);
      await this.refreshAll();
      await action.afterRefresh?.(response);
      const successMessage =
        typeof action.successMessage === 'function'
          ? action.successMessage(response)
          : action.successMessage;
      this.showToast(successMessage ?? `${action.title}: completado`);
    } catch (error) {
      const message = this.readError(error);
      this.errorMessage.set(message);
      await (await this.getSweetAlert()).fire({
        icon: 'error',
        title: 'No se pudo completar',
        text: message,
      });
    } finally {
      action.onSettled?.();
      this.pendingAction.set(null);
      this.actionBusy.set(false);
      this.restoreFocus();
    }
  }

  public showToast(title: string): void {
    void this.getSweetAlert()
      .then((sweetAlert) =>
        sweetAlert.fire({
          toast: true,
          position: 'top-end',
          icon: 'success',
          title,
          showConfirmButton: false,
          timer: 2200,
          timerProgressBar: true,
        }),
      )
      .catch(() => undefined);
  }

  public getSweetAlert(): Promise<typeof import('sweetalert2').default> {
    this.sweetAlertPromise ??= import('sweetalert2').then((module) => module.default);
    return this.sweetAlertPromise;
  }

  public openModal(modal: Exclude<ModalKind, null>): void {
    this.captureFocus();
    this.activeModal.set(modal);
    this.focusModal();
  }

  public captureFocus(): void {
    const activeElement = document.activeElement;
    this.lastFocusedElement = activeElement instanceof HTMLElement ? activeElement : null;
  }

  private focusModal(): void {
    window.setTimeout(() => {
      document.querySelector<HTMLElement>('[data-modal-initial-focus]')?.focus();
    });
  }

  public restoreFocus(): void {
    const target = this.lastFocusedElement;
    this.lastFocusedElement = null;
    window.setTimeout(() => {
      if (target?.isConnected) {
        target.focus();
        return;
      }
      document
        .querySelector<HTMLElement>(`[data-order-row="${CSS.escape(this.orders.selectedOrderId())}"]`)
        ?.focus();
    });
  }

  private async refreshFromTimer(): Promise<void> {
    if (this.pageHidden() || this.autoRefreshPaused() || this.refreshInFlight) {
      this.scheduleNextRefresh();
      return;
    }
    await this.refreshView(this.activeView(), false);
  }

  private activeRefreshInterval(): number {
    return dashboardRefreshInterval(
      this.activeView(),
      this.captchas.captchaWorkspaceMode() as CaptchaRefreshMode,
    );
  }

  public scheduleNextRefresh(): void {
    this.clearRefreshTimer();
    if (this.pageHidden() || !this.autoRefreshEnabled()) {
      return;
    }
    this.autoRefreshTimer = window.setTimeout(
      () => void this.refreshFromTimer(),
      this.activeRefreshInterval(),
    );
  }

  private clearRefreshTimer(): void {
    if (this.autoRefreshTimer !== null) {
      window.clearTimeout(this.autoRefreshTimer);
      this.autoRefreshTimer = null;
    }
  }

  public formatClock(date: Date): string {
    return date.toLocaleTimeString('es-PE', {
      timeZone: 'America/Lima',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hourCycle: 'h23',
    });
  }

  public capitalize(value: string): string {
    return value ? `${value.charAt(0).toUpperCase()}${value.slice(1)}` : value;
  }

  public optionalText(value: string): string | null {
    const trimmed = value.trim();
    return trimmed || null;
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
        this.api
          .getCaptchaEvents(
            1, 12, '', 'all', 'all', 'all', 'pending', 'review_priority', 'targeted', scope,
          )
          .catch((error: unknown) => {
            if (isRequestCancelled(error)) {
              throw error;
            }
            return null;
          }),
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
        this.api.getMonthlySummaryV2(this.finance.selectedMonth(), scope),
        this.api.getCaptchaSamplingControl(scope),
        this.api.getCaptchaAuthorityControl(scope),
        this.api.getOpportunityControl(scope),
        this.api.getOpportunityBursts(scope),
        this.api.getAppointmentReminders(scope),
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
  @HostListener('window:beforeunload') public onBeforeUnload(): void { this.orders.handleBeforeUnload(); }
  @HostListener('document:keydown', ['$event']) public onCaptchaKey(event: KeyboardEvent): void { this.captchas.handleCaptchaReviewKeyboard(event); }

  public get finance() { return this.injector.get(DASHBOARD_SHELL_FINANCE); }

  public get messages() { return this.injector.get(DASHBOARD_SHELL_MESSAGES); }

  public get followups() { return this.injector.get(DASHBOARD_SHELL_FOLLOWUPS); }

  public get captchas() { return this.injector.get(DASHBOARD_SHELL_CAPTCHAS); }

  public get orders() { return this.injector.get(DASHBOARD_SHELL_ORDERS); }
}
