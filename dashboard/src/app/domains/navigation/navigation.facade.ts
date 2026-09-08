import { Injectable, Injector, computed, inject, signal } from '@angular/core';
import { NavigationEnd, Router } from '@angular/router';
import { Subscription, filter } from 'rxjs';
import {
  CaptchaWorkspaceMode,
  LoadState,
  VIEW_LABELS,
  ViewKey,
} from '../../dashboard-domain.contracts';
import {
  DASHBOARD_NAVIGATION_CAPTCHAS,
  DASHBOARD_NAVIGATION_FINANCE,
  DASHBOARD_NAVIGATION_FOLLOWUPS,
  DASHBOARD_NAVIGATION_MESSAGES,
  DASHBOARD_NAVIGATION_OPERATIONS,
  DASHBOARD_NAVIGATION_ORDERS,
  DASHBOARD_NAVIGATION_PRESENTATION,
  DASHBOARD_NAVIGATION_UI,
} from '../../dashboard-domain.ports';
import {
  CaptchaRefreshMode,
  dashboardDataExpired,
  dashboardRefreshInterval,
} from '../../dashboard-refresh.policy';
import { OrdersListFacade } from '../../domains/orders/orders-list.facade';
import { RequestScope, isRequestCancelled } from '../../request-cancellation';
import { ViewStateKind } from '../../view-state/view-state.component';

@Injectable()
export class DashboardNavigation {
  private readonly injector = inject(Injector);

  private readonly router = inject(Router);
  public readonly orderList = inject(OrdersListFacade);
  private autoRefreshTimer: number | null = null;

  private readonly loadedViews = new Set<ViewKey>();

  private readonly lastSuccessfulViewUpdate = new Map<ViewKey, number>();

  private refreshInFlight: Promise<void> | null = null;

  private refreshingView: ViewKey | null = null;

  private currentRefreshScope: RequestScope | null = null;

  private refreshGeneration = 0;

  private routerSubscription: Subscription | null = null;

  public readonly activeView = signal<ViewKey>('summary');

  public readonly sidebarCollapsed = signal(
    window.localStorage.getItem('appointment-dashboard-sidebar-collapsed') === 'true',
  );

  public readonly mobileMenuOpen = signal(false);

  public readonly autoRefreshEnabled = signal(true);

  public readonly pageHidden = signal(document.visibilityState === 'hidden');

  public readonly lastUpdatedAt = signal<string | null>(null);

  public readonly loadState = signal<LoadState>('idle');

  public readonly viewLoadError = signal<string | null>(null);

  public readonly refreshingViewState = signal<ViewKey | null>(null);

  public readonly autoRefreshPaused = computed(
    () =>
      !this.autoRefreshEnabled() || this.ui.formDirty() || this.ui.actionBusy() || !!this.ui.pendingAction(),
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
      return this.operations.runs().length > 0 || this.operations.workerCommands().length > 0 || state === 'ready';
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
    this.routerSubscription = this.router.events
      .pipe(filter((event): event is NavigationEnd => event instanceof NavigationEnd))
      .subscribe((event) => void this.activateRoute(event.urlAfterRedirects));
  }

  ngOnDestroy(): void {
    this.clearRefreshTimer();
    this.currentRefreshScope?.cancel();
    this.routerSubscription?.unsubscribe();
    this.followups.disposeFollowupRequests();
    this.captchas.disposeCaptchaRequests();
    this.ui.disposeNotifications();
    this.orders.closeTrackedManualSessionsWithBeacon();
  }

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

  public async refreshAll(): Promise<void> {
    await this.refreshView(this.activeView(), true);
  }

  public async refreshNow(): Promise<void> {
    this.ui.formDirty.set(false);
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
          this.ui.errorMessage.set(`La orden ${orderId} no existe o ya no está disponible.`);
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
        if (this.operations.selectedRunId() !== runId) {
          void this.operations.selectRun(runId, false);
        }
      } else if (this.operations.selectedRunId()) {
        this.operations.closeRunDetail(false);
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
    this.ui.errorMessage.set(null);
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
      this.lastUpdatedAt.set(this.presentation.formatClock(new Date()));
      this.lastSuccessfulViewUpdate.set(view, Date.now());
      this.loadState.set('ready');
    } catch (error) {
      if (isRequestCancelled(error) || generation !== this.refreshGeneration) {
        return;
      }
      const message = this.presentation.readError(error);
      this.loadState.set('error');
      this.viewLoadError.set(message);
      this.ui.errorMessage.set(message);
    } finally {
      if (generation === this.refreshGeneration && this.refreshingViewState() === view) {
        this.refreshingViewState.set(null);
      }
    }
  }

  private async refreshCommonData(scope: RequestScope): Promise<void> {
    const [[health, worker], [manualSessions, catalog]] = await Promise.all([
      this.operations.fetchOperationalHealth(scope), this.orders.fetchOrderCommonData(scope),
    ]);
    this.operations.applyOperationalHealth(health, worker);
    this.orders.applyOrderCommonData(manualSessions, catalog);
  }

  private async refreshViewData(view: ViewKey, showLoading: boolean, scope: RequestScope): Promise<void> {
    if (view === 'inbox') { await this.operations.loadInboxView(scope); return; }
    if (view === 'summary') { await this.operations.loadSummaryView(scope); return; }
    if (view === 'finance') { await this.finance.loadFinanceView(scope); return; }
    if (view === 'messageTemplates') { await this.messages.loadMessagesView(scope); return; }
    if (view === 'orders') { await this.orders.loadOrdersView(scope); return; }
    if (view === 'runs') { await this.operations.loadRunsView(scope); return; }
    if (view === 'followups') { await this.followups.loadFollowupsView(scope); return; }
    await this.captchas.loadCaptchaData(showLoading || this.captchas.captchaState() === 'idle', scope);
  }

  public toggleSidebar(): void {
    const collapsed = !this.sidebarCollapsed();
    this.sidebarCollapsed.set(collapsed);
    window.localStorage.setItem('appointment-dashboard-sidebar-collapsed', String(collapsed));
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

  private get ui() { return this.injector.get(DASHBOARD_NAVIGATION_UI); }

  private get finance() { return this.injector.get(DASHBOARD_NAVIGATION_FINANCE); }

  private get messages() { return this.injector.get(DASHBOARD_NAVIGATION_MESSAGES); }

  private get operations() { return this.injector.get(DASHBOARD_NAVIGATION_OPERATIONS); }

  private get followups() { return this.injector.get(DASHBOARD_NAVIGATION_FOLLOWUPS); }

  private get captchas() { return this.injector.get(DASHBOARD_NAVIGATION_CAPTCHAS); }

  private get orders() { return this.injector.get(DASHBOARD_NAVIGATION_ORDERS); }

  private get presentation() { return this.injector.get(DASHBOARD_NAVIGATION_PRESENTATION); }
}
