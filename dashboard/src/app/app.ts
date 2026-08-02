import {
  Component,
  HostListener,
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
  ApiActionResponse,
  AppointmentApiService,
  CaptchaEvent,
  CaptchaEventsPage,
  CaptchaPrediction,
  CaptchaQuality,
  CaptchaQualityCase,
  CaptchaQualityCaseType,
  CaptchaQualityCasesPage,
  CaptchaQualityModel,
  CaptchaQualityWeek,
  CaptchaSummary,
  CloseServiceOrderPayload,
  ContactUpdatePayload,
  CreateServiceOrderPayload,
  ExcludedDateRange,
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
  WhatsAppFollowUpPackage,
  WhatsAppMessagePackage,
  WhatsAppWebDraftResponse,
  apiErrorMessage,
} from './appointment-api.service';
import { formatPeruDate, formatPeruDateTime, formatPeruTime } from './peru-date-time';
import { DASHBOARD_VIEW_FACADE } from './dashboard-view.facade';
import { ViewStateComponent, ViewStateKind } from './view-state/view-state.component';
import {
  CaptchaRefreshMode,
  dashboardDataExpired,
  dashboardRefreshInterval,
} from './dashboard-refresh.policy';
import { RequestScope, isRequestCancelled } from './request-cancellation';
import { WhatsappModalComponent } from './modals/whatsapp-modal.component';
import { PaymentModalComponent } from './modals/payment-modal.component';
import { EditOrderModalComponent } from './modals/edit-order-modal.component';
import { OrderActionsModalComponent } from './modals/order-actions-modal.component';
import { CreateOrderModalComponent } from './modals/create-order-modal.component';
import { FinanceEntryModalComponent } from './modals/finance-entry-modal.component';
import { WorkerRestartModalComponent } from './modals/worker-restart-modal.component';

type LoadState = 'idle' | 'loading' | 'ready' | 'error';
type ViewKey =
  | 'inbox'
  | 'summary'
  | 'finance'
  | 'orders'
  | 'runs'
  | 'invitations'
  | 'captchas';
type CaptchaAgreementFilter = 'all' | 'match' | 'mismatch' | 'pending';
type CaptchaPortalFilter = 'all' | 'accepted' | 'rejected' | 'unverified';
type CaptchaSourceFilter = 'all' | 'reservation' | 'observer';
type CaptchaReviewFilter = 'all' | 'validated' | 'pending';
type CaptchaWorkspaceMode = 'review' | 'history' | 'quality';
type CaptchaPredictionOption = { answer: string; modelNames: string[] };
type CaptchaPendingCorrection = {
  eventId: string;
  previousAnswer: string;
  nextAnswer: string;
};
const CAPTCHA_QUALITY_CASE_FILTERS: Array<{
  value: CaptchaQualityCaseType;
  label: string;
}> = [
  { value: 'wrong', label: 'Errores' },
  { value: 'high_confidence_wrong', label: 'Error con confianza alta' },
  { value: 'majority_wrong', label: 'Mayoría incorrecta' },
  { value: 'unanimous_wrong', label: 'Consenso incorrecto' },
  { value: 'disagreement', label: 'Desacuerdos' },
];
type ModalKind =
  | 'edit-order'
  | 'payment'
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
type StatusTone = 'good' | 'warn' | 'bad' | 'neutral';
type StatusPresentation = { label: string; tone: StatusTone };
type OrderViewState = {
  quickFilter: OrderQuickFilter;
  sortKey: OrderSortKey;
  sortDirection: SortDirection;
  page: number;
  pageSize: number;
};
type PendingAction = {
  title: string;
  message: string;
  execute: () => Promise<ApiActionResponse>;
  successMessage?: string;
  containsSecret?: boolean;
  onSuccess?: (response: ApiActionResponse) => void;
  afterRefresh?: (response: ApiActionResponse) => void | Promise<void>;
  onSettled?: () => void;
};
type OrderNextAction = {
  key: 'manual-session' | 'activate' | 'payment' | 'post-payment-whatsapp' | 'review' | 'none';
  label: string;
  description: string;
  disabled: boolean;
};
type InboxTaskKind =
  | 'preflight'
  | 'contact'
  | 'whatsapp'
  | 'payment'
  | 'followup'
  | 'review';
type InboxOrderTask = {
  key: string;
  kind: InboxTaskKind;
  order: ServiceOrder;
  title: string;
  description: string;
  label: string;
  actionLabel: string;
  icon: string;
  tone: 'bad' | 'warn' | 'neutral';
};

const ERROR_MESSAGE_DURATION_MS = 8_000;
const ORDER_VIEW_STATE_KEY = 'appointment-dashboard-order-view';
const ORDER_SEARCH_SESSION_KEY = 'appointment-dashboard-order-search';
const ORDER_PAGE_SIZES = [10, 20, 50] as const;
const ORDER_QUICK_FILTERS: readonly OrderQuickFilter[] = [
  'all',
  'ready',
  'payment_pending',
  'confirmed',
  'archived',
  'closed_no_charge',
  'restricted',
];
const ORDER_SORT_KEYS: readonly OrderSortKey[] = [
  'queue',
  'priority',
  'created_at',
  'updated_at',
  'status',
  'reservation',
  'payment',
  'closure',
  'applicant',
];
const DEFAULT_ORDER_VIEW_STATE: OrderViewState = {
  quickFilter: 'all',
  sortKey: 'queue',
  sortDirection: 'desc',
  page: 1,
  pageSize: 20,
};
const STATUS_PRESENTATIONS: Record<string, StatusPresentation> = {
  active: { label: 'Activo', tone: 'good' },
  actual: { label: 'Real', tone: 'good' },
  archived: { label: 'Archivada', tone: 'neutral' },
  available: { label: 'Disponible', tone: 'warn' },
  cancelled: { label: 'Cancelado', tone: 'neutral' },
  claimed: { label: 'En proceso', tone: 'warn' },
  closing: { label: 'Cerrando', tone: 'warn' },
  closed: { label: 'Cerrado', tone: 'neutral' },
  completed: { label: 'Completado', tone: 'good' },
  confirmed: { label: 'Confirmada', tone: 'good' },
  degraded: { label: 'Degradado', tone: 'bad' },
  draft_ready: { label: 'Borrador preparado', tone: 'warn' },
  error: { label: 'Error', tone: 'bad' },
  estimated: { label: 'Estimado', tone: 'warn' },
  failed: { label: 'Fallido', tone: 'bad' },
  family_no_charge: { label: 'Familiar sin cobro', tone: 'warn' },
  login_required: { label: 'Requiere vinculación', tone: 'warn' },
  mixed: { label: 'Mixto', tone: 'warn' },
  not_required: { label: 'No requerido', tone: 'neutral' },
  ok: { label: 'Correcto', tone: 'good' },
  opening: { label: 'Abriendo', tone: 'warn' },
  outside_hot_window: { label: 'Fuera de horario', tone: 'warn' },
  paid: { label: 'Pagado', tone: 'good' },
  partial: { label: 'Parcial', tone: 'warn' },
  paused: { label: 'Pausada', tone: 'warn' },
  pending: { label: 'Pendiente', tone: 'warn' },
  prepared: { label: 'Preparado', tone: 'warn' },
  session_ready: { label: 'WhatsApp listo', tone: 'good' },
  ready: { label: 'Lista', tone: 'good' },
  registered: { label: 'Registrada', tone: 'good' },
  rejected: { label: 'Rechazado', tone: 'bad' },
  reservation_unconfirmed: { label: 'Reserva sin confirmar', tone: 'bad' },
  reserved_payment_pending: { label: 'Reservada, pago pendiente', tone: 'warn' },
  running: { label: 'En ejecución', tone: 'warn' },
  sent: { label: 'Enviado', tone: 'good' },
  unknown: { label: 'Desconocido', tone: 'bad' },
  unavailable: { label: 'Sin disponibilidad', tone: 'neutral' },
  validated: { label: 'Validado', tone: 'good' },
  voided: { label: 'Anulado', tone: 'neutral' },
  web_unavailable: { label: 'WhatsApp Web no disponible', tone: 'bad' },
};
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
const VIEW_LABELS: Record<ViewKey, { label: string; group: string }> = {
  inbox: { label: 'Pendientes', group: 'Operación' },
  summary: { label: 'Resumen', group: 'Operación' },
  orders: { label: 'Órdenes', group: 'Operación' },
  runs: { label: 'Runs y actividad', group: 'Operación' },
  finance: { label: 'Finanzas', group: 'Administración' },
  invitations: { label: 'Invitaciones', group: 'Administración' },
  captchas: { label: 'Control de CAPTCHA', group: 'Automatización' },
};
const INITIAL_ORDER_VIEW_STATE = readOrderViewState();

function readOrderViewState(): OrderViewState {
  try {
    const stored = JSON.parse(
      window.localStorage.getItem(ORDER_VIEW_STATE_KEY) ?? '{}',
    ) as Partial<OrderViewState>;
    return {
      quickFilter: ORDER_QUICK_FILTERS.includes(stored.quickFilter as OrderQuickFilter)
        ? (stored.quickFilter as OrderQuickFilter)
        : DEFAULT_ORDER_VIEW_STATE.quickFilter,
      sortKey: ORDER_SORT_KEYS.includes(stored.sortKey as OrderSortKey)
        ? (stored.sortKey as OrderSortKey)
        : DEFAULT_ORDER_VIEW_STATE.sortKey,
      sortDirection: stored.sortDirection === 'asc' ? 'asc' : 'desc',
      page: Number.isInteger(stored.page) && Number(stored.page) > 0 ? Number(stored.page) : 1,
      pageSize: ORDER_PAGE_SIZES.includes(stored.pageSize as (typeof ORDER_PAGE_SIZES)[number])
        ? Number(stored.pageSize)
        : DEFAULT_ORDER_VIEW_STATE.pageSize,
    };
  } catch {
    return DEFAULT_ORDER_VIEW_STATE;
  }
}

function readOrderSearch(): string {
  try {
    return window.sessionStorage.getItem(ORDER_SEARCH_SESSION_KEY) ?? '';
  } catch {
    return '';
  }
}

function paginationWindow(current: number, total: number): number[] {
  const start = Math.max(1, Math.min(current - 2, total - 4));
  const end = Math.min(total, start + 4);
  return Array.from({ length: Math.max(0, end - start + 1) }, (_, index) => start + index);
}

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
  providers: [{ provide: DASHBOARD_VIEW_FACADE, useExisting: forwardRef(() => App) }],
  templateUrl: './app.html',
  styleUrl: './app.css',
  encapsulation: ViewEncapsulation.None,
})
export class App implements OnDestroy {
  protected readonly formatDate = formatPeruDate;
  protected readonly formatDateTime = formatPeruDateTime;
  protected readonly formatTime = formatPeruTime;
  private readonly api = inject(AppointmentApiService);
  private readonly router = inject(Router);
  private autoRefreshTimer: number | null = null;
  private readonly activeManualSessionIds = new Set<string>();
  private readonly loadedViews = new Set<ViewKey>();
  private readonly lastSuccessfulViewUpdate = new Map<ViewKey, number>();
  private refreshInFlight: Promise<void> | null = null;
  private refreshingView: ViewKey | null = null;
  private currentRefreshScope: RequestScope | null = null;
  private captchaLoadScope: RequestScope | null = null;
  private captchaQualityCaseScope: RequestScope | null = null;
  private refreshGeneration = 0;
  private routerSubscription: Subscription | null = null;
  private sweetAlertPromise: Promise<typeof import('sweetalert2').default> | null = null;
  private captchaReviewMessageTimer: number | null = null;
  private errorMessageTimer: number | null = null;
  private lastFocusedElement: HTMLElement | null = null;

  protected readonly activeView = signal<ViewKey>('summary');
  protected readonly sidebarCollapsed = signal(
    window.localStorage.getItem('appointment-dashboard-sidebar-collapsed') === 'true',
  );
  protected readonly mobileMenuOpen = signal(false);
  protected readonly activeModal = signal<ModalKind>(null);
  protected readonly autoRefreshEnabled = signal(true);
  protected readonly pageHidden = signal(document.visibilityState === 'hidden');
  protected readonly formDirty = signal(false);
  protected readonly lastUpdatedAt = signal<string | null>(null);
  protected readonly orderFilter = signal(readOrderSearch());
  protected readonly orderQuickFilter = signal<OrderQuickFilter>(
    INITIAL_ORDER_VIEW_STATE.quickFilter,
  );
  protected readonly orderSortKey = signal<OrderSortKey>(INITIAL_ORDER_VIEW_STATE.sortKey);
  protected readonly orderSortDirection = signal<SortDirection>(
    INITIAL_ORDER_VIEW_STATE.sortDirection,
  );
  protected readonly orderPage = signal(INITIAL_ORDER_VIEW_STATE.page);
  protected readonly orderPageSize = signal(INITIAL_ORDER_VIEW_STATE.pageSize);
  protected readonly runStatusFilter = signal('');
  protected readonly health = signal<HealthPayload | null>(null);
  protected readonly worker = signal<WorkerStatus | null>(null);
  protected readonly orders = signal<ServiceOrder[]>([]);
  protected readonly runs = signal<RunSummary[]>([]);
  protected readonly captchaSummary = signal<CaptchaSummary | null>(null);
  protected readonly captchaEvents = signal<CaptchaEvent[]>([]);
  protected readonly captchaReviewQueue = signal<CaptchaEvent[]>([]);
  protected readonly captchaReviewTotal = signal(0);
  protected readonly captchaReviewPosition = signal(0);
  protected readonly captchaWorkspaceMode = signal<CaptchaWorkspaceMode>('review');
  protected readonly captchaHistoryFiltersOpen = signal(false);
  protected readonly captchaState = signal<LoadState>('idle');
  protected readonly captchaError = signal<string | null>(null);
  protected readonly captchaPage = signal(1);
  protected readonly captchaPageSize = signal(12);
  protected readonly captchaTotal = signal(0);
  protected readonly captchaTotalPages = signal(1);
  protected readonly captchaSearch = signal('');
  protected readonly captchaAgreement = signal<CaptchaAgreementFilter>('all');
  protected readonly captchaPortalStatus = signal<CaptchaPortalFilter>('all');
  protected readonly captchaSource = signal<CaptchaSourceFilter>('all');
  protected readonly captchaReviewStatus = signal<CaptchaReviewFilter>('all');
  protected readonly captchaDrafts = signal<Record<string, string>>({});
  protected readonly captchaSavingEventId = signal('');
  protected readonly captchaReviewMessage = signal<string | null>(null);
  protected readonly captchaPendingCorrection = signal<CaptchaPendingCorrection | null>(null);
  protected readonly captchaQuality = signal<CaptchaQuality | null>(null);
  protected readonly captchaQualityCases = signal<CaptchaQualityCasesPage | null>(null);
  protected readonly captchaQualityState = signal<LoadState>('idle');
  protected readonly captchaQualityError = signal<string | null>(null);
  protected readonly captchaQualityCaseType = signal<CaptchaQualityCaseType>('wrong');
  protected readonly captchaQualityCasePage = signal(1);
  protected readonly captchaQualityCasePageSize = signal(12);
  protected readonly captchaDatasetExporting = signal(false);
  protected readonly captchaQualityCaseFilters = CAPTCHA_QUALITY_CASE_FILTERS;
  protected readonly activeCaptchaReview = computed(
    () => this.captchaReviewQueue()[this.captchaReviewPosition()] ?? null,
  );
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
  protected readonly viewLoadError = signal<string | null>(null);
  protected readonly refreshingViewState = signal<ViewKey | null>(null);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly copiedLabel = signal<string | null>(null);
  protected readonly selectedOrderId = signal('');
  protected readonly orderPanelOpen = signal(false);
  protected readonly selectedOrderDetail = signal<ServiceOrderDetail | null>(null);
  protected readonly orderDetailLoading = signal(false);
  protected readonly contactName = signal('');
  protected readonly contactWhatsapp = signal('');
  protected readonly contactSource = signal('whatsapp');
  protected readonly orderDocumentNumber = signal('');
  protected readonly orderDocumentType = signal<'dni' | 'foreign_resident_card'>('dni');
  protected readonly orderPassword = signal('');
  protected readonly orderPasswordVisible = signal(false);
  protected readonly orderPriority = signal(0);
  protected readonly orderMinimumReservationDate = signal('');
  protected readonly orderMaximumReservationDate = signal('');
  protected readonly orderAllowedWeekdays = signal<number[]>([]);
  protected readonly orderExcludedDateRanges = signal<ExcludedDateRange[]>([]);
  protected readonly orderExcludedDateStart = signal('');
  protected readonly orderExcludedDateEnd = signal('');
  protected readonly paymentAmountPaid = signal('');
  protected readonly paymentAmountAgreed = signal('');
  protected readonly editOrderSection = signal<
    'all' | 'contact' | 'credentials' | 'restrictions'
  >('all');
  protected readonly newDocumentNumber = signal('');
  protected readonly newDocumentType = signal<'dni' | 'foreign_resident_card'>('dni');
  protected readonly newPassword = signal('');
  protected readonly newContactName = signal('');
  protected readonly newContactWhatsapp = signal('');
  protected readonly newContactSource = signal('');
  protected readonly newMinimumReservationDate = signal('');
  protected readonly newMaximumReservationDate = signal('');
  protected readonly newAllowedWeekdays = signal<number[]>([]);
  protected readonly newExcludedDateRanges = signal<ExcludedDateRange[]>([]);
  protected readonly newExcludedDateStart = signal('');
  protected readonly newExcludedDateEnd = signal('');
  protected readonly splitKeepParentActive = signal(false);
  protected readonly closureReason = signal<ClosureReason>('client_withdrew');
  protected readonly closureNote = signal('');
  protected readonly actionBusy = signal(false);
  protected readonly pendingAction = signal<PendingAction | null>(null);
  protected readonly whatsappPackage = signal<WhatsAppMessagePackage | null>(null);
  protected readonly whatsappFollowUpPackage = signal<WhatsAppFollowUpPackage | null>(null);
  protected readonly whatsappPackageLoading = signal(false);
  protected readonly whatsappFollowUpLoading = signal(false);
  protected readonly whatsappTestRecipient = signal('');
  protected readonly whatsappTestMode = signal(false);
  protected readonly whatsappFollowUpMode = signal(false);
  protected readonly whatsappWebBusy = signal(false);
  protected readonly whatsappWebResult = signal<WhatsAppWebDraftResponse | null>(null);
  protected readonly whatsappManualFallbackOpen = signal(false);
  protected readonly whatsappSessionBusy = signal(false);
  protected readonly whatsappSessionState = signal<
    'unknown' | 'ready' | 'login_required' | 'error'
  >('unknown');

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
  protected readonly orderTotalPages = computed(() =>
    Math.max(1, Math.ceil(this.filteredOrders().length / this.orderPageSize())),
  );
  protected readonly currentOrderPage = computed(() =>
    Math.min(this.orderPage(), this.orderTotalPages()),
  );
  protected readonly paginatedOrders = computed(() => {
    const start = (this.currentOrderPage() - 1) * this.orderPageSize();
    return this.filteredOrders().slice(start, start + this.orderPageSize());
  });
  protected readonly orderPageStart = computed(() =>
    this.filteredOrders().length ? (this.currentOrderPage() - 1) * this.orderPageSize() + 1 : 0,
  );
  protected readonly orderPageEnd = computed(() =>
    Math.min(this.currentOrderPage() * this.orderPageSize(), this.filteredOrders().length),
  );
  protected readonly orderPageNumbers = computed(() =>
    paginationWindow(this.currentOrderPage(), this.orderTotalPages()),
  );
  protected readonly orderQuickFilters = computed(() => [
    { key: 'all' as const, label: 'Todas', count: this.orders().length },
    { key: 'ready' as const, label: 'Listas', count: this.countOrders('ready') },
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
      label: 'Con reglas de fecha',
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
  protected readonly captchaSelectedStats = computed(
    () => this.captchaSummary()?.stats.models['v2_selected'] ?? null,
  );
  protected readonly captchaPageNumbers = computed(() => {
    return paginationWindow(this.captchaPage(), this.captchaTotalPages());
  });
  protected readonly captchaQualityBestModel = computed<CaptchaQualityModel | null>(() => {
    return [...(this.captchaQuality()?.models ?? [])]
      .filter((model) => model.accuracy !== null)
      .sort(
        (left, right) =>
          (right.accuracy ?? 0) - (left.accuracy ?? 0) || right.evaluated - left.evaluated,
      )[0] ?? null;
  });
  protected readonly captchaQualityCasePageNumbers = computed(() => {
    const pagination = this.captchaQualityCases()?.pagination;
    return pagination ? paginationWindow(pagination.page, pagination.total_pages) : [];
  });
  protected readonly readyOrders = computed(
    () => this.orders().filter((order) => order.status === 'ready').length,
  );
  protected readonly pendingPaymentOrders = computed(
    () => this.orders().filter((order) => order.payment_status === 'pending').length,
  );
  protected readonly inboxOrderTasks = computed<InboxOrderTask[]>(() => {
    const tasks: InboxOrderTask[] = [];
    for (const order of this.orders()) {
      if (order.preflight_status === 'failed') {
        tasks.push({
          key: `preflight-${order.order_id}`,
          kind: 'preflight',
          order,
          title: 'Validación de acceso fallida',
          description: order.preflight_message ?? 'Vuelve a comprobar el acceso al portal.',
          label: 'Bloqueo',
          actionLabel: 'Volver a validar',
          icon: '!',
          tone: 'bad',
        });
        continue;
      }
      const hasPendingReservationPayment =
        order.status === 'reserved_payment_pending' &&
        order.reservation_status === 'confirmed' &&
        order.payment_status === 'pending';
      if (hasPendingReservationPayment && !order.contact_whatsapp_masked) {
        tasks.push({
          key: `contact-${order.order_id}`,
          kind: 'contact',
          order,
          title: 'Completar WhatsApp del cliente',
          description:
            'La reserva está confirmada, pero falta un WhatsApp válido para contactar al cliente.',
          label: 'Contacto',
          actionLabel: 'Corregir contacto',
          icon: '@',
          tone: 'bad',
        });
        continue;
      }
      if (
        hasPendingReservationPayment &&
        order.whatsapp_message_action_state === 'manual_required'
      ) {
        tasks.push({
          key: `whatsapp-${order.order_id}`,
          kind: 'whatsapp',
          order,
          title: 'Enviar constancia y cobro',
          description: 'La reserva está confirmada y todavía falta preparar el mensaje inicial.',
          label: 'WhatsApp',
          actionLabel: 'Preparar mensaje',
          icon: 'WA',
          tone: 'warn',
        });
        continue;
      }
      if (
        hasPendingReservationPayment &&
        ['failed', 'uncertain'].includes(order.whatsapp_message_action_state)
      ) {
        tasks.push({
          key: `review-whatsapp-${order.order_id}`,
          kind: 'review',
          order,
          title:
            order.whatsapp_message_action_state === 'uncertain'
              ? 'Confirmar resultado de WhatsApp'
              : 'Revisar fallo de WhatsApp',
          description:
            order.whatsapp_message_action_state === 'uncertain'
              ? 'El envío inicial terminó de forma ambigua y no debe repetirse automáticamente.'
              : 'El envío automático falló y requiere una decisión del operador.',
          label: 'WhatsApp',
          actionLabel: 'Revisar orden',
          icon: 'WA',
          tone: 'bad',
        });
        continue;
      }
      if (order.payment_status === 'pending' && order.reservation_status === 'confirmed') {
        tasks.push({
          key: `payment-${order.order_id}`,
          kind: 'payment',
          order,
          title: 'Registrar pago pendiente',
          description: 'El contacto inicial ya fue atendido y la reserva sigue pendiente de cobro.',
          label: 'Pago',
          actionLabel: 'Registrar pago',
          icon: 'S/',
          tone: 'warn',
        });
        continue;
      }
      if (
        this.isPostPaymentWhatsAppCandidate(order) &&
        ['failed', 'uncertain'].includes(order.whatsapp_followup_action_state)
      ) {
        tasks.push({
          key: `review-followup-${order.order_id}`,
          kind: 'review',
          order,
          title:
            order.whatsapp_followup_action_state === 'uncertain'
              ? 'Confirmar resultado post-pago'
              : 'Revisar fallo post-pago',
          description:
            order.whatsapp_followup_action_state === 'uncertain'
              ? 'El envío terminó de forma ambigua y no debe repetirse automáticamente.'
              : 'El seguimiento automático falló y requiere una decisión del operador.',
          label: 'Post-pago',
          actionLabel: 'Revisar orden',
          icon: 'PDF',
          tone: 'bad',
        });
      }
    }
    return tasks;
  });
  protected readonly inboxAccessCount = computed(
    () => this.inboxOrderTasks().filter((task) => task.kind === 'preflight').length,
  );
  protected readonly inboxPaymentCount = computed(
    () => this.inboxOrderTasks().filter((task) => task.kind === 'payment').length,
  );
  protected readonly inboxMessageCount = computed(
    () =>
      this.inboxOrderTasks().filter((task) =>
        ['contact', 'whatsapp', 'followup', 'review'].includes(task.kind),
      ).length,
  );
  protected readonly inboxPendingTotal = computed(
    () => this.inboxOrderTasks().length + this.captchaReviewTotal(),
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
    if (
      this.isPostPaymentWhatsAppCandidate(order) &&
      order.whatsapp_followup_action_state !== 'not_applicable'
    ) {
      if (['queued', 'blocked', 'running'].includes(order.whatsapp_followup_action_state)) {
        return {
          key: 'none',
          label: 'Seguimiento automático en proceso',
          description: 'No requiere intervención mientras el envío automático siga activo.',
          disabled: true,
        };
      }
      if (['failed', 'uncertain'].includes(order.whatsapp_followup_action_state)) {
        return {
          key: 'review',
          label: 'Revisar seguimiento',
          description:
            order.whatsapp_followup_action_state === 'uncertain'
              ? 'El resultado es ambiguo; comprueba WhatsApp antes de decidir.'
              : 'El envío falló; revisa la evidencia antes de repetirlo.',
          disabled: false,
        };
      }
      return {
        key: 'post-payment-whatsapp',
        label:
          order.whatsapp_followup_status === 'sent' ? 'Reenviar post-pago' : 'Enviar post-pago',
        description:
          order.whatsapp_followup_status === 'sent'
            ? 'El paquete post-pago ya figura enviado; usa esto solo para un reenvio.'
            : 'La reserva esta pagada; envia indicaciones y PDFs al cliente.',
        disabled: this.actionBusy(),
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
  protected readonly activeViewLabel = computed(() => VIEW_LABELS[this.activeView()].label);
  protected readonly activeViewGroup = computed(() => VIEW_LABELS[this.activeView()].group);
  protected readonly hasActiveViewData = computed(() => {
    const view = this.activeView();
    const state = this.loadState();
    if (view === 'summary') {
      return this.monthlySummary() !== null;
    }
    if (view === 'finance') {
      return this.financeSummary() !== null;
    }
    if (view === 'orders') {
      return this.orders().length > 0 || state === 'ready';
    }
    if (view === 'runs') {
      return this.runs().length > 0 || this.workerCommands().length > 0 || state === 'ready';
    }
    if (view === 'captchas') {
      return this.captchaSummary() !== null;
    }
    if (view === 'invitations') {
      return state === 'ready';
    }
    return this.orders().length > 0 || this.captchaReviewTotal() > 0 || state === 'ready';
  });
  protected readonly activeViewState = computed<ViewStateKind | null>(() => {
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
    this.currentRefreshScope?.cancel();
    this.captchaLoadScope?.cancel();
    this.captchaQualityCaseScope?.cancel();
    this.routerSubscription?.unsubscribe();
    if (this.captchaReviewMessageTimer !== null) {
      window.clearTimeout(this.captchaReviewMessageTimer);
    }
    if (this.errorMessageTimer !== null) {
      window.clearTimeout(this.errorMessageTimer);
    }
    this.closeTrackedManualSessionsWithBeacon();
  }

  @HostListener('window:beforeunload')
  protected handleBeforeUnload(): void {
    this.closeTrackedManualSessionsWithBeacon();
  }

  @HostListener('document:visibilitychange')
  protected handleVisibilityChange(): void {
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
  protected handleEscape(): void {
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
    if (this.orderPanelOpen()) {
      this.closeOrderPanel();
    }
  }

  @HostListener('document:keydown', ['$event'])
  protected handleCaptchaReviewKeyboard(event: KeyboardEvent): void {
    if (
      this.activeView() !== 'captchas' ||
      this.captchaWorkspaceMode() !== 'review' ||
      event.ctrlKey ||
      event.metaKey ||
      event.altKey
    ) {
      return;
    }
    const target = event.target as HTMLElement | null;
    if (target?.matches('input, textarea, select, button')) {
      return;
    }
    if (event.key === 'ArrowRight') {
      this.moveCaptchaReview(1);
      return;
    }
    if (event.key === 'ArrowLeft') {
      this.moveCaptchaReview(-1);
      return;
    }
    const captcha = this.activeCaptchaReview();
    if (!captcha || this.captchaSavingEventId()) {
      return;
    }
    const options = this.captchaPredictionOptions(captcha);
    const optionIndex = Number(event.key) - 1;
    if (Number.isInteger(optionIndex) && optionIndex >= 0 && options[optionIndex]) {
      event.preventDefault();
      void this.chooseCaptchaPrediction(captcha, options[optionIndex].answer);
      return;
    }
    if (event.key === 'Enter' && this.captchaChoiceMode(captcha) === 'consensus') {
      event.preventDefault();
      void this.chooseCaptchaPrediction(captcha, options[0].answer);
    }
  }

  protected async refreshAll(): Promise<void> {
    await this.refreshView(this.activeView(), true);
  }

  protected async refreshNow(): Promise<void> {
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
      finanzas: 'finance',
      invitaciones: 'invitations',
      captchas: 'captchas',
    };
    const view = viewBySection[section] ?? 'summary';
    const previousView = this.activeView();
    let queryChanged = false;
    const month = tree.queryParams['month'];
    if (
      ['summary', 'finance'].includes(view) &&
      /^\d{4}-\d{2}$/.test(month ?? '') &&
      month !== this.selectedMonth()
    ) {
      this.selectedMonth.set(month);
      queryChanged = true;
    }
    const captchaMode = tree.queryParams['mode'];
    if (
      view === 'captchas' &&
      ['review', 'history', 'quality'].includes(captchaMode) &&
      captchaMode !== this.captchaWorkspaceMode()
    ) {
      this.captchaWorkspaceMode.set(captchaMode as CaptchaWorkspaceMode);
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
        if (!this.orders().some((order) => order.order_id === orderId)) {
          this.errorMessage.set(`La orden ${orderId} no existe o ya no está disponible.`);
          await this.router.navigateByUrl('/ordenes', { replaceUrl: true });
          return;
        }
        if (this.selectedOrderId() !== orderId || !this.orderPanelOpen()) {
          this.selectOrder(orderId, true, false);
        }
      } else if (this.orderPanelOpen()) {
        this.closeOrderPanel(false);
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
      await Promise.all([
        this.refreshCommonData(scope),
        this.refreshViewData(view, showLoading, scope),
      ]);
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
    const [health, worker, manualSessions] = await Promise.all([
      this.api.getHealth(scope),
      this.api.getWorker(scope),
      this.api.getManualSessions(scope),
    ]);
    this.health.set(health);
    this.worker.set(worker);
    this.manualSessions.set(manualSessions);
  }

  private async refreshViewData(
    view: ViewKey,
    showLoading: boolean,
    scope: RequestScope,
  ): Promise<void> {
    if (view === 'inbox') {
      const [orders, pendingCaptchas] = await Promise.all([
        this.api.getServiceOrders(scope),
        this.api.getCaptchaEvents(
          1, 12, '', 'all', 'all', 'all', 'pending', 'review_priority', scope,
        ).catch((error: unknown) => {
          if (isRequestCancelled(error)) {
            throw error;
          }
          return null;
        }),
      ]);
      this.applyOrders(orders);
      if (pendingCaptchas) {
        this.captchaReviewTotal.set(pendingCaptchas.pagination.total);
      }
      return;
    }
    if (view === 'summary') {
      const [orders, runs, monthlySummary] = await Promise.all([
        this.api.getServiceOrders(scope),
        this.api.getRuns(scope),
        this.api.getMonthlySummary(this.selectedMonth(), scope),
      ]);
      this.applyOrders(orders);
      this.runs.set(runs);
      this.monthlySummary.set(monthlySummary);
      return;
    }
    if (view === 'finance') {
      const categoriesRequest = this.financeCategories().length
        ? Promise.resolve(this.financeCategories())
        : this.api.getFinanceCategories(scope);
      const [financeCategories, financeEntries, financeSummary] = await Promise.all([
        categoriesRequest,
        this.api.getFinanceEntries(this.selectedMonth(), scope),
        this.api.getFinanceSummary(this.selectedMonth(), scope),
      ]);
      this.financeCategories.set(financeCategories);
      this.financeEntries.set(financeEntries);
      this.financeSummary.set(financeSummary);
      return;
    }
    if (view === 'orders') {
      this.applyOrders(await this.api.getServiceOrders(scope));
      return;
    }
    if (view === 'runs') {
      const [runs, workerCommands] = await Promise.all([
        this.api.getRuns(scope),
        this.api.getWorkerCommands(scope),
      ]);
      this.runs.set(runs);
      this.workerCommands.set(workerCommands);
      return;
    }
    if (view === 'invitations') {
      return;
    }
    await this.loadCaptchaData(showLoading || this.captchaState() === 'idle', scope);
  }

  private applyOrders(orders: ServiceOrder[]): void {
    this.orders.set(orders);
    this.keepValidOrderPage();
    this.keepValidSelection(orders);
    this.hydrateSelectedOrderForms();
    if (this.orderPanelOpen() && this.selectedOrderId() && !this.selectedOrderDetail()) {
      void this.loadSelectedOrderDetail(this.selectedOrderId());
    }
  }

  protected toggleSidebar(): void {
    const collapsed = !this.sidebarCollapsed();
    this.sidebarCollapsed.set(collapsed);
    window.localStorage.setItem('appointment-dashboard-sidebar-collapsed', String(collapsed));
  }

  protected async loadCaptchaData(showLoading = true, scope?: RequestScope): Promise<void> {
    const ownsScope = !scope;
    if (ownsScope) {
      this.captchaLoadScope?.cancel();
      this.captchaLoadScope = new RequestScope();
    }
    const activeScope = scope ?? this.captchaLoadScope!;
    if (showLoading) {
      this.captchaState.set('loading');
    }
    this.captchaError.set(null);
    try {
      if (this.captchaWorkspaceMode() === 'quality') {
        const [summary] = await Promise.all([
          this.api.getCaptchaSummary(activeScope),
          this.loadCaptchaQuality(activeScope),
        ]);
        this.captchaSummary.set(summary);
        this.captchaReviewTotal.set(
          Math.max(0, summary.stats.events - summary.stats.human_labeled),
        );
        this.captchaState.set('ready');
        return;
      }
      const [summary, page, reviewPage] = await Promise.all([
        this.api.getCaptchaSummary(activeScope),
        this.api.getCaptchaEvents(
          this.captchaPage(),
          this.captchaPageSize(),
          this.captchaSearch().trim(),
          this.captchaAgreement(),
          this.captchaPortalStatus(),
          this.captchaSource(),
          this.captchaReviewStatus(),
          'newest',
          activeScope,
        ),
        this.api.getCaptchaEvents(
          1, 48, '', 'all', 'all', 'all', 'pending', 'review_priority', activeScope,
        ),
      ]);
      this.captchaSummary.set(summary);
      this.applyCaptchaPage(page);
      this.captchaReviewQueue.set(reviewPage.events);
      this.captchaReviewTotal.set(reviewPage.pagination.total);
      if (this.captchaReviewPosition() >= reviewPage.events.length) {
        this.captchaReviewPosition.set(0);
      }
      this.captchaState.set('ready');
    } catch (error) {
      if (isRequestCancelled(error)) {
        return;
      }
      this.captchaState.set('error');
      this.captchaError.set(this.readError(error));
    } finally {
      if (ownsScope && this.captchaLoadScope === activeScope) {
        this.captchaLoadScope = null;
      }
    }
  }

  protected async loadCaptchaQuality(scope?: RequestScope): Promise<void> {
    if (!this.captchaQuality()) {
      this.captchaQualityState.set('loading');
    }
    this.captchaQualityError.set(null);
    try {
      const [quality, cases] = await Promise.all([
        this.api.getCaptchaQuality(scope),
        this.api.getCaptchaQualityCases(
          this.captchaQualityCaseType(),
          this.captchaQualityCasePage(),
          this.captchaQualityCasePageSize(),
          scope,
        ),
      ]);
      this.captchaQuality.set(quality);
      this.applyCaptchaQualityCases(cases);
      this.captchaQualityState.set('ready');
    } catch (error) {
      if (isRequestCancelled(error)) {
        return;
      }
      this.captchaQualityState.set('error');
      this.captchaQualityError.set(this.readError(error));
    }
  }

  protected async changeCaptchaQualityCaseType(value: CaptchaQualityCaseType): Promise<void> {
    if (value === this.captchaQualityCaseType()) {
      return;
    }
    this.captchaQualityCaseType.set(value);
    this.captchaQualityCasePage.set(1);
    await this.loadCaptchaQualityCases();
  }

  protected async goToCaptchaQualityCasePage(page: number): Promise<void> {
    const pagination = this.captchaQualityCases()?.pagination;
    if (!pagination || page < 1 || page > pagination.total_pages || page === pagination.page) {
      return;
    }
    this.captchaQualityCasePage.set(page);
    await this.loadCaptchaQualityCases();
  }

  private async loadCaptchaQualityCases(): Promise<void> {
    this.captchaQualityCaseScope?.cancel();
    const scope = new RequestScope();
    this.captchaQualityCaseScope = scope;
    this.captchaQualityError.set(null);
    try {
      const cases = await this.api.getCaptchaQualityCases(
        this.captchaQualityCaseType(),
        this.captchaQualityCasePage(),
        this.captchaQualityCasePageSize(),
        scope,
      );
      this.applyCaptchaQualityCases(cases);
    } catch (error) {
      if (!isRequestCancelled(error)) {
        this.captchaQualityError.set(this.readError(error));
      }
    } finally {
      if (this.captchaQualityCaseScope === scope) {
        this.captchaQualityCaseScope = null;
      }
    }
  }

  private applyCaptchaQualityCases(cases: CaptchaQualityCasesPage): void {
    this.captchaQualityCases.set(cases);
    this.captchaQualityCasePage.set(cases.pagination.page);
    this.captchaQualityCasePageSize.set(cases.pagination.page_size);
  }

  protected async exportCaptchaDataset(): Promise<void> {
    if (this.captchaDatasetExporting()) {
      return;
    }
    this.captchaDatasetExporting.set(true);
    this.captchaQualityError.set(null);
    try {
      const archive = await this.api.downloadCaptchaDataset();
      const url = URL.createObjectURL(archive);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = 'captcha-human-validated-dataset.zip';
      anchor.hidden = true;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
    } catch (error) {
      this.captchaQualityError.set(this.readError(error));
    } finally {
      this.captchaDatasetExporting.set(false);
    }
  }

  protected async applyCaptchaFilters(): Promise<void> {
    this.captchaPage.set(1);
    await this.loadCaptchaData();
  }

  protected async setCaptchaAgreement(filter: CaptchaAgreementFilter): Promise<void> {
    if (this.captchaAgreement() === filter) {
      return;
    }
    this.captchaAgreement.set(filter);
    await this.applyCaptchaFilters();
  }

  protected async changeCaptchaPortalStatus(value: CaptchaPortalFilter): Promise<void> {
    this.captchaPortalStatus.set(value);
    await this.applyCaptchaFilters();
  }

  protected async changeCaptchaSource(value: CaptchaSourceFilter): Promise<void> {
    this.captchaSource.set(value);
    await this.applyCaptchaFilters();
  }

  protected async changeCaptchaReviewStatus(value: CaptchaReviewFilter): Promise<void> {
    this.captchaReviewStatus.set(value);
    await this.applyCaptchaFilters();
  }

  protected showCaptchaWorkspace(mode: CaptchaWorkspaceMode): void {
    const changed = this.captchaWorkspaceMode() !== mode;
    this.captchaWorkspaceMode.set(mode);
    this.captchaPendingCorrection.set(null);
    this.clearCaptchaReviewMessage();
    this.scheduleNextRefresh();
    if (this.activeView() === 'captchas') {
      void this.router.navigate([], {
        queryParams: { mode },
        queryParamsHandling: 'merge',
        replaceUrl: true,
      });
      if (changed) {
        void this.loadCaptchaData(mode === 'quality');
      }
    }
  }

  protected toggleCaptchaHistoryFilters(): void {
    this.captchaHistoryFiltersOpen.update((open) => !open);
  }

  protected captchaActiveFilterCount(): number {
    return (
      Number(this.captchaAgreement() !== 'all') +
      Number(this.captchaPortalStatus() !== 'all') +
      Number(this.captchaSource() !== 'all')
    );
  }

  protected moveCaptchaReview(offset: number): void {
    const next = this.captchaReviewPosition() + offset;
    if (next < 0 || next >= this.captchaReviewQueue().length) {
      return;
    }
    this.captchaReviewPosition.set(next);
    this.captchaPendingCorrection.set(null);
    this.clearCaptchaReviewMessage();
  }

  protected async changeCaptchaPageSize(value: number | string): Promise<void> {
    this.captchaPageSize.set(Number(value));
    await this.applyCaptchaFilters();
  }

  protected async goToCaptchaPage(page: number): Promise<void> {
    if (page < 1 || page > this.captchaTotalPages() || page === this.captchaPage()) {
      return;
    }
    this.captchaPage.set(page);
    await this.loadCaptchaData();
  }

  protected captchaPrediction(event: CaptchaEvent, modelName: string): CaptchaPrediction | null {
    return event.predictions.find((prediction) => prediction.model_name === modelName) ?? null;
  }

  protected captchaPredictionTone(event: CaptchaEvent, prediction: CaptchaPrediction): string {
    const reference = event.human_label?.answer ?? event.external_answer;
    if (!reference) {
      return 'neutral';
    }
    return prediction.prediction === reference ? 'good' : 'warn';
  }

  protected captchaPortalLabel(event: CaptchaEvent): string {
    if (this.isObserverCaptcha(event)) {
      return 'Portal no aplica';
    }
    if (event.portal_accepted === true) {
      return 'Aceptado por el portal';
    }
    if (event.portal_accepted === false) {
      return 'CAPTCHA rechazado';
    }
    return 'Sin validar por el portal';
  }

  protected captchaPortalTone(event: CaptchaEvent): string {
    if (event.portal_accepted === true) {
      return 'good';
    }
    if (event.portal_accepted === false) {
      return 'bad';
    }
    return 'neutral';
  }

  protected captchaAgreementLabel(event: CaptchaEvent): string {
    if (this.isObserverCaptcha(event)) {
      return event.predictions.length ? 'Solo modelos locales' : 'Inferencia pendiente';
    }
    if (!event.external_answer || !this.captchaPrediction(event, 'v2_selected')) {
      return 'Comparación pendiente';
    }
    return event.selected_matches_external ? 'Coincide con 2Captcha' : 'Difiere de 2Captcha';
  }

  protected captchaAgreementTone(event: CaptchaEvent): string {
    if (this.isObserverCaptcha(event)) {
      return event.predictions.length ? 'good' : 'neutral';
    }
    if (!event.external_answer || !this.captchaPrediction(event, 'v2_selected')) {
      return 'neutral';
    }
    return event.selected_matches_external ? 'good' : 'warn';
  }

  protected formatMilliseconds(value: number | null | undefined): string {
    if (value === null || value === undefined || !Number.isFinite(value)) {
      return 'Sin dato';
    }
    return value >= 1000 ? `${(value / 1000).toFixed(3)} s` : `${value.toFixed(3)} ms`;
  }

  protected formatConfidence(value: number | null | undefined): string {
    if (value === null || value === undefined || !Number.isFinite(value)) {
      return 'Sin dato';
    }
    return `${(value * 100).toFixed(1)}%`;
  }

  protected captchaQualityAccuracy(value: number | null | undefined): string {
    return this.formatConfidence(value);
  }

  protected captchaQualityModelTone(model: CaptchaQualityModel): string {
    if (model.accuracy === null || model.evaluated < 10) {
      return 'neutral';
    }
    if (model.accuracy >= 0.95) {
      return 'good';
    }
    return model.accuracy >= 0.85 ? 'warn' : 'bad';
  }

  protected captchaQualityCaseSummary(item: CaptchaQualityCase): string {
    if (item.case_types.includes('unanimous_wrong')) {
      return 'Los tres modelos coincidieron en una respuesta incorrecta.';
    }
    if (item.case_types.includes('majority_wrong')) {
      return 'La respuesta apoyada por la mayoría fue incorrecta.';
    }
    if (item.case_types.includes('high_confidence_wrong')) {
      return 'Al menos un modelo falló con confianza alta.';
    }
    if (item.case_types.includes('disagreement')) {
      return 'Los modelos no produjeron la misma respuesta.';
    }
    return 'Al menos un modelo difiere de la validación humana.';
  }

  protected captchaQualityWeeklyModel(week: CaptchaQualityWeek, modelName: string) {
    return week.models[modelName] ?? null;
  }

  protected captchaOrderLabel(event: CaptchaEvent): string {
    if (this.isObserverCaptcha(event)) {
      return `Observador · muestra ${event.metadata.attempt ?? '?'} de 15`;
    }
    return event.metadata.order_id || (event.metadata.run_id ? 'Observador' : 'Sin orden');
  }

  protected isObserverCaptcha(event: CaptchaEvent): boolean {
    return event.metadata.observer === 1 || event.metadata.observer === true;
  }

  protected captchaLocalTotalMs(event: CaptchaEvent): number | null {
    if (!event.predictions.length) {
      return null;
    }
    return event.predictions.reduce((total, prediction) => total + prediction.inference_ms, 0);
  }

  protected captchaDraft(event: CaptchaEvent): string {
    return this.captchaDrafts()[event.event_id] ?? event.human_label?.answer ?? '';
  }

  protected updateCaptchaDraft(eventId: string, value: string): void {
    const normalized = value
      .toUpperCase()
      .replace(/[^A-Z0-9]/g, '')
      .slice(0, 5);
    this.captchaDrafts.update((drafts) => ({ ...drafts, [eventId]: normalized }));
    this.clearCaptchaReviewMessage();
  }

  protected captchaPredictionOptions(event: CaptchaEvent): CaptchaPredictionOption[] {
    const groups = new Map<string, string[]>();
    for (const prediction of event.predictions) {
      const models = groups.get(prediction.prediction) ?? [];
      groups.set(prediction.prediction, [...models, prediction.model_name]);
    }
    return [...groups.entries()]
      .map(([answer, modelNames]) => ({ answer, modelNames }))
      .sort(
        (left, right) =>
          right.modelNames.length - left.modelNames.length ||
          left.answer.localeCompare(right.answer),
      );
  }

  protected captchaChoiceMode(event: CaptchaEvent): 'consensus' | 'majority' | 'manual' {
    const options = this.captchaPredictionOptions(event);
    if (event.predictions.length === 3 && options.length === 1) {
      return 'consensus';
    }
    if (event.predictions.length === 3 && options.length === 2) {
      return 'majority';
    }
    return 'manual';
  }

  protected captchaChoiceLabel(event: CaptchaEvent): string {
    const mode = this.captchaChoiceMode(event);
    if (mode === 'consensus') {
      return 'Consenso';
    }
    if (mode === 'majority') {
      return 'Mayoría 2–1';
    }
    return event.predictions.length === 3 ? 'Tres respuestas' : 'Sin consenso';
  }

  protected captchaModelLabel(modelName: string): string {
    return (
      {
        v1_real: 'Modelo A',
        v2_scratch: 'Modelo B',
        v2_selected: 'Modelo C',
      }[modelName] ?? modelName
    );
  }

  protected captchaSourceLabel(event: CaptchaEvent): string {
    return this.isObserverCaptcha(event) ? 'Observador' : 'Reserva';
  }

  protected captchaSuggestionTone(event: CaptchaEvent, answer: string): string {
    if (!event.human_label) {
      return 'neutral';
    }
    return event.human_label.answer === answer ? 'good' : 'bad';
  }

  protected async chooseCaptchaPrediction(event: CaptchaEvent, answer: string): Promise<void> {
    this.updateCaptchaDraft(event.event_id, answer);
    await this.requestCaptchaHumanLabel(event, answer);
  }

  protected async saveCaptchaHumanLabel(event: CaptchaEvent): Promise<void> {
    await this.requestCaptchaHumanLabel(event, this.captchaDraft(event));
  }

  protected pendingCaptchaCorrection(eventId: string): CaptchaPendingCorrection | null {
    const correction = this.captchaPendingCorrection();
    return correction?.eventId === eventId ? correction : null;
  }

  protected async confirmCaptchaCorrection(event: CaptchaEvent): Promise<void> {
    const correction = this.pendingCaptchaCorrection(event.event_id);
    if (!correction) {
      return;
    }
    await this.persistCaptchaHumanLabel(event, correction.nextAnswer);
  }

  protected cancelCaptchaCorrection(event: CaptchaEvent): void {
    this.captchaPendingCorrection.set(null);
    this.updateCaptchaDraft(event.event_id, event.human_label?.answer ?? '');
  }

  private async requestCaptchaHumanLabel(event: CaptchaEvent, answer: string): Promise<void> {
    if (!/^[A-Z0-9]{5}$/.test(answer)) {
      this.showCaptchaReviewMessage('Escribe exactamente cinco letras o números.', 5_000);
      return;
    }
    const currentAnswer = event.human_label?.answer;
    if (currentAnswer === answer) {
      this.captchaPendingCorrection.set(null);
      this.showCaptchaReviewMessage(`La respuesta ${answer} ya está validada.`);
      return;
    }
    if (currentAnswer) {
      this.captchaPendingCorrection.set({
        eventId: event.event_id,
        previousAnswer: currentAnswer,
        nextAnswer: answer,
      });
      return;
    }
    await this.persistCaptchaHumanLabel(event, answer);
  }

  private async persistCaptchaHumanLabel(event: CaptchaEvent, answer: string): Promise<void> {
    this.captchaSavingEventId.set(event.event_id);
    this.captchaPendingCorrection.set(null);
    this.clearCaptchaReviewMessage();
    try {
      const response = await this.api.saveCaptchaHumanLabel(
        event.event_id,
        event.image_sha256,
        answer,
      );
      this.showCaptchaReviewMessage(`Respuesta ${answer} guardada para entrenamiento.`);
      if (this.captchaWorkspaceMode() === 'review' || this.captchaReviewStatus() === 'pending') {
        this.captchaReviewPosition.set(0);
        await this.loadCaptchaData(false);
      } else {
        this.captchaEvents.update((events) =>
          events.map((item) => (item.event_id === event.event_id ? response.event : item)),
        );
        this.captchaSummary.update((summary) =>
          summary && !event.human_label
            ? {
                ...summary,
                stats: { ...summary.stats, human_labeled: summary.stats.human_labeled + 1 },
              }
            : summary,
        );
      }
    } catch (error) {
      this.showCaptchaReviewMessage(this.readError(error), 6_000);
    } finally {
      this.captchaSavingEventId.set('');
    }
  }

  private showCaptchaReviewMessage(message: string, durationMs = 3_500): void {
    this.clearCaptchaReviewMessage();
    this.captchaReviewMessage.set(message);
    this.captchaReviewMessageTimer = window.setTimeout(() => {
      this.captchaReviewMessage.set(null);
      this.captchaReviewMessageTimer = null;
    }, durationMs);
  }

  private clearCaptchaReviewMessage(): void {
    if (this.captchaReviewMessageTimer !== null) {
      window.clearTimeout(this.captchaReviewMessageTimer);
      this.captchaReviewMessageTimer = null;
    }
    this.captchaReviewMessage.set(null);
  }

  private applyCaptchaPage(page: CaptchaEventsPage): void {
    this.captchaEvents.set(page.events);
    this.captchaPage.set(page.pagination.page);
    this.captchaPageSize.set(page.pagination.page_size);
    this.captchaTotal.set(page.pagination.total);
    this.captchaTotalPages.set(page.pagination.total_pages);
    const correction = this.captchaPendingCorrection();
    if (correction && !page.events.some((event) => event.event_id === correction.eventId)) {
      this.captchaPendingCorrection.set(null);
    }
    this.captchaDrafts.update((drafts) => {
      const next = { ...drafts };
      for (const event of page.events) {
        if (!(event.event_id in next) && event.human_label) {
          next[event.event_id] = event.human_label.answer;
        }
      }
      return next;
    });
  }

  protected async changeMonth(month: string): Promise<void> {
    if (!/^\d{4}-\d{2}$/.test(month) || this.monthlyLoading() || this.financeLoading()) {
      return;
    }
    this.selectedMonth.set(month);
    const view = this.activeView();
    this.monthlyLoading.set(view === 'summary');
    this.financeLoading.set(view === 'finance');
    this.errorMessage.set(null);
    try {
      if (view === 'summary') {
        this.monthlySummary.set(await this.api.getMonthlySummary(month));
      } else {
        const [entries, financeSummary] = await Promise.all([
          this.api.getFinanceEntries(month),
          this.api.getFinanceSummary(month),
        ]);
        this.financeEntries.set(entries);
        this.financeSummary.set(financeSummary);
      }
    } catch (error) {
      this.errorMessage.set(this.readError(error));
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

  protected async requestVoidFinanceEntry(entry: FinanceEntry): Promise<void> {
    if (entry.status !== 'active') {
      return;
    }
    void (await this.getSweetAlert()).fire({
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
      (order.allowed_weekdays && order.allowed_weekdays.length > 0) ||
      (order.excluded_date_ranges?.length ?? 0) > 0,
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
    return this.capitalize(SPANISH_LIST_FORMAT.format(days.map((day) => WEEKDAY_NAMES[day - 1])));
  }

  protected restrictionTimingLabel(order: ServiceOrder): string {
    const limits: string[] = [];
    if (order.minimum_reservation_date) {
      limits.push(`A partir del ${this.formatDate(order.minimum_reservation_date)}`);
    }
    if (order.maximum_reservation_date) {
      limits.push(`Hasta el ${this.formatDate(order.maximum_reservation_date)}`);
    }
    if ((order.excluded_date_ranges?.length ?? 0) > 0) {
      const ranges = order.excluded_date_ranges.map(
        (range) => `${this.formatDate(range.start_date)}–${this.formatDate(range.end_date)}`,
      );
      limits.push(`Excepto ${ranges.join(', ')}`);
    }
    return limits.length ? limits.join(' · ') : 'Sin restricciones de fecha';
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

  protected openInboxCaptchaReview(): void {
    this.showCaptchaWorkspace('review');
    void this.router.navigate(['/captchas'], { queryParams: { mode: 'review' } });
  }

  protected openInboxOrder(order: ServiceOrder): void {
    void this.router.navigate(['/ordenes', order.order_id]);
  }

  protected runInboxOrderTask(task: InboxOrderTask): void {
    if (task.kind === 'preflight') {
      this.selectOrder(task.order.order_id, false);
      this.requestOrderValidation(task.order);
      return;
    }
    if (task.kind === 'contact') {
      void this.openEditOrder(task.order, 'contact');
      return;
    }
    if (task.kind === 'whatsapp') {
      this.selectOrder(task.order.order_id, false);
      void this.openOrderWhatsApp(task.order);
      return;
    }
    if (task.kind === 'payment') {
      void this.openPayment(task.order);
      return;
    }
    if (task.kind === 'review') {
      this.openInboxOrder(task.order);
      return;
    }
    this.selectOrder(task.order.order_id, false);
    void this.openPostPaymentWhatsApp(task.order);
  }

  protected openOrderFromSummary(orderId: string): void {
    void this.router.navigate(['/ordenes', orderId]);
  }

  protected openPaymentFromSummary(orderId: string): void {
    const order = this.orders().find((item) => item.order_id === orderId);
    if (!order) {
      this.openOrderFromSummary(orderId);
      return;
    }
    void this.router.navigate(['/ordenes', orderId]);
    void this.openPayment(order);
  }

  protected selectOrder(orderId: string, loadDetail = true, updateRoute = true): void {
    if (!this.orderPanelOpen()) {
      this.captureFocus();
    }
    this.selectedOrderId.set(orderId);
    this.orderPanelOpen.set(true);
    this.selectedOrderDetail.set(null);
    this.formDirty.set(false);
    this.hydrateSelectedOrderForms();
    if (updateRoute && this.activeView() === 'orders') {
      void this.router.navigate(['/ordenes', orderId]);
    }
    if (loadDetail) {
      void this.loadSelectedOrderDetail(orderId);
    }
    window.setTimeout(() => {
      document.querySelector<HTMLElement>('[data-order-panel]')?.focus();
    });
  }

  protected closeOrderPanel(updateRoute = true): void {
    if (this.activeModal() || this.actionBusy()) {
      return;
    }
    this.orderPanelOpen.set(false);
    this.selectedOrderDetail.set(null);
    this.formDirty.set(false);
    if (updateRoute && this.activeView() === 'orders') {
      void this.router.navigateByUrl('/ordenes');
    }
    this.restoreFocus();
  }

  protected async selectRun(runId: string, updateRoute = true): Promise<void> {
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

  protected closeRunDetail(updateRoute = true): void {
    this.selectedRunId.set('');
    this.selectedRunDetail.set(null);
    this.runDetailError.set(null);
    this.runDetailState.set('idle');
    if (updateRoute && this.activeView() === 'runs') {
      void this.router.navigateByUrl('/actividad');
    }
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

  protected async openEditOrder(
    order: ServiceOrder,
    section: 'all' | 'contact' | 'credentials' | 'restrictions' = 'all',
  ): Promise<void> {
    this.selectOrder(order.order_id, false);
    this.editOrderSection.set(section);
    this.openModal('edit-order');
    await this.loadSelectedOrderDetail(order.order_id);
  }

  protected async openPayment(order: ServiceOrder): Promise<void> {
    this.selectOrder(order.order_id, false);
    this.paymentAmountAgreed.set(order.amount_agreed ?? '50.00');
    this.paymentAmountPaid.set(order.amount_agreed ?? '50.00');
    this.openModal('payment');
    await this.loadSelectedOrderDetail(order.order_id);
    const refreshed = this.selectedOrderDetail();
    if (refreshed?.order_id === order.order_id) {
      this.paymentAmountAgreed.set(refreshed.amount_agreed ?? '50.00');
      this.paymentAmountPaid.set(refreshed.amount_agreed ?? '50.00');
    }
  }

  protected setQuickPaymentAmount(amount: string): void {
    this.editField(this.paymentAmountPaid, amount);
  }

  protected showPendingPayments(): void {
    this.setOrderQuickFilter('payment_pending');
    void this.router.navigateByUrl('/ordenes');
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
    this.whatsappFollowUpPackage.set(null);
    this.whatsappTestRecipient.set('');
    this.whatsappTestMode.set(true);
    this.whatsappFollowUpMode.set(true);
    this.whatsappWebResult.set(null);
    this.whatsappManualFallbackOpen.set(true);
    this.openModal('whatsapp');
  }

  protected openWhatsAppEvidenceTest(): void {
    this.whatsappPackage.set(null);
    this.whatsappFollowUpPackage.set(null);
    this.whatsappTestRecipient.set('');
    this.whatsappTestMode.set(true);
    this.whatsappFollowUpMode.set(false);
    this.whatsappWebResult.set(null);
    this.whatsappManualFallbackOpen.set(true);
    this.openModal('whatsapp');
  }

  protected async validateWhatsAppSession(): Promise<boolean> {
    if (this.whatsappSessionBusy()) {
      return false;
    }
    this.whatsappSessionBusy.set(true);
    this.errorMessage.set(null);
    try {
      for (let attempt = 0; attempt < 3; attempt += 1) {
        const response = await this.api.validateWhatsAppWebSession();
        if (response.status === 'session_ready') {
          this.whatsappSessionState.set('ready');
          await this.showToast('WhatsApp vinculado y listo');
          return true;
        }
        if (response.status !== 'login_required') {
          this.whatsappSessionState.set('error');
          await (await this.getSweetAlert()).fire({
            icon: 'warning',
            title: 'WhatsApp no está disponible',
            text: response.message,
            confirmButtonText: 'Entendido',
          });
          return false;
        }
        this.whatsappSessionState.set('login_required');
        const scanResult = await (await this.getSweetAlert()).fire({
          icon: 'info',
          title: 'Vincular WhatsApp',
          text: response.message,
          imageUrl: response.qr_image_data_url ?? undefined,
          imageAlt: 'Código QR para vincular WhatsApp Web',
          imageWidth: 280,
          imageHeight: 280,
          showCancelButton: true,
          confirmButtonText: 'Comprobar vinculación',
          cancelButtonText: 'Cancelar',
          allowOutsideClick: false,
        });
        if (!scanResult.isConfirmed) {
          return false;
        }
      }
      this.whatsappSessionState.set('error');
      await (await this.getSweetAlert()).fire({
        icon: 'warning',
        title: 'Vinculación pendiente',
        text: 'WhatsApp todavía no confirmó el QR. Vuelve a validar la sesión.',
        confirmButtonText: 'Entendido',
      });
      return false;
    } catch (error) {
      this.whatsappSessionState.set('error');
      this.errorMessage.set(this.readError(error));
      await (await this.getSweetAlert()).fire({
        icon: 'error',
        title: 'No se pudo validar WhatsApp',
        text: this.errorMessage() ?? 'Error desconocido.',
        confirmButtonText: 'Entendido',
      });
      return false;
    } finally {
      this.whatsappSessionBusy.set(false);
    }
  }

  protected async prepareWhatsAppTest(): Promise<void> {
    const recipient = this.whatsappTestRecipient().trim();
    if (!recipient) {
      this.errorMessage.set('Ingresa tu WhatsApp con codigo de pais, por ejemplo +51987654321.');
      return;
    }
    if (this.whatsappFollowUpMode()) {
      await this.loadWhatsAppFollowUpPackage(() =>
        this.api.prepareWhatsAppFollowUpTest(recipient),
      );
      this.whatsappManualFallbackOpen.set(false);
      await this.showToast('Prueba preparada: revisa el contenido antes de enviarlo');
      return;
    }
    await this.loadWhatsAppPackage(() => this.api.prepareWhatsAppTest(recipient));
    this.whatsappManualFallbackOpen.set(false);
    await this.showToast('Prueba preparada: revisa las imágenes y el texto antes de enviarla');
  }

  protected async openOrderWhatsApp(order: ServiceOrder, allowResend = false): Promise<void> {
    this.whatsappPackage.set(null);
    this.whatsappFollowUpPackage.set(null);
    this.whatsappTestMode.set(false);
    this.whatsappFollowUpMode.set(false);
    this.whatsappWebResult.set(null);
    this.whatsappManualFallbackOpen.set(false);
    this.openModal('whatsapp');
    try {
      await this.loadWhatsAppPackage(() =>
        this.api.prepareOrderWhatsApp(order.order_id, allowResend),
      );
      this.whatsappManualFallbackOpen.set(false);
      await this.showToast('Paquete preparado: revisa las imágenes y el texto antes de enviarlo');
    } catch {
      if (!allowResend && order.whatsapp_message_status === 'sent') {
        const result = await (await this.getSweetAlert()).fire({
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

  protected async openPostPaymentWhatsApp(order: ServiceOrder, allowResend = false): Promise<void> {
    this.whatsappPackage.set(null);
    this.whatsappFollowUpPackage.set(null);
    this.whatsappTestMode.set(false);
    this.whatsappFollowUpMode.set(true);
    this.whatsappWebResult.set(null);
    this.whatsappManualFallbackOpen.set(true);
    this.openModal('whatsapp');
    try {
      const message = await this.loadWhatsAppFollowUpPackage(() =>
        this.api.preparePostPaymentWhatsApp(order.order_id, allowResend),
      );
      await this.prepareWhatsAppFollowUpWebDraft(message);
    } catch {
      if (!allowResend && order.whatsapp_followup_status === 'sent') {
        const result = await (await this.getSweetAlert()).fire({
          icon: 'warning',
          title: 'Post-pago ya enviado',
          text: 'Esta orden ya tiene un seguimiento post-pago confirmado. ¿Deseas preparar un reenvio?',
          showCancelButton: true,
          confirmButtonText: 'Preparar reenvio',
          cancelButtonText: 'Cancelar',
        });
        if (result.isConfirmed) {
          await this.openPostPaymentWhatsApp(order, true);
        }
      }
    }
  }

  protected canPrepareOrderWhatsApp(order: ServiceOrder): boolean {
    const baseEligible =
      order.status === 'reserved_payment_pending' &&
      order.reservation_status === 'confirmed' &&
      order.payment_status === 'pending' &&
      !!order.amount_agreed &&
      order.charge_required;
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

  protected canPreparePostPaymentWhatsApp(order: ServiceOrder): boolean {
    if (!this.isPostPaymentWhatsAppCandidate(order)) {
      return false;
    }
    const detail = this.selectedOrderDetail();
    if (!detail || detail.order_id !== order.order_id) {
      return false;
    }
    return /^\+\d{8,15}$/.test(detail.contact_whatsapp ?? '');
  }

  protected postPaymentWhatsAppHint(order: ServiceOrder): string {
    if (!this.isPostPaymentWhatsAppCandidate(order)) {
      return 'Requiere reserva confirmada y pago ya registrado.';
    }
    const detail = this.selectedOrderDetail();
    if (!detail || detail.order_id !== order.order_id) {
      return 'Cargando contacto protegido...';
    }
    if (!/^\+\d{8,15}$/.test(detail.contact_whatsapp ?? '')) {
      return 'Corrige el WhatsApp al formato internacional, por ejemplo +51987654321.';
    }
    return order.whatsapp_followup_status === 'sent'
      ? 'Ya fue enviado; la siguiente accion preparara un reenvio explicito.'
      : 'Listo para preparar indicaciones post-pago y PDFs.';
  }

  protected isPostPaymentWhatsAppCandidate(order: ServiceOrder): boolean {
    return (
      order.status === 'paid' &&
      order.reservation_status === 'confirmed' &&
      order.payment_status === 'paid'
    );
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
    autoSend = false,
  ): Promise<void> {
    const message = preparedMessage ?? this.whatsappPackage();
    if (!message || this.whatsappWebBusy()) {
      return;
    }
    this.whatsappWebBusy.set(true);
    this.errorMessage.set(null);
    try {
      let response = await this.api.prepareWhatsAppWebDraft(
        message.message_id,
        'album',
        autoSend,
      );
      if (response.status === 'login_required') {
        const sessionReady = await this.validateWhatsAppSession();
        if (sessionReady) {
          response = await this.api.prepareWhatsAppWebDraft(
            message.message_id,
            'album',
            autoSend,
          );
        }
      }
      this.whatsappWebResult.set(response);
      this.whatsappManualFallbackOpen.set(response.status === 'web_unavailable');
      if (response.status === 'login_required') {
        this.whatsappSessionState.set('login_required');
      } else if (response.status === 'draft_ready') {
        await this.showToast('WhatsApp preparado: revisa el álbum y pulsa Enviar');
      } else if (response.status === 'sent') {
        this.whatsappPackage.set({
          ...message,
          status: 'sent',
          sent_at: response.sent_at ?? new Date().toISOString(),
        });
        await this.showToast('Constancia y cobro enviados por WhatsApp');
      }
    } catch (error) {
      this.errorMessage.set(this.readError(error));
      this.whatsappManualFallbackOpen.set(true);
    } finally {
      this.whatsappWebBusy.set(false);
    }
  }

  protected async confirmAndSendWhatsAppEvidence(): Promise<void> {
    const message = this.whatsappPackage();
    if (!message || message.status === 'sent' || this.whatsappWebBusy()) {
      return;
    }
    const result = await (await this.getSweetAlert()).fire({
      icon: 'question',
      title: message.test_mode ? 'Enviar prueba de evidencias' : 'Enviar evidencia y cobro',
      text:
        `Se enviarán la constancia, el QR de Yape y el texto combinado a ` +
        `${message.recipient_phone}. WhatsApp realizará un único intento.`,
      showCancelButton: true,
      confirmButtonText: message.test_mode ? 'Enviar prueba ahora' : 'Enviar ahora',
      cancelButtonText: 'Seguir revisando',
      reverseButtons: true,
      focusCancel: true,
    });
    if (!result.isConfirmed) {
      return;
    }
    await this.prepareWhatsAppWebDraft(message, true);
  }

  protected async prepareWhatsAppFollowUpWebDraft(
    preparedMessage?: WhatsAppFollowUpPackage,
  ): Promise<WhatsAppWebDraftResponse | null> {
    const message = preparedMessage ?? this.whatsappFollowUpPackage();
    if (!message || this.whatsappWebBusy()) {
      return null;
    }
    this.whatsappWebBusy.set(true);
    this.errorMessage.set(null);
    try {
      let response = await this.api.prepareWhatsAppFollowUpWebDraft(message.message_id);
      if (response.status === 'login_required') {
        const sessionReady = await this.validateWhatsAppSession();
        if (sessionReady) {
          response = await this.api.prepareWhatsAppFollowUpWebDraft(message.message_id);
        }
      }
      this.whatsappWebResult.set(response);
      this.whatsappManualFallbackOpen.set(response.status === 'web_unavailable');
      if (response.status === 'login_required') {
        this.whatsappSessionState.set('login_required');
      } else if (response.status === 'draft_ready') {
        await this.showToast('Post-pago preparado: revisa WhatsApp y pulsa Enviar');
      } else if (response.status === 'sent') {
        this.whatsappFollowUpPackage.set({
          ...message,
          status: 'sent',
          sent_at: response.sent_at ?? new Date().toISOString(),
        });
        await this.showToast('Post-pago enviado por WhatsApp');
      }
      return response;
    } catch (error) {
      this.errorMessage.set(this.readError(error));
      this.whatsappManualFallbackOpen.set(true);
      return null;
    } finally {
      this.whatsappWebBusy.set(false);
    }
  }

  protected async confirmAndSendWhatsAppFollowUp(): Promise<void> {
    const message = this.whatsappFollowUpPackage();
    if (!message || message.status === 'sent' || this.whatsappWebBusy()) {
      return;
    }
    const documentCount = message.steps.reduce(
      (total, step) => total + step.attachment_urls.length,
      0,
    );
    const result = await (await this.getSweetAlert()).fire({
      icon: 'question',
      title: message.test_mode ? 'Enviar prueba post-pago' : 'Enviar post-pago',
      text:
        `Se enviarán ${documentCount} PDF y el texto post-pago a ` +
        `${message.recipient_phone}. WhatsApp realizará un único intento.`,
      showCancelButton: true,
      confirmButtonText: message.test_mode ? 'Enviar prueba ahora' : 'Enviar ahora',
      cancelButtonText: 'Seguir revisando',
      reverseButtons: true,
      focusCancel: true,
    });
    if (!result.isConfirmed) {
      return;
    }
    await this.prepareWhatsAppFollowUpWebDraft(message);
  }

  protected async confirmWhatsAppSent(): Promise<void> {
    const message = this.whatsappPackage();
    if (!message || message.status === 'sent') {
      return;
    }
    const result = await (await this.getSweetAlert()).fire({
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

  protected async confirmWhatsAppFollowUpSent(): Promise<void> {
    const message = this.whatsappFollowUpPackage();
    if (!message || message.status === 'sent') {
      return;
    }
    const result = await (await this.getSweetAlert()).fire({
      icon: 'question',
      title: 'Confirmar seguimiento',
      text: 'Confirma solo despues de enviar el paquete post-pago en WhatsApp.',
      showCancelButton: true,
      confirmButtonText: 'Si, ya lo envie',
      cancelButtonText: 'Todavia no',
    });
    if (!result.isConfirmed) {
      return;
    }
    this.actionBusy.set(true);
    try {
      const response = await this.api.markWhatsAppFollowUpSent(message.message_id);
      this.whatsappFollowUpPackage.set({
        ...message,
        status: 'sent',
        sent_at: response.sent_at ?? new Date().toISOString(),
      });
      await this.showToast('Seguimiento post-pago registrado');
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
      this.whatsappFollowUpPackage.set(null);
      this.whatsappTestRecipient.set('');
      this.whatsappTestMode.set(false);
      this.whatsappFollowUpMode.set(false);
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
      void this.openPayment(order);
    } else if (action.key === 'post-payment-whatsapp') {
      void this.openPostPaymentWhatsApp(order);
    } else if (action.key === 'review') {
      this.openOrderActions(order);
    }
  }

  protected rowPrimaryActionLabel(order: ServiceOrder): string {
    if (order.payment_status === 'pending') {
      return 'Registrar pago';
    }
    if (
      this.isPostPaymentWhatsAppCandidate(order) &&
      order.whatsapp_followup_action_state !== 'not_applicable'
    ) {
      if (['failed', 'uncertain'].includes(order.whatsapp_followup_action_state)) {
        return 'Revisar post-pago';
      }
      if (['queued', 'blocked', 'running'].includes(order.whatsapp_followup_action_state)) {
        return 'Ver seguimiento';
      }
      return order.whatsapp_followup_status === 'sent' ? 'Reenviar post-pago' : 'Enviar post-pago';
    }
    if (order.status === 'paused') {
      return 'Activar';
    }
    if (order.status === 'ready') {
      return 'Abrir sesión';
    }
    return 'Ver detalle';
  }

  protected runRowPrimaryAction(order: ServiceOrder): void {
    if (order.payment_status === 'pending') {
      void this.openPayment(order);
      return;
    }
    if (
      this.isPostPaymentWhatsAppCandidate(order) &&
      order.whatsapp_followup_action_state !== 'not_applicable'
    ) {
      this.selectOrder(order.order_id);
      if (order.whatsapp_followup_action_state === 'sent') {
        void this.openPostPaymentWhatsApp(order);
      }
      return;
    }
    if (order.status === 'paused') {
      this.selectOrder(order.order_id);
      this.requestOrderAction('activate', 'Activar orden');
    } else if (order.status === 'ready') {
      void this.openManualSessionNow(order);
    } else {
      this.selectOrder(order.order_id);
    }
  }

  protected setQuickPriority(priority: number): void {
    this.orderPriority.set(priority);
    this.requestPriorityUpdate();
  }

  protected priorityExplanation(order: ServiceOrder): string {
    if (order.priority >= 200) {
      return 'Enfoque exclusivo: el worker revisa unicamente esta orden.';
    }
    if (order.priority >= 100) {
      return 'Enfoque prioritario: se atiende antes que la cola normal.';
    }
    return 'Cola normal: mayor numero primero; empate por orden de creacion.';
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
    this.resetOrderPage();
    this.persistOrderViewState();
  }

  protected setOrderFilter(value: string): void {
    this.orderFilter.set(value);
    this.resetOrderPage();
    this.persistOrderViewState();
    try {
      window.sessionStorage.setItem(ORDER_SEARCH_SESSION_KEY, value);
    } catch {
      // La búsqueda permanece disponible en memoria si el navegador bloquea storage.
    }
  }

  protected setOrderSort(key: OrderSortKey): void {
    if (this.orderSortKey() === key) {
      this.orderSortDirection.set(this.orderSortDirection() === 'asc' ? 'desc' : 'asc');
    } else {
      this.orderSortKey.set(key);
      this.orderSortDirection.set(this.defaultOrderSortDirection(key));
    }
    this.resetOrderPage();
    this.persistOrderViewState();
  }

  protected chooseOrderSort(key: OrderSortKey): void {
    if (this.orderSortKey() === key) {
      return;
    }
    this.orderSortKey.set(key);
    this.orderSortDirection.set(this.defaultOrderSortDirection(key));
    this.resetOrderPage();
    this.persistOrderViewState();
  }

  protected toggleOrderSortDirection(): void {
    this.orderSortDirection.set(this.orderSortDirection() === 'asc' ? 'desc' : 'asc');
    this.resetOrderPage();
    this.persistOrderViewState();
  }

  protected changeOrderPageSize(value: number | string): void {
    const pageSize = Number(value);
    if (!ORDER_PAGE_SIZES.includes(pageSize as (typeof ORDER_PAGE_SIZES)[number])) {
      return;
    }
    this.orderPageSize.set(pageSize);
    this.resetOrderPage();
    this.persistOrderViewState();
  }

  protected goToOrderPage(page: number): void {
    if (page < 1 || page > this.orderTotalPages() || page === this.currentOrderPage()) {
      return;
    }
    this.orderPage.set(page);
    this.persistOrderViewState();
    window.requestAnimationFrame(() => {
      document.querySelector('.order-controls')?.scrollIntoView({ behavior: 'smooth' });
    });
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

  protected needsCredentialCorrection(order: ServiceOrder): boolean {
    return order.preflight_details?.['error_type'] === 'invalid_credentials';
  }

  protected toggleOrderPasswordVisibility(): void {
    this.orderPasswordVisible.update((visible) => !visible);
  }

  protected requestCredentialsUpdate(): void {
    if (this.orderDetailLoading()) {
      this.errorMessage.set('Espera a que cargue el detalle protegido de la orden.');
      return;
    }
    const order = this.requireSelectedOrder();
    const detail = this.selectedOrderDetail();
    if (!order || !detail) {
      this.errorMessage.set('No se pudo cargar el acceso actual de la orden.');
      return;
    }
    const documentNumber = this.orderDocumentNumber().trim();
    const password = this.orderPassword();
    if (!documentNumber || !password) {
      this.errorMessage.set('Usuario o documento y nueva contraseña son obligatorios.');
      return;
    }
    const documentChanged = documentNumber !== detail.document_number;
    const message = documentChanged
      ? 'Cambiarás el usuario o documento de acceso. La cuenta y sus subórdenes se pausarán hasta validar la nueva identidad en el portal.'
      : 'Reemplazarás la contraseña. La cuenta y sus subórdenes se pausarán hasta validar nuevamente el acceso al portal.';
    this.setPendingAction({
      title: documentChanged ? 'Cambiar usuario y contraseña' : 'Cambiar contraseña',
      message,
      containsSecret: true,
      execute: () =>
        this.api.updateServiceOrderCredentials(order.order_id, {
          document_number: documentNumber,
          document_type: this.orderDocumentType(),
          password,
        }),
      onSuccess: () => {
        this.orderPassword.set('');
        this.orderPasswordVisible.set(false);
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
    const entersExclusiveMode = order.priority < 200 && priority >= 200;
    const leavesExclusiveMode = order.priority >= 200 && priority < 200;
    const entersFocusedMode = order.priority < 100 && priority >= 100;
    const leavesFocusedMode = order.priority >= 100 && priority < 100;
    const effect = entersExclusiveMode
      ? ' Activara el enfoque exclusivo, limpiara su pausa y cualquier exclusivo anterior volvera a prioridad 100.'
      : leavesExclusiveMode
        ? priority >= 100
          ? ' Saldra del modo exclusivo y conservara el enfoque prioritario.'
          : ' Saldra del modo exclusivo y volvera a la cola normal.'
        : entersFocusedMode
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
    const excludedDateRanges = this.prepareExcludedDateRanges(
      this.orderExcludedDateRanges(),
      this.orderExcludedDateStart(),
      this.orderExcludedDateEnd(),
    );
    if (excludedDateRanges === null) {
      return;
    }
    const payload: ReservationRestrictionsUpdatePayload = {
      minimum_reservation_date: this.optionalText(this.orderMinimumReservationDate()),
      maximum_reservation_date: this.optionalText(this.orderMaximumReservationDate()),
      allowed_weekdays: this.orderAllowedWeekdays().length > 0 ? this.orderAllowedWeekdays() : null,
      excluded_date_ranges: excludedDateRanges,
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
      title: 'Actualizar reglas de reserva',
      message: `Guardar las reglas de reserva de ${order.order_id}. Los campos vacíos quitarán esa regla.`,
      execute: () => this.api.updateServiceOrderRestrictions(order.order_id, payload),
    });
  }

  protected addOrderExcludedDateRange(): void {
    const ranges = this.prepareExcludedDateRanges(
      this.orderExcludedDateRanges(),
      this.orderExcludedDateStart(),
      this.orderExcludedDateEnd(),
    );
    if (ranges === null) {
      return;
    }
    this.orderExcludedDateRanges.set(ranges);
    this.orderExcludedDateStart.set('');
    this.orderExcludedDateEnd.set('');
    this.formDirty.set(true);
  }

  protected removeOrderExcludedDateRange(index: number): void {
    this.orderExcludedDateRanges.update((ranges) =>
      ranges.filter((_, rangeIndex) => rangeIndex !== index),
    );
    this.formDirty.set(true);
  }

  protected clearOrderExcludedDateRanges(): void {
    this.orderExcludedDateRanges.set([]);
    this.formDirty.set(true);
  }

  protected addNewExcludedDateRange(): void {
    const ranges = this.prepareExcludedDateRanges(
      this.newExcludedDateRanges(),
      this.newExcludedDateStart(),
      this.newExcludedDateEnd(),
    );
    if (ranges === null) {
      return;
    }
    this.newExcludedDateRanges.set(ranges);
    this.newExcludedDateStart.set('');
    this.newExcludedDateEnd.set('');
    this.formDirty.set(true);
  }

  protected removeNewExcludedDateRange(index: number): void {
    this.newExcludedDateRanges.update((ranges) =>
      ranges.filter((_, rangeIndex) => rangeIndex !== index),
    );
    this.formDirty.set(true);
  }

  protected clearNewExcludedDateRanges(): void {
    this.newExcludedDateRanges.set([]);
    this.formDirty.set(true);
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

  protected requestOrderValidation(order: ServiceOrder): void {
    this.setPendingAction({
      title: 'Validar acceso',
      message: `Ingresar al portal y validar identidad y programas de ${order.order_id}.`,
      execute: () => this.api.revalidateServiceOrder(order.order_id),
      onSuccess: () => this.activeModal.set(null),
    });
  }

  protected preflightLabel(order: ServiceOrder): string {
    const labels: Record<ServiceOrder['preflight_status'], string> = {
      not_required: 'Sin validación previa',
      pending: 'Validación pendiente',
      running: 'Validando acceso',
      validated: 'Acceso validado',
      failed: 'Validación fallida',
    };
    return labels[order.preflight_status] ?? order.preflight_status;
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
      successMessage: 'Pago registrado; envío automático en proceso',
      onSuccess: () => this.activeModal.set(null),
    });
  }

  protected async copySelectedOrderWhatsapp(): Promise<void> {
    const phone = this.selectedOrderDetail()?.contact_whatsapp;
    if (!phone) {
      return;
    }
    await navigator.clipboard.writeText(phone);
    this.markCopied('whatsapp-number');
  }

  protected openSelectedOrderWhatsapp(): void {
    const digits = this.selectedOrderDetail()?.contact_whatsapp?.replace(/\D/g, '');
    if (digits) {
      window.open(`https://wa.me/${digits}`, '_blank', 'noopener,noreferrer');
    }
  }

  protected requestCreateOrder(): void {
    const excludedDateRanges = this.prepareExcludedDateRanges(
      this.newExcludedDateRanges(),
      this.newExcludedDateStart(),
      this.newExcludedDateEnd(),
    );
    if (excludedDateRanges === null) {
      return;
    }
    const payload: CreateServiceOrderPayload = {
      document_number: this.newDocumentNumber().trim(),
      document_type: this.newDocumentType(),
      password: this.newPassword(),
      contact_whatsapp: this.optionalText(this.newContactWhatsapp()),
      contact_name: this.newContactName().trim(),
      contact_source: this.newContactSource(),
      minimum_reservation_date: this.optionalText(this.newMinimumReservationDate()),
      maximum_reservation_date: this.optionalText(this.newMaximumReservationDate()),
      allowed_weekdays: this.newAllowedWeekdays().length > 0 ? this.newAllowedWeekdays() : null,
      excluded_date_ranges: excludedDateRanges,
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
      !payload.document_type ||
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
      title: 'Reiniciar worker',
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

  protected async copyDashboardSnapshot(): Promise<void> {
    try {
      const workerCommands = await this.api.getWorkerCommands();
      this.workerCommands.set(workerCommands);
      const snapshot = {
        health: this.health(),
        worker: this.sanitizeWorker(this.worker()),
        current_order: this.currentOrder(),
        service_orders: this.filteredOrders().map((order) => this.sanitizeOrder(order)),
        runs: this.filteredRuns().map((run) => this.sanitizeRun(run)),
        worker_commands: workerCommands.map((command) => this.sanitizeWorkerCommand(command)),
      };
      await navigator.clipboard.writeText(JSON.stringify(snapshot, null, 2));
      this.markCopied('snapshot');
    } catch (error) {
      this.errorMessage.set(this.readError(error));
    }
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
      worker && !worker.current_order_id && worker.phase?.startsWith('monitoring_observer'),
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

  protected paymentLabel(order: ServiceOrder): string {
    if (!order.charge_required) {
      return 'Sin cobro';
    }
    return this.statusLabel(order.payment_status, 'Sin pago');
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

  protected statusLabel(
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

  protected statusTone(value: string | boolean | null | undefined): StatusTone {
    if (typeof value === 'boolean') {
      return value ? 'good' : 'bad';
    }
    if (!value) {
      return 'neutral';
    }
    return STATUS_PRESENTATIONS[value.trim().toLowerCase()]?.tone ?? 'neutral';
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
      await this.showToast(action.successMessage ?? `${action.title}: completado`);
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

  private async showToast(title: string): Promise<void> {
    await (await this.getSweetAlert()).fire({
      toast: true,
      position: 'top-end',
      icon: 'success',
      title,
      showConfirmButton: false,
      timer: 2200,
      timerProgressBar: true,
    });
  }

  private getSweetAlert(): Promise<typeof import('sweetalert2').default> {
    this.sweetAlertPromise ??= import('sweetalert2').then((module) => module.default);
    return this.sweetAlertPromise;
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

  private async loadWhatsAppFollowUpPackage(
    load: () => Promise<WhatsAppFollowUpPackage>,
  ): Promise<WhatsAppFollowUpPackage> {
    this.whatsappFollowUpLoading.set(true);
    this.errorMessage.set(null);
    try {
      const message = await load();
      this.whatsappFollowUpPackage.set(message);
      return message;
    } catch (error) {
      this.errorMessage.set(this.readError(error));
      throw error;
    } finally {
      this.whatsappFollowUpLoading.set(false);
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
    if (this.pageHidden() || this.autoRefreshPaused() || this.refreshInFlight) {
      this.scheduleNextRefresh();
      return;
    }
    await this.refreshView(this.activeView(), false);
  }

  private activeRefreshInterval(): number {
    return dashboardRefreshInterval(
      this.activeView(),
      this.captchaWorkspaceMode() as CaptchaRefreshMode,
    );
  }

  private scheduleNextRefresh(): void {
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

  private resetOrderPage(): void {
    this.orderPage.set(1);
  }

  private keepValidOrderPage(): void {
    const validPage = Math.min(this.orderPage(), this.orderTotalPages());
    if (validPage === this.orderPage()) {
      return;
    }
    this.orderPage.set(validPage);
    this.persistOrderViewState();
  }

  private persistOrderViewState(): void {
    const state: OrderViewState = {
      quickFilter: this.orderQuickFilter(),
      sortKey: this.orderSortKey(),
      sortDirection: this.orderSortDirection(),
      page: this.orderPage(),
      pageSize: this.orderPageSize(),
    };
    try {
      window.localStorage.setItem(ORDER_VIEW_STATE_KEY, JSON.stringify(state));
    } catch {
      // El estado sigue funcionando durante la sesión si el navegador bloquea storage.
    }
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
    this.orderDocumentNumber.set(detail?.document_number ?? '');
    this.orderDocumentType.set(order.document_type);
    this.orderPassword.set('');
    this.orderPasswordVisible.set(false);
    this.orderPriority.set(order.priority);
    this.orderMinimumReservationDate.set(order.minimum_reservation_date ?? '');
    this.orderMaximumReservationDate.set(order.maximum_reservation_date ?? '');
    this.orderAllowedWeekdays.set([...(order.allowed_weekdays ?? [])]);
    this.orderExcludedDateRanges.set([...(order.excluded_date_ranges ?? [])]);
    this.orderExcludedDateStart.set('');
    this.orderExcludedDateEnd.set('');
    this.paymentAmountPaid.set(order.amount_paid ?? '');
    this.paymentAmountAgreed.set(order.amount_agreed ?? '');
    this.closureReason.set((order.closure_reason as ClosureReason | null) ?? 'client_withdrew');
    this.closureNote.set(order.closure_note ?? '');
  }

  private clearCreateOrderForm(): void {
    this.newDocumentNumber.set('');
    this.newDocumentType.set('dni');
    this.newPassword.set('');
    this.newContactName.set('');
    this.newContactWhatsapp.set('');
    this.newContactSource.set('');
    this.newMinimumReservationDate.set('');
    this.newMaximumReservationDate.set('');
    this.newAllowedWeekdays.set([]);
    this.newExcludedDateRanges.set([]);
    this.newExcludedDateStart.set('');
    this.newExcludedDateEnd.set('');
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
      exchange_rate_pen: this.financeCurrency() === 'PEN' ? null : this.optionalText(exchangeRate),
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

  private prepareExcludedDateRanges(
    ranges: ExcludedDateRange[],
    startDate: string,
    endDate: string,
  ): ExcludedDateRange[] | null {
    const start = startDate.trim();
    const end = endDate.trim();
    if (!start && !end) {
      return this.normalizeExcludedDateRanges(ranges);
    }
    if (!start || !end) {
      this.errorMessage.set('Completa ambas fechas del rango excluido.');
      return null;
    }
    if (end < start) {
      this.errorMessage.set('El final del rango excluido no puede ser anterior al inicio.');
      return null;
    }
    return this.normalizeExcludedDateRanges([...ranges, { start_date: start, end_date: end }]);
  }

  private normalizeExcludedDateRanges(ranges: ExcludedDateRange[]): ExcludedDateRange[] {
    const sorted = [...ranges].sort((left, right) =>
      left.start_date.localeCompare(right.start_date),
    );
    const merged: ExcludedDateRange[] = [];
    for (const range of sorted) {
      const previous = merged.at(-1);
      if (previous && range.start_date <= previous.end_date) {
        previous.end_date =
          previous.end_date >= range.end_date ? previous.end_date : range.end_date;
        continue;
      }
      merged.push({ ...range });
    }
    return merged;
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
