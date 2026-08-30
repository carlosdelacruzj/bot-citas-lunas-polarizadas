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
  AppointmentReminderStatus,
  AppointmentApiService,
  CaptchaAuthorityControl,
  CaptchaEvent,
  CaptchaEventsPage,
  CaptchaPrediction,
  CaptchaQuality,
  CaptchaQualityCase,
  CaptchaQualityCaseType,
  CaptchaQualityCasesPage,
  CaptchaQualityModel,
  CaptchaQualityWeek,
  CaptchaSamplingControl,
  CaptchaSummary,
  CloseServiceOrderPayload,
  ContactUpdatePayload,
  CreateServiceOrderPayload,
  ExcludedDateRange,
  FinanceCategory,
  FinanceDataQuality,
  FinanceDataQualitySummary,
  FinanceEntry,
  FinanceEntryKind,
  FinanceEntryPayload,
  FinanceSummary,
  FinanceMonthClosure,
  HealthPayload,
  ManualSession,
  ManualSessionMode,
  MetricPeriod,
  MonthlySummaryV2,
  OperatorInboxPayload,
  OperatorInboxTask,
  PaymentResolutionType,
  OpportunityBurst,
  OpportunityControl,
  OpportunityControlAction,
  OpportunityControlTarget,
  PaymentPaidPayload,
  PostAppointmentFollowup,
  PostAppointmentPayload,
  PostAppointmentQuery,
  PriorityUpdatePayload,
  ReservationRestrictionsUpdatePayload,
  RunDetail,
  RunSummary,
  ServiceOrder,
  ServiceOrderDetail,
  WorkerCommand,
  WorkerStatus,
  WhatsAppFollowUpPackage,
  WhatsAppMessageTemplate,
  WhatsAppMessagePackage,
  WhatsAppReviewPayload,
  WhatsAppReviewResolution,
  WhatsAppWebDraftResponse,
  apiErrorMessage,
} from './appointment-api.service';
import {
  formatPeruDate,
  formatPeruDateTime,
  formatPeruTime,
  peruDateTimeSortValue,
} from './peru-date-time';
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
type NewServicePackage = 'standard' | 'restricted' | 'custom';
type ViewKey =
  | 'inbox'
  | 'summary'
  | 'finance'
  | 'messageTemplates'
  | 'orders'
  | 'followups'
  | 'runs'
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
type PostAppointmentFilter =
  | 'active'
  | 'attention'
  | 'observations'
  | 'access_lost'
  | 'progressed'
  | 'history';
type PostAppointmentSortKey = 'priority' | 'appointment_date' | 'last_reviewed_at' | 'applicant';
type ClosureReason =
  | 'completed_by_us'
  | 'family_no_charge'
  | 'client_withdrew'
  | 'external_slot'
  | 'duplicate'
  | 'not_serviceable'
  | 'uncollectible';
type SortDirection = 'asc' | 'desc';
type StatusTone = 'good' | 'warn' | 'bad' | 'neutral';
type StatusPresentation = { label: string; tone: StatusTone };
type DashboardSnapshotHealth = Pick<
  HealthPayload,
  'status' | 'worker_running' | 'reason' | 'captcha_shadow_enabled'
>;
type DashboardSnapshotWorker = Pick<
  WorkerStatus,
  | 'phase'
  | 'paused'
  | 'current_order_id'
  | 'session_started_at'
  | 'last_check_at'
  | 'next_check_at'
  | 'confirmed_reservations'
  | 'consecutive_errors'
  | 'updated_at'
  | 'worker_running'
  | 'continuous_worker_enabled'
>;
type DashboardSnapshotOrder = Pick<
  ServiceOrder,
  | 'order_id'
  | 'priority'
  | 'charge_required'
  | 'service_type'
  | 'status'
  | 'reservation_status'
  | 'payment_status'
  | 'whatsapp_message_action_state'
  | 'whatsapp_followup_action_state'
  | 'parent_order_id'
  | 'preflight_status'
  | 'registration_notice_status'
  | 'created_at'
  | 'updated_at'
>;
type DashboardSnapshotRun = Pick<
  RunSummary,
  | 'run_id'
  | 'order_id'
  | 'status'
  | 'exit_code'
  | 'started_at'
  | 'finished_at'
  | 'duration_seconds'
  | 'reservation_attempted'
  | 'reservation_confirmed'
  | 'screenshot_count'
>;
type DashboardSnapshotWorkerCommand = Pick<
  WorkerCommand,
  'command_id' | 'command' | 'status' | 'requested_at' | 'claimed_at' | 'processed_at'
>;
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
  successMessage?: string | ((response: ApiActionResponse) => string);
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
type InboxOrderTask = {
  key: OperatorInboxTask['key'];
  kind: OperatorInboxTask['kind'];
  action: OperatorInboxTask['action'];
  orderId: string;
  applicantName: string | null;
  documentNumberMasked: string;
  title: string;
  description: string;
  label: string;
  actionLabel: string;
  icon: string;
  tone: 'bad' | 'warn' | 'neutral';
  updatedAt: string;
};

const ERROR_MESSAGE_DURATION_MS = 8_000;
const ORDER_VIEW_STATE_KEY = 'appointment-dashboard-order-view';
const ORDER_SEARCH_SESSION_KEY = 'appointment-dashboard-order-search';
const ORDER_PAGE_SIZES = [10, 20, 50] as const;
const POST_APPOINTMENT_PAGE_SIZES = [5, 10, 20] as const;
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
  blocked: { label: 'Bloqueado', tone: 'warn' },
  cancelled: { label: 'Cancelado', tone: 'neutral' },
  claimed: { label: 'En proceso', tone: 'warn' },
  closing: { label: 'Cerrando', tone: 'warn' },
  closed: { label: 'Cerrado', tone: 'neutral' },
  completed: { label: 'Completado', tone: 'good' },
  observation_with_progress: { label: 'Observación con avance', tone: 'warn' },
  observation_no_progress: { label: 'Observación sin avance', tone: 'bad' },
  awaiting_update: { label: 'Esperando actualización', tone: 'warn' },
  in_progress: { label: 'En progreso', tone: 'good' },
  upcoming: { label: 'Cita próxima', tone: 'neutral' },
  access_lost: { label: 'Archivado · acceso perdido', tone: 'neutral' },
  portal_unavailable: { label: 'Portal no disponible', tone: 'bad' },
  review_required: { label: 'Revisión pendiente', tone: 'warn' },
  not_checked: { label: 'Aún no revisado', tone: 'neutral' },
  confirmed: { label: 'Confirmada', tone: 'good' },
  degraded: { label: 'Degradado', tone: 'bad' },
  draft_ready: { label: 'Borrador preparado', tone: 'warn' },
  error: { label: 'Error', tone: 'bad' },
  estimated: { label: 'Estimado', tone: 'warn' },
  failed: { label: 'Fallido', tone: 'bad' },
  family_no_charge: { label: 'Familiar sin cobro', tone: 'warn' },
  invalid_credentials: { label: 'Credenciales rechazadas', tone: 'bad' },
  login_required: { label: 'Requiere vinculación', tone: 'warn' },
  mixed: { label: 'Mixto', tone: 'warn' },
  monitoring_started: { label: 'Monitoreo iniciado', tone: 'good' },
  no_pending_request: { label: 'Sin solicitud pendiente', tone: 'warn' },
  not_required: { label: 'No requerido', tone: 'neutral' },
  ok: { label: 'Correcto', tone: 'good' },
  opening: { label: 'Abriendo', tone: 'warn' },
  outside_hot_window: { label: 'Fuera de horario', tone: 'warn' },
  paid: { label: 'Pagado', tone: 'good' },
  partial: { label: 'Parcial', tone: 'warn' },
  paused: { label: 'Pausada', tone: 'warn' },
  pending: { label: 'Pendiente', tone: 'warn' },
  prepared: { label: 'Preparado', tone: 'warn' },
  queued: { label: 'En cola', tone: 'warn' },
  session_ready: { label: 'WhatsApp listo', tone: 'good' },
  ready: { label: 'Lista', tone: 'good' },
  registered: { label: 'Registrada', tone: 'good' },
  rejected: { label: 'Rechazado', tone: 'bad' },
  reservation_unconfirmed: { label: 'Reserva sin confirmar', tone: 'bad' },
  reserved_payment_pending: { label: 'Reservada, pago pendiente', tone: 'warn' },
  resolved: { label: 'Conciliado manualmente', tone: 'neutral' },
  running: { label: 'En ejecución', tone: 'warn' },
  sent: { label: 'Enviado', tone: 'good' },
  uncertain: { label: 'Envío incierto', tone: 'bad' },
  unknown: { label: 'Desconocido', tone: 'bad' },
  unavailable: { label: 'Sin disponibilidad', tone: 'neutral' },
  validated: { label: 'Validado', tone: 'good' },
  voided: { label: 'Anulado', tone: 'neutral' },
  written_off: { label: 'Incobrable', tone: 'neutral' },
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
  followups: { label: 'Citas y recordatorios', group: 'Operación' },
  runs: { label: 'Runs y actividad', group: 'Operación' },
  finance: { label: 'Finanzas', group: 'Administración' },
  messageTemplates: { label: 'Mensajes de WhatsApp', group: 'Administración' },
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

function compareOptionalTimestamps(
  left: number | null,
  right: number | null,
  direction: number,
): number {
  if (left === null && right === null) {
    return 0;
  }
  if (left === null) {
    return 1;
  }
  if (right === null) {
    return -1;
  }
  return (left - right) * direction;
}

function normalizeDashboardText(value: unknown): string {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .trim()
    .toLocaleLowerCase('es');
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
  public readonly formatDate = formatPeruDate;
  public readonly formatDateTime = formatPeruDateTime;
  public readonly formatTime = formatPeruTime;
  private readonly api = inject(AppointmentApiService);
  private readonly router = inject(Router);
  private autoRefreshTimer: number | null = null;
  private postAppointmentSearchTimer: number | null = null;
  private postAppointmentRequestScope: RequestScope | null = null;
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
  public readonly orderFilter = signal(readOrderSearch());
  public readonly orderQuickFilter = signal<OrderQuickFilter>(
    INITIAL_ORDER_VIEW_STATE.quickFilter,
  );
  public readonly orderSortKey = signal<OrderSortKey>(INITIAL_ORDER_VIEW_STATE.sortKey);
  public readonly orderSortDirection = signal<SortDirection>(
    INITIAL_ORDER_VIEW_STATE.sortDirection,
  );
  public readonly orderPage = signal(INITIAL_ORDER_VIEW_STATE.page);
  public readonly orderPageSize = signal(INITIAL_ORDER_VIEW_STATE.pageSize);
  public readonly runStatusFilter = signal('');
  public readonly health = signal<HealthPayload | null>(null);
  public readonly worker = signal<WorkerStatus | null>(null);
  public readonly opportunityControl = signal<OpportunityControl | null>(null);
  public readonly opportunityBursts = signal<OpportunityBurst[]>([]);
  public readonly captchaAuthorityControl = signal<CaptchaAuthorityControl | null>(null);
  public readonly captchaSamplingControl = signal<CaptchaSamplingControl | null>(null);
  public readonly captchaSamplingEnabled = signal(false);
  public readonly captchaSamplingLimit = signal(10);
  public readonly captchaSamplingDirty = signal(false);
  public readonly captchaSamplingSaving = signal(false);
  public readonly orders = signal<ServiceOrder[]>([]);
  public readonly operatorInbox = signal<OperatorInboxPayload | null>(null);
  public readonly runs = signal<RunSummary[]>([]);
  public readonly postAppointmentPayload = signal<PostAppointmentPayload | null>(null);
  public readonly reviewingPostAppointmentOrderIds = signal<ReadonlySet<string>>(new Set());
  public readonly postAppointmentFilter = signal<PostAppointmentFilter>('active');
  public readonly postAppointmentSearch = signal('');
  public readonly postAppointmentSortKey = signal<PostAppointmentSortKey>('priority');
  public readonly postAppointmentSortDirection = signal<SortDirection>('asc');
  public readonly postAppointmentPage = signal(1);
  public readonly postAppointmentPageSize = signal(10);
  public readonly captchaSummary = signal<CaptchaSummary | null>(null);
  public readonly captchaEvents = signal<CaptchaEvent[]>([]);
  public readonly captchaReviewQueue = signal<CaptchaEvent[]>([]);
  public readonly captchaReviewTotal = signal(0);
  public readonly captchaPendingTotal = signal(0);
  public readonly captchaReviewPosition = signal(0);
  public readonly captchaWorkspaceMode = signal<CaptchaWorkspaceMode>('review');
  public readonly captchaHistoryFiltersOpen = signal(false);
  public readonly captchaState = signal<LoadState>('idle');
  public readonly captchaError = signal<string | null>(null);
  public readonly captchaPage = signal(1);
  public readonly captchaPageSize = signal(12);
  public readonly captchaTotal = signal(0);
  public readonly captchaTotalPages = signal(1);
  public readonly captchaSearch = signal('');
  public readonly captchaAgreement = signal<CaptchaAgreementFilter>('all');
  public readonly captchaPortalStatus = signal<CaptchaPortalFilter>('all');
  public readonly captchaSource = signal<CaptchaSourceFilter>('all');
  public readonly captchaReviewStatus = signal<CaptchaReviewFilter>('all');
  public readonly captchaDrafts = signal<Record<string, string>>({});
  public readonly captchaSavingEventId = signal('');
  public readonly captchaReviewMessage = signal<string | null>(null);
  public readonly captchaPendingCorrection = signal<CaptchaPendingCorrection | null>(null);
  public readonly captchaShadowEnabled = computed(
    () => this.health()?.captcha_shadow_enabled === true,
  );
  public readonly captchaQuality = signal<CaptchaQuality | null>(null);
  public readonly captchaQualityCases = signal<CaptchaQualityCasesPage | null>(null);
  public readonly captchaQualityState = signal<LoadState>('idle');
  public readonly captchaQualityError = signal<string | null>(null);
  public readonly captchaQualityCaseType = signal<CaptchaQualityCaseType>('wrong');
  public readonly captchaQualityCasePage = signal(1);
  public readonly captchaQualityCasePageSize = signal(12);
  public readonly captchaDatasetExporting = signal(false);
  public readonly captchaQualityCaseFilters = CAPTCHA_QUALITY_CASE_FILTERS;
  public readonly activeCaptchaReview = computed(
    () => this.captchaReviewQueue()[this.captchaReviewPosition()] ?? null,
  );
  public readonly selectedRunId = signal('');
  public readonly selectedRunDetail = signal<RunDetail | null>(null);
  public readonly runDetailState = signal<LoadState>('idle');
  public readonly runDetailError = signal<string | null>(null);
  public readonly workerCommands = signal<WorkerCommand[]>([]);
  public readonly releaseSafeBackoffsOnRestart = signal(false);
  public readonly manualSessions = signal<ManualSession[]>([]);
  public readonly closingManualSessionIds = signal<ReadonlySet<string>>(new Set());
  public readonly selectedMonth = signal(INITIAL_MONTH);
  public readonly monthlySummary = signal<MonthlySummaryV2 | null>(null);
  public readonly appointmentReminderStatus = signal<AppointmentReminderStatus | null>(null);
  public readonly whatsappMessageTemplates = signal<WhatsAppMessageTemplate[]>([]);
  public readonly monthlyLoading = signal(false);
  public readonly financeCategories = signal<FinanceCategory[]>([]);
  public readonly financeEntries = signal<FinanceEntry[]>([]);
  public readonly financeSummary = signal<FinanceSummary | null>(null);
  public readonly financeQuality = signal<FinanceDataQualitySummary | null>(null);
  public readonly financeMonthClosure = signal<FinanceMonthClosure | null>(null);
  public readonly financeLoading = signal(false);
  public readonly financeClosureOpeningBalance = signal('');
  public readonly financeClosureClosingBalance = signal('');
  public readonly financeClosureReconciledBy = signal('');
  public readonly financeClosureNotes = signal('');
  public readonly financeMismatchPaymentId = signal('');
  public readonly financeMismatchResolution = signal<PaymentResolutionType>('discount');
  public readonly financeMismatchReason = signal('');
  public readonly financeMismatchReconciledBy = signal('');
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
  public readonly loadState = signal<LoadState>('idle');
  public readonly viewLoadError = signal<string | null>(null);
  public readonly refreshingViewState = signal<ViewKey | null>(null);
  public readonly errorMessage = signal<string | null>(null);
  public readonly copiedLabel = signal<string | null>(null);
  public readonly selectedOrderId = signal('');
  public readonly orderPanelOpen = signal(false);
  public readonly selectedOrderDetail = signal<ServiceOrderDetail | null>(null);
  public readonly orderDetailLoading = signal(false);
  public readonly contactName = signal('');
  public readonly contactWhatsapp = signal('');
  public readonly contactWhatsappUsername = signal('');
  public readonly contactSource = signal('whatsapp');
  public readonly orderDocumentNumber = signal('');
  public readonly orderDocumentType = signal<'dni' | 'foreign_resident_card'>('dni');
  public readonly orderPassword = signal('');
  public readonly orderPasswordVisible = signal(false);
  public readonly orderPriority = signal(0);
  public readonly orderMinimumReservationDate = signal('');
  public readonly orderMaximumReservationDate = signal('');
  public readonly orderAllowedWeekdays = signal<number[]>([]);
  public readonly orderExcludedDateRanges = signal<ExcludedDateRange[]>([]);
  public readonly orderExcludedDateStart = signal('');
  public readonly orderExcludedDateEnd = signal('');
  public readonly paymentAmountPaid = signal('');
  public readonly paymentAmountAgreed = signal('');
  public readonly editOrderSection = signal<
    'all' | 'contact' | 'credentials' | 'restrictions'
  >('all');
  public readonly newDocumentNumber = signal('');
  public readonly newDocumentType = signal<'dni' | 'foreign_resident_card'>('dni');
  public readonly newPassword = signal('');
  public readonly newContactName = signal('');
  public readonly newContactWhatsapp = signal('');
  public readonly newContactWhatsappUsername = signal('');
  public readonly newContactSource = signal('');
  public readonly newServicePackage = signal<NewServicePackage>('standard');
  public readonly newCustomReservationPrice = signal('');
  public readonly newMinimumReservationDate = signal('');
  public readonly newMaximumReservationDate = signal('');
  public readonly newAllowedWeekdays = signal<number[]>([]);
  public readonly newExcludedDateRanges = signal<ExcludedDateRange[]>([]);
  public readonly newExcludedDateStart = signal('');
  public readonly newExcludedDateEnd = signal('');
  public readonly splitKeepParentActive = signal(false);
  public readonly closureReason = signal<ClosureReason>('client_withdrew');
  public readonly closureNote = signal('');
  public readonly actionBusy = signal(false);
  public readonly pendingAction = signal<PendingAction | null>(null);
  public readonly whatsappPackage = signal<WhatsAppMessagePackage | null>(null);
  public readonly whatsappFollowUpPackage = signal<WhatsAppFollowUpPackage | null>(null);
  public readonly whatsappPackageLoading = signal(false);
  public readonly whatsappFollowUpLoading = signal(false);
  public readonly whatsappTestRecipient = signal('');
  public readonly whatsappTestMode = signal(false);
  public readonly whatsappFollowUpMode = signal(false);
  public readonly whatsappReviewMode = signal(false);
  public readonly whatsappReview = signal<WhatsAppReviewPayload | null>(null);
  public readonly whatsappReviewNote = signal('');
  public readonly whatsappWebBusy = signal(false);
  public readonly whatsappWebResult = signal<WhatsAppWebDraftResponse | null>(null);
  public readonly whatsappManualFallbackOpen = signal(false);
  public readonly whatsappSessionBusy = signal(false);
  public readonly whatsappSessionState = signal<
    'unknown' | 'ready' | 'login_required' | 'error'
  >('unknown');

  public readonly selectedOrder = computed(() => {
    const selected = this.selectedOrderId();
    return this.orders().find((order) => order.order_id === selected) ?? this.orders()[0] ?? null;
  });
  public readonly latestOpportunityBurst = computed(
    () => this.opportunityBursts()[0] ?? null,
  );
  public readonly currentOrder = computed(() => {
    const currentOrderId = this.worker()?.current_order_id;
    return this.orders().find((order) => order.order_id === currentOrderId) ?? null;
  });
  public readonly modalOrder = computed(() => this.selectedOrder());
  public readonly filteredOrders = computed(() => {
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
  public readonly orderTotalPages = computed(() =>
    Math.max(1, Math.ceil(this.filteredOrders().length / this.orderPageSize())),
  );
  public readonly currentOrderPage = computed(() =>
    Math.min(this.orderPage(), this.orderTotalPages()),
  );
  public readonly paginatedOrders = computed(() => {
    const start = (this.currentOrderPage() - 1) * this.orderPageSize();
    return this.filteredOrders().slice(start, start + this.orderPageSize());
  });
  public readonly orderPageStart = computed(() =>
    this.filteredOrders().length ? (this.currentOrderPage() - 1) * this.orderPageSize() + 1 : 0,
  );
  public readonly orderPageEnd = computed(() =>
    Math.min(this.currentOrderPage() * this.orderPageSize(), this.filteredOrders().length),
  );
  public readonly orderPageNumbers = computed(() =>
    paginationWindow(this.currentOrderPage(), this.orderTotalPages()),
  );
  public readonly orderQuickFilters = computed(() => [
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
  public readonly captchaPageNumbers = computed(() => {
    return paginationWindow(this.captchaPage(), this.captchaTotalPages());
  });
  public readonly captchaQualityBestModel = computed<CaptchaQualityModel | null>(() => {
    return [...(this.captchaQuality()?.models ?? [])]
      .filter((model) => model.accuracy !== null)
      .sort(
        (left, right) =>
          (right.accuracy ?? 0) - (left.accuracy ?? 0) || right.evaluated - left.evaluated,
      )[0] ?? null;
  });
  public readonly captchaQualityCasePageNumbers = computed(() => {
    const pagination = this.captchaQualityCases()?.pagination;
    return pagination ? paginationWindow(pagination.page, pagination.total_pages) : [];
  });
  public readonly readyOrders = computed(
    () => this.orders().filter((order) => order.status === 'ready').length,
  );
  public readonly captchaSamplingEffectiveLimit = computed(() =>
    this.captchaSamplingEnabled() ? this.captchaSamplingLimit() : 1,
  );
  public readonly captchaSamplingEstimatedSeconds = computed(() =>
    Math.round(Math.max(this.captchaSamplingEffectiveLimit() - 1, 0) * 4) / 10,
  );
  public readonly captchaAuthorityUsesV6 = computed(() => {
    const control = this.captchaAuthorityControl();
    return Boolean(
      control?.mode === 'canary' &&
        control.circuit_state === 'closed' &&
        control.remaining_local_decisions > 0,
    );
  });
  public readonly pendingPaymentOrders = computed(
    () => this.orders().filter((order) => order.payment_status === 'pending').length,
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
  public readonly confirmedOrders = computed(
    () => this.orders().filter((order) => order.reservation_status === 'confirmed').length,
  );
  public readonly postAppointmentItems = computed(
    () => this.postAppointmentPayload()?.items ?? [],
  );
  public readonly postAppointmentQuickFilters = computed(() => {
    const counts = this.postAppointmentPayload()?.filter_counts;
    return [
      {
        key: 'active' as const,
        label: 'En seguimiento',
        count: counts?.active ?? 0,
      },
      {
        key: 'attention' as const,
        label: 'Requieren atención',
        count: counts?.attention ?? 0,
      },
      {
        key: 'observations' as const,
        label: 'Con observación',
        count: counts?.observations ?? 0,
      },
      {
        key: 'access_lost' as const,
        label: 'Historial sin acceso',
        count: counts?.access_lost ?? 0,
      },
      {
        key: 'progressed' as const,
        label: 'Con avance',
        count: counts?.progressed ?? 0,
      },
    ];
  });
  public readonly postAppointmentTotalPages = computed(() =>
    Math.max(
      1,
      Math.ceil(
        (this.postAppointmentPayload()?.pagination.total ?? 0) /
          this.postAppointmentPageSize(),
      ),
    ),
  );
  public readonly currentPostAppointmentPage = computed(() =>
    Math.min(this.postAppointmentPage(), this.postAppointmentTotalPages()),
  );
  public readonly paginatedPostAppointmentItems = computed(() => this.postAppointmentItems());
  public readonly postAppointmentPageStart = computed(() =>
    (this.postAppointmentPayload()?.pagination.total ?? 0) > 0
      ? (this.postAppointmentPayload()?.pagination.offset ?? 0) + 1
      : 0,
  );
  public readonly postAppointmentPageEnd = computed(() =>
    (this.postAppointmentPayload()?.pagination.offset ?? 0) +
      this.postAppointmentItems().length,
  );
  public readonly postAppointmentPageNumbers = computed(() =>
    paginationWindow(this.currentPostAppointmentPage(), this.postAppointmentTotalPages()),
  );
  public readonly failedRuns = computed(
    () => this.runs().filter((run) => this.statusTone(run.status) === 'bad').length,
  );
  public readonly selectedOrderChildren = computed(() => {
    const orderId = this.selectedOrder()?.order_id;
    return orderId ? this.orders().filter((order) => order.parent_order_id === orderId) : [];
  });
  public readonly orderNextAction = computed<OrderNextAction>(() => {
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
      if (order.whatsapp_followup_action_state === 'resolved') {
        return {
          key: 'none',
          label: 'Post-pago conciliado',
          description: 'El operador cerró este resultado y ya no requiere atención.',
          disabled: true,
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
  public readonly selectedRun = computed(() => this.selectedRunDetail());
  public readonly selectedOrderWhatsappPlaceholder = computed(
    () => this.selectedOrder()?.contact_whatsapp_masked ?? 'sin numero registrado',
  );
  public readonly selectedOrderWhatsapp = computed(() => {
    const order = this.selectedOrder();
    const detail = this.selectedOrderDetail();
    if (order && detail?.order_id === order.order_id) {
      return detail.contact_whatsapp ?? detail.contact_whatsapp_username ?? 'sin WhatsApp';
    }
    return order?.contact_whatsapp_masked ?? order?.contact_whatsapp_username_masked ?? 'sin WhatsApp';
  });
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
      return this.monthlySummary() !== null;
    }
    if (view === 'finance') {
      return this.financeSummary() !== null;
    }
    if (view === 'messageTemplates') {
      return this.whatsappMessageTemplates().length > 0 || state === 'ready';
    }
    if (view === 'orders') {
      return this.orders().length > 0 || state === 'ready';
    }
    if (view === 'runs') {
      return this.runs().length > 0 || this.workerCommands().length > 0 || state === 'ready';
    }
    if (view === 'followups') {
      return this.postAppointmentPayload() !== null;
    }
    if (view === 'captchas') {
      return this.captchaSummary() !== null;
    }
    return this.orders().length > 0 || state === 'ready';
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
    if (this.postAppointmentSearchTimer !== null) {
      window.clearTimeout(this.postAppointmentSearchTimer);
    }
    this.postAppointmentRequestScope?.cancel();
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
  public handleBeforeUnload(): void {
    this.closeTrackedManualSessionsWithBeacon();
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
    if (this.orderPanelOpen()) {
      this.closeOrderPanel();
    }
  }

  @HostListener('document:keydown', ['$event'])
  public handleCaptchaReviewKeyboard(event: KeyboardEvent): void {
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
      if (view === 'inbox' || view === 'captchas') {
        await this.refreshCommonData(scope);
        if (view === 'captchas' && !this.captchaShadowEnabled()) {
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
      const inboxRequest = this.api.getOperatorInbox(scope);
      if (!this.captchaShadowEnabled()) {
        this.operatorInbox.set(await inboxRequest);
        this.captchaReviewTotal.set(0);
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
        this.captchaReviewTotal.set(pendingCaptchas.pagination.total);
      }
      return;
    }
    if (view === 'summary') {
      const [
        orders,
        runs,
        monthlySummary,
        captchaSamplingControl,
        captchaAuthorityControl,
        opportunityControl,
        opportunityBursts,
        appointmentReminderStatus,
      ] = await Promise.all([
        this.api.getServiceOrders(scope),
        this.api.getRuns(scope),
        this.api.getMonthlySummaryV2(this.selectedMonth(), scope),
        this.api.getCaptchaSamplingControl(scope),
        this.api.getCaptchaAuthorityControl(scope),
        this.api.getOpportunityControl(scope),
        this.api.getOpportunityBursts(scope),
        this.api.getAppointmentReminders(scope),
      ]);
      this.applyOrders(orders);
      this.runs.set(runs);
      this.monthlySummary.set(monthlySummary);
      this.applyCaptchaSamplingControl(captchaSamplingControl);
      this.captchaAuthorityControl.set(captchaAuthorityControl);
      this.opportunityControl.set(opportunityControl);
      this.opportunityBursts.set(opportunityBursts.bursts);
      this.appointmentReminderStatus.set(appointmentReminderStatus);
      return;
    }
    if (view === 'finance') {
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
    if (view === 'messageTemplates') {
      this.whatsappMessageTemplates.set(await this.api.getWhatsAppMessageTemplates(scope));
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
    if (view === 'followups') {
      this.setPostAppointmentPayload(
        await this.api.getPostAppointmentFollowups(this.postAppointmentQuery(true), scope),
      );
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

  public toggleSidebar(): void {
    const collapsed = !this.sidebarCollapsed();
    this.sidebarCollapsed.set(collapsed);
    window.localStorage.setItem('appointment-dashboard-sidebar-collapsed', String(collapsed));
  }

  public async loadCaptchaData(showLoading = true, scope?: RequestScope): Promise<void> {
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
        this.captchaPendingTotal.set(
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
          'all',
          activeScope,
        ),
        this.api.getCaptchaEvents(
          1, 48, '', 'all', 'all', 'all', 'pending', 'review_priority', 'targeted', activeScope,
        ),
      ]);
      this.captchaSummary.set(summary);
      this.captchaPendingTotal.set(
        Math.max(0, summary.stats.events - summary.stats.human_labeled),
      );
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

  public async loadCaptchaQuality(scope?: RequestScope): Promise<void> {
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

  public async changeCaptchaQualityCaseType(value: CaptchaQualityCaseType): Promise<void> {
    if (value === this.captchaQualityCaseType()) {
      return;
    }
    this.captchaQualityCaseType.set(value);
    this.captchaQualityCasePage.set(1);
    await this.loadCaptchaQualityCases();
  }

  public async goToCaptchaQualityCasePage(page: number): Promise<void> {
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

  public async exportCaptchaDataset(): Promise<void> {
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

  public async applyCaptchaFilters(): Promise<void> {
    this.captchaPage.set(1);
    await this.loadCaptchaData();
  }

  public async setCaptchaAgreement(filter: CaptchaAgreementFilter): Promise<void> {
    if (this.captchaAgreement() === filter) {
      return;
    }
    this.captchaAgreement.set(filter);
    await this.applyCaptchaFilters();
  }

  public async changeCaptchaPortalStatus(value: CaptchaPortalFilter): Promise<void> {
    this.captchaPortalStatus.set(value);
    await this.applyCaptchaFilters();
  }

  public async changeCaptchaSource(value: CaptchaSourceFilter): Promise<void> {
    this.captchaSource.set(value);
    await this.applyCaptchaFilters();
  }

  public async changeCaptchaReviewStatus(value: CaptchaReviewFilter): Promise<void> {
    this.captchaReviewStatus.set(value);
    await this.applyCaptchaFilters();
  }

  public showCaptchaWorkspace(mode: CaptchaWorkspaceMode): void {
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

  public showAllPendingCaptchas(): void {
    this.captchaReviewStatus.set('pending');
    this.captchaPage.set(1);
    this.showCaptchaWorkspace('history');
  }

  public toggleCaptchaHistoryFilters(): void {
    this.captchaHistoryFiltersOpen.update((open) => !open);
  }

  public captchaActiveFilterCount(): number {
    return (
      Number(this.captchaAgreement() !== 'all') +
      Number(this.captchaPortalStatus() !== 'all') +
      Number(this.captchaSource() !== 'all')
    );
  }

  public moveCaptchaReview(offset: number): void {
    const next = this.captchaReviewPosition() + offset;
    if (next < 0 || next >= this.captchaReviewQueue().length) {
      return;
    }
    this.captchaReviewPosition.set(next);
    this.captchaPendingCorrection.set(null);
    this.clearCaptchaReviewMessage();
  }

  public async changeCaptchaPageSize(value: number | string): Promise<void> {
    this.captchaPageSize.set(Number(value));
    await this.applyCaptchaFilters();
  }

  public async goToCaptchaPage(page: number): Promise<void> {
    if (page < 1 || page > this.captchaTotalPages() || page === this.captchaPage()) {
      return;
    }
    this.captchaPage.set(page);
    await this.loadCaptchaData();
  }

  public captchaPrediction(event: CaptchaEvent, modelName: string): CaptchaPrediction | null {
    return event.predictions.find((prediction) => prediction.model_name === modelName) ?? null;
  }

  public captchaPredictionTone(event: CaptchaEvent, prediction: CaptchaPrediction): string {
    const reference = event.human_label?.answer ?? event.external_answer;
    if (!reference) {
      return 'neutral';
    }
    return prediction.prediction === reference ? 'good' : 'warn';
  }

  public captchaPortalLabel(event: CaptchaEvent): string {
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

  public captchaPortalTone(event: CaptchaEvent): string {
    if (event.portal_accepted === true) {
      return 'good';
    }
    if (event.portal_accepted === false) {
      return 'bad';
    }
    return 'neutral';
  }

  public captchaAgreementLabel(event: CaptchaEvent): string {
    if (this.isObserverCaptcha(event)) {
      return event.predictions.length ? 'Solo modelos locales' : 'Inferencia pendiente';
    }
    if (
      !event.external_answer ||
      !event.selected_model_name ||
      !this.captchaPrediction(event, event.selected_model_name)
    ) {
      return 'Comparación pendiente';
    }
    return event.selected_matches_external ? 'Coincide con 2Captcha' : 'Difiere de 2Captcha';
  }

  public captchaAgreementTone(event: CaptchaEvent): string {
    if (this.isObserverCaptcha(event)) {
      return event.predictions.length ? 'good' : 'neutral';
    }
    if (
      !event.external_answer ||
      !event.selected_model_name ||
      !this.captchaPrediction(event, event.selected_model_name)
    ) {
      return 'neutral';
    }
    return event.selected_matches_external ? 'good' : 'warn';
  }

  public formatMilliseconds(value: number | null | undefined): string {
    if (value === null || value === undefined || !Number.isFinite(value)) {
      return 'Sin dato';
    }
    return value >= 1000 ? `${(value / 1000).toFixed(3)} s` : `${value.toFixed(3)} ms`;
  }

  public formatConfidence(value: number | null | undefined): string {
    if (value === null || value === undefined || !Number.isFinite(value)) {
      return 'Sin dato';
    }
    return `${(value * 100).toFixed(1)}%`;
  }

  public captchaQualityAccuracy(value: number | null | undefined): string {
    return this.formatConfidence(value);
  }

  public captchaQualityModelTone(model: CaptchaQualityModel): string {
    if (model.accuracy === null || model.evaluated < 10) {
      return 'neutral';
    }
    if (model.accuracy >= 0.95) {
      return 'good';
    }
    return model.accuracy >= 0.85 ? 'warn' : 'bad';
  }

  public captchaQualityCaseSummary(item: CaptchaQualityCase): string {
    if (item.case_types.includes('unanimous_wrong')) {
      return 'Todos los modelos coincidieron en una respuesta incorrecta.';
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

  public captchaQualityWeeklyModel(week: CaptchaQualityWeek, modelName: string) {
    return week.models[modelName] ?? null;
  }

  public captchaOrderLabel(event: CaptchaEvent): string {
    if (this.isObserverCaptcha(event)) {
      return `Observador · muestra ${event.metadata.attempt ?? '?'} de 15`;
    }
    return event.metadata.order_id || (event.metadata.run_id ? 'Observador' : 'Sin orden');
  }

  public isObserverCaptcha(event: CaptchaEvent): boolean {
    return event.metadata.observer === 1 || event.metadata.observer === true;
  }

  public captchaLocalTotalMs(event: CaptchaEvent): number | null {
    if (!event.predictions.length) {
      return null;
    }
    return event.predictions.reduce((total, prediction) => total + prediction.inference_ms, 0);
  }

  public captchaDraft(event: CaptchaEvent): string {
    return this.captchaDrafts()[event.event_id] ?? event.human_label?.answer ?? '';
  }

  public updateCaptchaDraft(eventId: string, value: string): void {
    const normalized = value
      .toUpperCase()
      .replace(/[^A-Z0-9]/g, '')
      .slice(0, 5);
    this.captchaDrafts.update((drafts) => ({ ...drafts, [eventId]: normalized }));
    this.clearCaptchaReviewMessage();
  }

  public captchaPredictionOptions(event: CaptchaEvent): CaptchaPredictionOption[] {
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

  public captchaChoiceMode(
    event: CaptchaEvent,
  ): 'consensus' | 'majority' | 'plurality' | 'manual' {
    const options = this.captchaPredictionOptions(event);
    if (event.predictions.length >= 2 && options.length === 1) {
      return 'consensus';
    }
    const leadingVotes = options[0]?.modelNames.length ?? 0;
    if (leadingVotes > event.predictions.length / 2) {
      return 'majority';
    }
    if (leadingVotes >= 2) {
      return 'plurality';
    }
    return 'manual';
  }

  public captchaChoiceLabel(event: CaptchaEvent): string {
    const mode = this.captchaChoiceMode(event);
    if (mode === 'consensus') {
      return 'Consenso';
    }
    if (mode === 'majority') {
      const leadingVotes = this.captchaPredictionOptions(event)[0]?.modelNames.length ?? 0;
      return `Mayoría ${leadingVotes}–${event.predictions.length - leadingVotes}`;
    }
    if (mode === 'plurality') {
      return 'Coincidencia parcial';
    }
    return event.predictions.length ? `${event.predictions.length} respuestas` : 'Sin consenso';
  }

  public captchaReviewReasonLabel(event: CaptchaEvent): string {
    const labels: Record<string, string> = {
      canary_v6: 'Canario V6',
      anomaly: 'Anomalía',
      model_disagreement: 'Desacuerdo V3/V6',
      control_sample: 'Muestra de control',
    };
    return labels[event.review_priority_reason ?? ''] ?? 'Revisión dirigida';
  }

  public captchaModelLabel(modelName: string): string {
    return (
      {
        v1_real: 'v1 original',
        v2_scratch: 'v2 desde cero',
        v2_selected: 'v2 seleccionado',
        v3_selected: 'v3 seleccionado',
        v4_candidate: 'v4 histórico',
        v5_candidate: 'v5 histórico',
        v6_sequence_candidate: 'v6 secuencial',
      }[modelName] ?? modelName
    );
  }

  public captchaSourceLabel(event: CaptchaEvent): string {
    return this.isObserverCaptcha(event) ? 'Observador' : 'Reserva';
  }

  public captchaSuggestionTone(event: CaptchaEvent, answer: string): string {
    if (!event.human_label) {
      return 'neutral';
    }
    return event.human_label.answer === answer ? 'good' : 'bad';
  }

  public async chooseCaptchaPrediction(event: CaptchaEvent, answer: string): Promise<void> {
    this.updateCaptchaDraft(event.event_id, answer);
    await this.requestCaptchaHumanLabel(event, answer);
  }

  public async saveCaptchaHumanLabel(event: CaptchaEvent): Promise<void> {
    await this.requestCaptchaHumanLabel(event, this.captchaDraft(event));
  }

  public pendingCaptchaCorrection(eventId: string): CaptchaPendingCorrection | null {
    const correction = this.captchaPendingCorrection();
    return correction?.eventId === eventId ? correction : null;
  }

  public async confirmCaptchaCorrection(event: CaptchaEvent): Promise<void> {
    const correction = this.pendingCaptchaCorrection(event.event_id);
    if (!correction) {
      return;
    }
    await this.persistCaptchaHumanLabel(event, correction.nextAnswer);
  }

  public cancelCaptchaCorrection(event: CaptchaEvent): void {
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

  public async changeMonth(month: string): Promise<void> {
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

  public openNewFinanceEntry(): void {
    this.clearFinanceForm();
    this.openModal('finance-entry');
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
    this.openModal('finance-entry');
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

  public async requestVoidFinanceEntry(entry: FinanceEntry): Promise<void> {
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
        this.showToast('Movimiento anulado');
      } catch (error) {
        this.errorMessage.set(this.readError(error));
      } finally {
        this.actionBusy.set(false);
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
    this.financeMismatchReconciledBy.set('');
  }

  public cancelFinanceMismatchResolution(): void {
    this.financeMismatchPaymentId.set('');
    this.financeMismatchReason.set('');
    this.financeMismatchReconciledBy.set('');
  }

  public requestReconcileFinancePayment(paymentId: string): void {
    const reason = this.financeMismatchReason().trim();
    const reconciledBy = this.financeMismatchReconciledBy().trim();
    if (reason.length < 3 || !reconciledBy) {
      this.errorMessage.set('Indica una causa de al menos 3 caracteres y el responsable.');
      return;
    }
    const resolution = this.financeMismatchResolution();
    void this.setPendingAction({
      title: 'Conciliar diferencia de pago',
      message: `Registrar ${this.financeResolutionLabel(resolution).toLowerCase()} como causa explícita. El importe original no se reescribe.`,
      execute: () =>
        this.api.reconcileFinancePaymentAmount(paymentId, {
          resolution_type: resolution,
          reason,
          reconciled_by: reconciledBy,
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
    const reconciledBy = this.financeClosureReconciledBy().trim();
    if (status === 'reconciled' && (!opening || !closing || !reconciledBy)) {
      this.errorMessage.set('Para conciliar, completa saldo inicial, saldo final y responsable.');
      return;
    }
    void this.setPendingAction({
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
          reconciled_by: status === 'reconciled' ? reconciledBy : null,
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

  public hasReservationRestrictions(order: ServiceOrder): boolean {
    return Boolean(
      order.minimum_reservation_date ||
      order.maximum_reservation_date ||
      (order.allowed_weekdays && order.allowed_weekdays.length > 0) ||
      (order.excluded_date_ranges?.length ?? 0) > 0,
    );
  }

  public serviceTypeLabel(order: ServiceOrder): string {
    if (order.service_type === 'selected_weekday') {
      return 'Día elegido';
    }
    if (order.service_type === 'custom') {
      return this.hasReservationRestrictions(order)
        ? 'Disponibilidad restringida'
        : 'Personalizado';
    }
    return 'Estándar';
  }

  public servicePriceLabel(order: ServiceOrder): string {
    const amount = Number(order.reservation_price);
    return Number.isFinite(amount) ? `S/${amount.toFixed(2)}` : `S/${order.reservation_price}`;
  }

  public restrictionDaysLabel(order: ServiceOrder): string {
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

  public restrictionTimingLabel(order: ServiceOrder): string {
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

  public metricPeriodLabel(period: MetricPeriod): string {
    if (period.coverage_end_exclusive <= period.start) {
      return 'Sin cobertura todavía';
    }
    const start = this.formatDate(period.start);
    const end = new Date(`${period.coverage_end_exclusive}T12:00:00`);
    end.setDate(end.getDate() - 1);
    return `${start} – ${this.formatDate(end.toISOString().slice(0, 10))}`;
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
      return current > 0 ? `${this.formatMoney(current)} · sin cobros comparables previos` : 'Sin cobros en ambos rangos';
    }
    const change = current / previous - 1;
    return `${this.formatMoney(current)} · ${change >= 0 ? '+' : ''}${this.formatPercent(change)}`;
  }

  public openInboxCaptchaReview(): void {
    this.showCaptchaWorkspace('review');
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
      await this.openEditOrder(order, 'credentials');
      return;
    }
    if (task.action === 'revalidate') {
      this.selectOrder(order.order_id, false);
      this.requestOrderValidation(order);
      return;
    }
    if (task.action === 'edit_contact') {
      await this.openEditOrder(order, 'contact');
      return;
    }
    if (task.action === 'prepare_whatsapp') {
      this.selectOrder(order.order_id, false);
      await this.openOrderWhatsApp(order);
      return;
    }
    if (task.action === 'register_payment') {
      await this.openPayment(order);
      return;
    }
    if (
      task.action === 'review_whatsapp' ||
      task.action === 'review_post_payment_whatsapp'
    ) {
      await this.openWhatsAppReview(order);
    }
  }

  private async loadInboxTaskOrder(orderId: string): Promise<ServiceOrderDetail | null> {
    this.actionBusy.set(true);
    this.errorMessage.set(null);
    try {
      const order = await this.api.getServiceOrder(orderId);
      this.orders.update((orders) => [order, ...orders.filter((item) => item.order_id !== orderId)]);
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
    const order = this.orders().find((item) => item.order_id === orderId);
    if (!order) {
      this.openOrderFromSummary(orderId);
      return;
    }
    void this.router.navigate(['/ordenes', orderId]);
    void this.openPayment(order);
  }

  public selectOrder(orderId: string, loadDetail = true, updateRoute = true): void {
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

  public closeOrderPanel(updateRoute = true): void {
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

  public async openEditOrder(
    order: ServiceOrder,
    section: 'all' | 'contact' | 'credentials' | 'restrictions' = 'all',
  ): Promise<void> {
    this.selectOrder(order.order_id, false);
    this.editOrderSection.set(section);
    this.openModal('edit-order');
    await this.loadSelectedOrderDetail(order.order_id);
  }

  public async openPayment(order: ServiceOrder): Promise<void> {
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

  public setQuickPaymentAmount(amount: string): void {
    this.editField(this.paymentAmountPaid, amount);
  }

  public showPendingPayments(): void {
    this.setOrderQuickFilter('payment_pending');
    void this.router.navigateByUrl('/ordenes');
  }

  public openOrderActions(order: ServiceOrder): void {
    this.selectOrder(order.order_id);
    this.openModal('order-actions');
  }

  public openCreateOrder(): void {
    this.openModal('create-order');
  }

  public openWhatsAppTest(): void {
    this.whatsappPackage.set(null);
    this.whatsappFollowUpPackage.set(null);
    this.whatsappTestRecipient.set('');
    this.whatsappTestMode.set(true);
    this.whatsappFollowUpMode.set(true);
    this.whatsappReviewMode.set(false);
    this.whatsappReview.set(null);
    this.whatsappWebResult.set(null);
    this.whatsappManualFallbackOpen.set(true);
    this.openModal('whatsapp');
  }

  public openWhatsAppEvidenceTest(): void {
    this.whatsappPackage.set(null);
    this.whatsappFollowUpPackage.set(null);
    this.whatsappTestRecipient.set('');
    this.whatsappTestMode.set(true);
    this.whatsappFollowUpMode.set(false);
    this.whatsappReviewMode.set(false);
    this.whatsappReview.set(null);
    this.whatsappWebResult.set(null);
    this.whatsappManualFallbackOpen.set(true);
    this.openModal('whatsapp');
  }

  public async validateWhatsAppSession(): Promise<boolean> {
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
          this.showToast('WhatsApp vinculado y listo');
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

  public async prepareWhatsAppTest(): Promise<void> {
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
      this.showToast('Prueba preparada: revisa el contenido antes de enviarlo');
      return;
    }
    await this.loadWhatsAppPackage(() => this.api.prepareWhatsAppTest(recipient));
    this.whatsappManualFallbackOpen.set(false);
    this.showToast('Prueba preparada: revisa las imágenes y el texto antes de enviarla');
  }

  public async openOrderWhatsApp(order: ServiceOrder, allowResend = false): Promise<void> {
    this.whatsappPackage.set(null);
    this.whatsappFollowUpPackage.set(null);
    this.whatsappTestMode.set(false);
    this.whatsappFollowUpMode.set(false);
    this.whatsappReviewMode.set(false);
    this.whatsappReview.set(null);
    this.whatsappWebResult.set(null);
    this.whatsappManualFallbackOpen.set(false);
    this.openModal('whatsapp');
    try {
      await this.loadWhatsAppPackage(() =>
        this.api.prepareOrderWhatsApp(order.order_id, allowResend),
      );
      this.whatsappManualFallbackOpen.set(false);
      this.showToast('Paquete preparado: revisa las imágenes y el texto antes de enviarlo');
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

  public async openPostPaymentWhatsApp(order: ServiceOrder, allowResend = false): Promise<void> {
    this.whatsappPackage.set(null);
    this.whatsappFollowUpPackage.set(null);
    this.whatsappTestMode.set(false);
    this.whatsappFollowUpMode.set(true);
    this.whatsappReviewMode.set(false);
    this.whatsappReview.set(null);
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

  public async openWhatsAppReview(order: ServiceOrder): Promise<void> {
    const isFollowUp =
      this.isPostPaymentWhatsAppCandidate(order) &&
      ['failed', 'uncertain'].includes(order.whatsapp_followup_action_state);
    this.whatsappPackage.set(null);
    this.whatsappFollowUpPackage.set(null);
    this.whatsappTestMode.set(false);
    this.whatsappFollowUpMode.set(isFollowUp);
    this.whatsappReviewMode.set(true);
    this.whatsappReview.set(null);
    this.whatsappReviewNote.set('');
    this.whatsappWebResult.set(null);
    this.whatsappManualFallbackOpen.set(true);
    this.openModal('whatsapp');
    this.whatsappFollowUpLoading.set(true);
    this.errorMessage.set(null);
    try {
      const review = await this.api.getWhatsAppReview(
        order.order_id,
        isFollowUp ? 'whatsapp-followup' : 'whatsapp',
      );
      this.whatsappReview.set(review);
      this.whatsappFollowUpPackage.set(review.message);
    } catch (error) {
      this.errorMessage.set(this.readError(error));
    } finally {
      this.whatsappFollowUpLoading.set(false);
    }
  }

  public async resolveWhatsAppReview(resolution: WhatsAppReviewResolution): Promise<void> {
    const review = this.whatsappReview();
    if (!review || this.actionBusy()) {
      return;
    }
    const note = this.whatsappReviewNote().trim();
    if (resolution === 'dismissed' && !note) {
      this.errorMessage.set('Indica el motivo para cerrar el pendiente sin envío.');
      return;
    }
    const labels: Record<WhatsAppReviewResolution, { title: string; text: string }> = {
      confirmed_complete: {
        title: 'Confirmar paquete completo',
        text: 'Úsalo solo si verificaste en el chat que todo el paquete ya fue enviado.',
      },
      completed_missing: {
        title: 'Confirmar contenido completado',
        text: 'Confirma solo después de enviar manualmente únicamente lo que faltaba.',
      },
      dismissed: {
        title: 'Cerrar pendiente sin envío',
        text: 'El intento seguirá registrado como incierto o fallido y se guardará tu motivo.',
      },
    };
    const copy = labels[resolution];
    const confirmation = await (await this.getSweetAlert()).fire({
      icon: resolution === 'dismissed' ? 'warning' : 'question',
      title: copy.title,
      text: copy.text,
      showCancelButton: true,
      confirmButtonText: 'Sí, registrar resolución',
      cancelButtonText: 'Cancelar',
      focusCancel: true,
    });
    if (!confirmation.isConfirmed) {
      return;
    }
    this.actionBusy.set(true);
    try {
      await this.api.resolveWhatsAppReview(review.job.job_key, resolution, note || null);
      await this.refreshAll();
      this.actionBusy.set(false);
      this.closeModal();
      this.showToast('Pendiente de WhatsApp resuelto y auditado');
    } catch (error) {
      this.errorMessage.set(this.readError(error));
    } finally {
      this.actionBusy.set(false);
    }
  }

  public canPrepareOrderWhatsApp(order: ServiceOrder): boolean {
    const baseEligible =
      order.status === 'reserved_payment_pending' &&
      order.reservation_status === 'confirmed' &&
      order.payment_status === 'pending' &&
      !!order.amount_agreed &&
      order.charge_required;
    if (!baseEligible) {
      return false;
    }
    if (order.whatsapp_message_action_state === 'resolved') {
      return false;
    }
    const detail = this.selectedOrderDetail();
    if (!detail || detail.order_id !== order.order_id) {
      return false;
    }
    return this.hasWhatsAppRecipient(detail);
  }

  public whatsappPreparationHint(order: ServiceOrder): string {
    if (order.whatsapp_message_action_state === 'resolved') {
      return 'El resultado fue conciliado y cerrado por el operador.';
    }
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
    if (!this.hasWhatsAppRecipient(detail)) {
      return 'Registra un numero internacional o un @usuario de WhatsApp valido.';
    }
    return order.whatsapp_message_status === 'sent'
      ? 'Ya fue enviado; la siguiente accion preparara un reenvio explicito.'
      : 'Listo para preparar saludo, constancia y cobro.';
  }

  public canPreparePostPaymentWhatsApp(order: ServiceOrder): boolean {
    if (!this.isPostPaymentWhatsAppCandidate(order)) {
      return false;
    }
    if (order.whatsapp_followup_action_state === 'resolved') {
      return false;
    }
    const detail = this.selectedOrderDetail();
    if (!detail || detail.order_id !== order.order_id) {
      return false;
    }
    return this.hasWhatsAppRecipient(detail);
  }

  public postPaymentWhatsAppHint(order: ServiceOrder): string {
    if (!this.isPostPaymentWhatsAppCandidate(order)) {
      return 'Requiere reserva confirmada y pago ya registrado.';
    }
    if (order.whatsapp_followup_action_state === 'resolved') {
      return 'El resultado fue conciliado y cerrado por el operador.';
    }
    const detail = this.selectedOrderDetail();
    if (!detail || detail.order_id !== order.order_id) {
      return 'Cargando contacto protegido...';
    }
    if (!this.hasWhatsAppRecipient(detail)) {
      return 'Registra un numero internacional o un @usuario de WhatsApp valido.';
    }
    return order.whatsapp_followup_status === 'sent'
      ? 'Ya fue enviado; la siguiente accion preparara un reenvio explicito.'
      : 'Listo para preparar indicaciones post-pago y PDFs.';
  }

  public isPostPaymentWhatsAppCandidate(order: ServiceOrder): boolean {
    return (
      order.status === 'paid' &&
      order.reservation_status === 'confirmed' &&
      order.payment_status === 'paid'
    );
  }

  private hasWhatsAppRecipient(detail: ServiceOrderDetail): boolean {
    return /^\+\d{8,15}$/.test(detail.contact_whatsapp ?? '')
      || /^@\S{1,99}$/.test(detail.contact_whatsapp_username ?? '');
  }

  public async copyWhatsAppText(text: string, label: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(text);
      this.markCopied(label);
      this.showToast('Texto copiado');
    } catch {
      this.errorMessage.set('El navegador no permitio copiar. Selecciona el texto manualmente.');
    }
  }

  public async copyWhatsAppAttachment(): Promise<void> {
    const message = this.whatsappPackage();
    if (!message) {
      return;
    }
    try {
      const blob = await this.api.getWhatsAppAttachment(message.attachment_url);
      const png = blob.type === 'image/png' ? blob : new Blob([blob], { type: 'image/png' });
      await navigator.clipboard.write([new ClipboardItem({ 'image/png': png })]);
      this.markCopied('constancia');
      this.showToast('Constancia copiada. Pegala con Ctrl+V en WhatsApp.');
    } catch {
      this.errorMessage.set(
        'No se pudo copiar la imagen. Usa Descargar constancia como alternativa.',
      );
    }
  }

  public async prepareWhatsAppWebDraft(
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
        this.showToast('WhatsApp preparado: revisa el álbum y pulsa Enviar');
      } else if (response.status === 'sent') {
        this.whatsappPackage.set({
          ...message,
          status: 'sent',
          sent_at: response.sent_at ?? new Date().toISOString(),
        });
        this.showToast('Constancia y cobro enviados por WhatsApp');
      }
    } catch (error) {
      this.errorMessage.set(this.readError(error));
      this.whatsappManualFallbackOpen.set(true);
    } finally {
      this.whatsappWebBusy.set(false);
    }
  }

  public async confirmAndSendWhatsAppEvidence(): Promise<void> {
    const message = this.whatsappPackage();
    if (!message || message.status === 'sent' || this.whatsappWebBusy()) {
      return;
    }
    const result = await (await this.getSweetAlert()).fire({
      icon: 'question',
      title: message.test_mode ? 'Enviar prueba de evidencias' : 'Enviar evidencia y cobro',
      text:
        `Se enviarán la constancia, el QR de Yape y el texto combinado a ` +
        `${message.recipient_label}. WhatsApp realizará un único intento.`,
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

  public async prepareWhatsAppFollowUpWebDraft(
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
        this.showToast('Post-pago preparado: revisa WhatsApp y pulsa Enviar');
      } else if (response.status === 'sent') {
        this.whatsappFollowUpPackage.set({
          ...message,
          status: 'sent',
          sent_at: response.sent_at ?? new Date().toISOString(),
        });
        this.showToast('Post-pago enviado por WhatsApp');
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

  public async confirmAndSendWhatsAppFollowUp(): Promise<void> {
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
        `${message.recipient_label}. WhatsApp realizará un único intento.`,
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

  public async confirmWhatsAppSent(): Promise<void> {
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
      this.showToast('Envio de WhatsApp registrado');
    } catch (error) {
      this.errorMessage.set(this.readError(error));
    } finally {
      this.actionBusy.set(false);
    }
  }

  public async confirmWhatsAppFollowUpSent(): Promise<void> {
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
      await this.refreshAll();
      this.showToast('Seguimiento post-pago registrado');
    } catch (error) {
      this.errorMessage.set(this.readError(error));
    } finally {
      this.actionBusy.set(false);
    }
  }

  public openWorkerRestart(): void {
    this.releaseSafeBackoffsOnRestart.set(false);
    this.openModal('worker-restart');
  }

  public opportunityMode(target: OpportunityControlTarget) {
    return this.opportunityControl()?.[target] ?? null;
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
        message:
          'Se aplicará a nuevas detecciones. El máximo seguirá siendo 2 sesiones y no cambiarán los intervalos ni CAPTCHA.',
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
      this.whatsappReviewMode.set(false);
      this.whatsappReview.set(null);
      this.whatsappReviewNote.set('');
      this.whatsappWebResult.set(null);
      this.whatsappManualFallbackOpen.set(false);
    }
    this.restoreFocus();
  }

  public runNextOrderAction(): void {
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
      void this.openWhatsAppReview(order);
    }
  }

  public rowPrimaryActionLabel(order: ServiceOrder): string {
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
      if (order.whatsapp_followup_action_state === 'resolved') {
        return 'Post-pago conciliado';
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

  public runRowPrimaryAction(order: ServiceOrder): void {
    if (order.payment_status === 'pending') {
      void this.openPayment(order);
      return;
    }
    if (
      this.isPostPaymentWhatsAppCandidate(order) &&
      order.whatsapp_followup_action_state !== 'not_applicable'
    ) {
      this.selectOrder(order.order_id);
      if (['failed', 'uncertain'].includes(order.whatsapp_followup_action_state)) {
        void this.openWhatsAppReview(order);
      } else if (order.whatsapp_followup_action_state === 'sent') {
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

  public setQuickPriority(priority: number): void {
    this.orderPriority.set(priority);
    this.requestPriorityUpdate();
  }

  public priorityExplanation(order: ServiceOrder): string {
    if (order.priority >= 200) {
      return 'Enfoque exclusivo: el worker revisa unicamente esta orden.';
    }
    if (order.priority >= 100) {
      return 'Enfoque prioritario: se atiende antes que la cola normal.';
    }
    return 'Cola normal: mayor numero primero; empate por orden de creacion.';
  }

  public isClosedOrder(order: ServiceOrder): boolean {
    return ['archived', 'paid'].includes(order.status) || !!order.closed_at;
  }

  public editField<T>(field: WritableSignal<T>, value: T): void {
    field.set(value);
    this.formDirty.set(true);
  }

  public setOrderQuickFilter(filter: OrderQuickFilter): void {
    this.orderQuickFilter.set(filter);
    this.resetOrderPage();
    this.persistOrderViewState();
  }

  public setOrderFilter(value: string): void {
    this.orderFilter.set(value);
    this.resetOrderPage();
    this.persistOrderViewState();
    try {
      window.sessionStorage.setItem(ORDER_SEARCH_SESSION_KEY, value);
    } catch {
      // La búsqueda permanece disponible en memoria si el navegador bloquea storage.
    }
  }

  public setOrderSort(key: OrderSortKey): void {
    if (this.orderSortKey() === key) {
      this.orderSortDirection.set(this.orderSortDirection() === 'asc' ? 'desc' : 'asc');
    } else {
      this.orderSortKey.set(key);
      this.orderSortDirection.set(this.defaultOrderSortDirection(key));
    }
    this.resetOrderPage();
    this.persistOrderViewState();
  }

  public chooseOrderSort(key: OrderSortKey): void {
    if (this.orderSortKey() === key) {
      return;
    }
    this.orderSortKey.set(key);
    this.orderSortDirection.set(this.defaultOrderSortDirection(key));
    this.resetOrderPage();
    this.persistOrderViewState();
  }

  public toggleOrderSortDirection(): void {
    this.orderSortDirection.set(this.orderSortDirection() === 'asc' ? 'desc' : 'asc');
    this.resetOrderPage();
    this.persistOrderViewState();
  }

  public changeOrderPageSize(value: number | string): void {
    const pageSize = Number(value);
    if (!ORDER_PAGE_SIZES.includes(pageSize as (typeof ORDER_PAGE_SIZES)[number])) {
      return;
    }
    this.orderPageSize.set(pageSize);
    this.resetOrderPage();
    this.persistOrderViewState();
  }

  public goToOrderPage(page: number): void {
    if (page < 1 || page > this.orderTotalPages() || page === this.currentOrderPage()) {
      return;
    }
    this.orderPage.set(page);
    this.persistOrderViewState();
    window.requestAnimationFrame(() => {
      document.querySelector('.order-controls')?.scrollIntoView({ behavior: 'smooth' });
    });
  }

  public sortIndicator(key: OrderSortKey): string {
    if (this.orderSortKey() !== key) {
      return '';
    }
    return this.orderSortDirection() === 'asc' ? 'ASC' : 'DESC';
  }

  public orderAriaSort(key: OrderSortKey): 'ascending' | 'descending' | null {
    if (this.orderSortKey() !== key) {
      return null;
    }
    return this.orderSortDirection() === 'asc' ? 'ascending' : 'descending';
  }

  public requestContactUpdate(): void {
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
      contact_whatsapp_username: this.optionalText(this.contactWhatsappUsername()),
      contact_source: this.optionalText(this.contactSource()),
    };
    if (!payload.contact_name && !payload.contact_whatsapp && !payload.contact_whatsapp_username) {
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

  public needsCredentialCorrection(order: ServiceOrder): boolean {
    return order.preflight_error_type === 'invalid_credentials';
  }

  public toggleOrderPasswordVisibility(): void {
    this.orderPasswordVisible.update((visible) => !visible);
  }

  public requestCredentialsUpdate(): void {
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

  public requestPriorityUpdate(): void {
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

  public requestReservationRestrictionsUpdate(): void {
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

  public addOrderExcludedDateRange(): void {
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

  public removeOrderExcludedDateRange(index: number): void {
    this.orderExcludedDateRanges.update((ranges) =>
      ranges.filter((_, rangeIndex) => rangeIndex !== index),
    );
    this.formDirty.set(true);
  }

  public clearOrderExcludedDateRanges(): void {
    this.orderExcludedDateRanges.set([]);
    this.formDirty.set(true);
  }

  public addNewExcludedDateRange(): void {
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

  public removeNewExcludedDateRange(index: number): void {
    this.newExcludedDateRanges.update((ranges) =>
      ranges.filter((_, rangeIndex) => rangeIndex !== index),
    );
    this.formDirty.set(true);
  }

  public clearNewExcludedDateRanges(): void {
    this.newExcludedDateRanges.set([]);
    this.formDirty.set(true);
  }

  public requestOrderAction(
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

  public requestOrderValidation(order: ServiceOrder): void {
    this.setPendingAction({
      title: 'Validar acceso',
      message: `Ingresar al portal y validar identidad y programas de ${order.order_id}.`,
      execute: () => this.api.revalidateServiceOrder(order.order_id),
      onSuccess: () => this.activeModal.set(null),
    });
  }

  public preflightLabel(order: ServiceOrder): string {
    const labels: Record<ServiceOrder['preflight_status'], string> = {
      not_required: 'Sin validación previa',
      pending: 'Validación pendiente',
      running: 'Validando acceso',
      validated: 'Acceso validado',
      failed: 'Validación fallida',
    };
    return labels[order.preflight_status] ?? order.preflight_status;
  }

  public requestCloseOrder(): void {
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

  public setClosureReason(value: string): void {
    const allowed: ClosureReason[] = [
      'completed_by_us',
      'family_no_charge',
      'client_withdrew',
      'external_slot',
      'duplicate',
      'not_serviceable',
      'uncollectible',
    ];
    const reason = allowed.includes(value as ClosureReason)
      ? (value as ClosureReason)
      : 'client_withdrew';
    this.editField(this.closureReason, reason);
  }

  public requestMarkPaid(): void {
    const order = this.requireSelectedOrder();
    if (!order) {
      return;
    }
    const payload: PaymentPaidPayload = {
      amount_paid: String(this.paymentAmountPaid() ?? '').trim(),
      amount_agreed: this.optionalText(String(this.paymentAmountAgreed() ?? '')),
      expected_payment_status: order.payment_status,
      expected_amount_agreed: order.amount_agreed,
      expected_amount_paid: order.amount_paid ?? '0.00',
    };
    if (!payload.amount_paid) {
      this.errorMessage.set('Ingresa el monto pagado.');
      return;
    }
    const paid = Number(payload.amount_paid);
    const agreed = Number(payload.amount_agreed);
    if (!Number.isFinite(paid) || paid <= 0) {
      this.errorMessage.set('El total pagado debe ser mayor que cero.');
      return;
    }
    const isPartial = Number.isFinite(agreed) && paid < agreed;
    this.setPendingAction({
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
      onSuccess: () => this.activeModal.set(null),
    });
  }

  public async copySelectedOrderWhatsapp(): Promise<void> {
    const recipient = this.selectedOrderDetail()?.contact_whatsapp
      ?? this.selectedOrderDetail()?.contact_whatsapp_username;
    if (!recipient) {
      return;
    }
    await navigator.clipboard.writeText(recipient);
    this.markCopied('whatsapp-number');
  }

  public openSelectedOrderWhatsapp(): void {
    const digits = this.selectedOrderDetail()?.contact_whatsapp?.replace(/\D/g, '');
    if (digits) {
      window.open(`https://wa.me/${digits}`, '_blank', 'noopener,noreferrer');
    }
  }

  public requestCreateOrder(): void {
    const excludedDateRanges = this.prepareExcludedDateRanges(
      this.newExcludedDateRanges(),
      this.newExcludedDateStart(),
      this.newExcludedDateEnd(),
    );
    if (excludedDateRanges === null) {
      return;
    }
    const servicePackage = this.newServicePackage();
    const customPrice = Number(this.newCustomReservationPrice());
    if (
      servicePackage === 'custom' &&
      (!Number.isFinite(customPrice) || customPrice <= 0 || customPrice > 99999.99)
    ) {
      this.errorMessage.set('Ingresa un precio personalizado válido mayor que cero.');
      return;
    }
    const serviceType = servicePackage === 'standard' ? 'standard' : 'custom';
    const reservationPrice =
      servicePackage === 'standard'
        ? '50.00'
        : servicePackage === 'restricted'
          ? '70.00'
          : customPrice.toFixed(2);
    const payload: CreateServiceOrderPayload = {
      document_number: this.newDocumentNumber().trim(),
      document_type: this.newDocumentType(),
      password: this.newPassword(),
      contact_whatsapp: this.optionalText(this.newContactWhatsapp()),
      contact_whatsapp_username: this.optionalText(this.newContactWhatsappUsername()),
      contact_name: this.newContactName().trim(),
      contact_source: this.newContactSource(),
      service_type: serviceType,
      reservation_price: reservationPrice,
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
      servicePackage === 'restricted' &&
      (!payload.minimum_reservation_date || !payload.maximum_reservation_date)
    ) {
      this.errorMessage.set(
        'La disponibilidad restringida exige una fecha inicial y una fecha final.',
      );
      return;
    }
    if (
      servicePackage === 'restricted' &&
      !payload.allowed_weekdays?.length &&
      !payload.excluded_date_ranges?.length
    ) {
      this.errorMessage.set(
        'Indica días permitidos o fechas excluidas para delimitar la disponibilidad restringida.',
      );
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
      message: `Crear orden para documento ${payload.document_number} como ${
        servicePackage === 'standard'
          ? 'servicio estándar'
          : servicePackage === 'restricted'
            ? 'disponibilidad restringida'
            : 'servicio personalizado'
      } por S/${reservationPrice}.`,
      execute: () => this.api.createServiceOrder(payload),
      containsSecret: true,
      onSuccess: () => {
        this.clearCreateOrderForm();
        this.activeModal.set(null);
      },
      onSettled: () => this.newPassword.set(''),
    });
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

  public setCaptchaSamplingEnabled(enabled: boolean): void {
    if (this.captchaSamplingEnabled() === enabled) {
      return;
    }
    this.captchaSamplingEnabled.set(enabled);
    this.captchaSamplingDirty.set(true);
  }

  public setCaptchaSamplingLimit(value: number | string): void {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) {
      return;
    }
    const normalized = Math.min(50, Math.max(2, Math.round(parsed)));
    if (this.captchaSamplingLimit() === normalized) {
      return;
    }
    this.captchaSamplingLimit.set(normalized);
    this.captchaSamplingDirty.set(true);
  }

  public async saveCaptchaSamplingControl(): Promise<void> {
    if (this.captchaSamplingSaving()) {
      return;
    }
    this.captchaSamplingSaving.set(true);
    this.errorMessage.set(null);
    try {
      const control = await this.api.updateCaptchaSamplingControl(
        this.captchaSamplingEnabled(),
        this.captchaSamplingLimit(),
      );
      this.captchaSamplingDirty.set(false);
      this.applyCaptchaSamplingControl(control);
      this.showToast(
        control.enabled
          ? `Muestreo activado: ${control.sample_limit} CAPTCHA por lote`
          : 'Muestreo adicional desactivado',
      );
    } catch (error) {
      this.errorMessage.set(this.readError(error));
    } finally {
      this.captchaSamplingSaving.set(false);
    }
  }

  private applyCaptchaSamplingControl(control: CaptchaSamplingControl): void {
    this.captchaSamplingControl.set(control);
    if (!this.captchaSamplingDirty()) {
      this.captchaSamplingEnabled.set(control.enabled);
      this.captchaSamplingLimit.set(control.sample_limit);
    }
  }

  public requestCaptchaAuthorityFallback(): void {
    this.setPendingAction({
      title: 'Usar 2Captcha como autoridad',
      message:
        'V6 seguirá comparando en sombra, pero desde el siguiente CAPTCHA final la respuesta se pedirá a 2Captcha.',
      execute: async () => {
        this.captchaAuthorityControl.set(
          await this.api.updateCaptchaAuthorityControl('2captcha'),
        );
        return { status: 'ok' };
      },
      successMessage: '2Captcha quedó como autoridad del CAPTCHA final',
    });
  }

  public requestCaptchaAuthorityCanary(): void {
    const resetCircuit = this.captchaAuthorityControl()?.circuit_state === 'open';
    this.setPendingAction({
      title: resetCircuit ? 'Reactivar canario V6' : 'Activar canario V6',
      message: resetCircuit
        ? 'Se cerrará el circuito después de tu revisión. V6 volverá a resolver únicamente dentro del límite restante y con fallback a 2Captcha.'
        : 'V6 resolverá dentro del límite restante y con los umbrales guardados. 2Captcha seguirá disponible como fallback.',
      execute: async () => {
        this.captchaAuthorityControl.set(
          await this.api.updateCaptchaAuthorityControl('canary', resetCircuit),
        );
        return { status: 'ok' };
      },
      successMessage: 'Canario V6 activo para el siguiente CAPTCHA compatible',
    });
  }

  public requestManualSession(): void {
    const order = this.requireSelectedOrder();
    if (!order) {
      return;
    }
    const mode = this.manualSessionMode(order);
    this.setPendingAction({
      title: this.manualSessionActionLabel(order),
      message:
        mode === 'appointment'
          ? `Abrir el panel de citas en un navegador independiente para ${order.order_id}.`
          : `Abrir el portal para consultar ${order.order_id}. El bot no cambiará el estado de la orden.`,
      execute: () => this.api.openManualSession(order.order_id, mode),
      onSuccess: (response) => {
        if (response.session_id) {
          this.activeManualSessionIds.add(response.session_id);
        }
        this.activeModal.set(null);
      },
    });
  }

  public requestDiagnosticSession(): void {
    const order = this.requireSelectedOrder();
    if (!order) {
      return;
    }
    this.setPendingAction({
      title: 'Medir flujo manual',
      message:
        `Abrir el portal desde el inicio para ${order.order_id}. ` +
        'Se registraran campos y solicitudes de forma sanitizada; tu controlas el envio final.',
      execute: () => this.api.openManualSession(order.order_id, 'diagnostic'),
      onSuccess: (response) => {
        if (response.session_id) {
          this.activeManualSessionIds.add(response.session_id);
        }
        this.activeModal.set(null);
      },
    });
  }

  public async openManualSessionNow(
    order: ServiceOrder,
    mode: ManualSessionMode = this.manualSessionMode(order),
  ): Promise<void> {
    if (this.actionBusy()) {
      return;
    }
    this.actionBusy.set(true);
    this.errorMessage.set(null);
    try {
      const response = await this.api.openManualSession(order.order_id, mode);
      if (response.session_id) {
        this.activeManualSessionIds.add(response.session_id);
      }
      await this.refreshAll();
      this.showToast(
        mode === 'diagnostic'
          ? 'Medición activa'
          : mode === 'appointment'
            ? 'Sesión manual abierta'
            : 'Portal abierto para consulta',
      );
    } catch (error) {
      this.errorMessage.set(this.readError(error));
    } finally {
      this.actionBusy.set(false);
    }
  }

  public async closeManualSession(session: ManualSession): Promise<void> {
    if (this.isManualSessionClosing(session.session_id) || session.close_requested) {
      return;
    }
    this.closingManualSessionIds.update((sessionIds) => {
      const next = new Set(sessionIds);
      next.add(session.session_id);
      return next;
    });
    this.errorMessage.set(null);
    try {
      await this.api.closeManualSession(session.session_id);
      this.activeManualSessionIds.delete(session.session_id);
      this.manualSessions.update((sessions) =>
        sessions.filter((item) => item.session_id !== session.session_id),
      );
      this.showToast('Cierre solicitado');
    } catch (error) {
      this.errorMessage.set(this.readError(error));
    } finally {
      this.closingManualSessionIds.update((sessionIds) => {
        const next = new Set(sessionIds);
        next.delete(session.session_id);
        return next;
      });
    }
  }

  public isManualSessionClosing(sessionId: string): boolean {
    return this.closingManualSessionIds().has(sessionId);
  }

  public setPostAppointmentFilter(filter: PostAppointmentFilter): void {
    this.postAppointmentFilter.set(filter);
    this.postAppointmentPage.set(1);
    this.schedulePostAppointmentReload();
  }

  public setPostAppointmentSearch(value: string): void {
    this.postAppointmentSearch.set(value);
    this.postAppointmentPage.set(1);
    this.schedulePostAppointmentReload(275);
  }

  public choosePostAppointmentSort(key: PostAppointmentSortKey): void {
    if (this.postAppointmentSortKey() === key) {
      return;
    }
    this.postAppointmentSortKey.set(key);
    this.postAppointmentSortDirection.set(
      key === 'priority' || key === 'applicant' ? 'asc' : 'desc',
    );
    this.postAppointmentPage.set(1);
    this.schedulePostAppointmentReload();
  }

  public togglePostAppointmentSortDirection(): void {
    this.postAppointmentSortDirection.set(
      this.postAppointmentSortDirection() === 'asc' ? 'desc' : 'asc',
    );
    this.postAppointmentPage.set(1);
    this.schedulePostAppointmentReload();
  }

  public changePostAppointmentPageSize(value: number | string): void {
    const pageSize = Number(value);
    if (
      !POST_APPOINTMENT_PAGE_SIZES.includes(
        pageSize as (typeof POST_APPOINTMENT_PAGE_SIZES)[number],
      )
    ) {
      return;
    }
    this.postAppointmentPageSize.set(pageSize);
    this.postAppointmentPage.set(1);
    this.schedulePostAppointmentReload();
  }

  public goToPostAppointmentPage(page: number): void {
    if (
      page < 1 ||
      page > this.postAppointmentTotalPages() ||
      page === this.currentPostAppointmentPage()
    ) {
      return;
    }
    this.postAppointmentPage.set(page);
    this.schedulePostAppointmentReload();
    window.requestAnimationFrame(() => {
      document.querySelector('.followups-controls')?.scrollIntoView({ behavior: 'smooth' });
    });
  }

  public postAppointmentItemNumber(index: number): number {
    return this.postAppointmentPageStart() + index;
  }

  public postAppointmentItemLabel(index: number): string {
    return String(this.postAppointmentItemNumber(index)).padStart(3, '0');
  }

  public async reviewPostAppointment(item: PostAppointmentFollowup): Promise<void> {
    if (item.outcome === 'access_lost' || this.isPostAppointmentReviewing(item.order_id)) {
      return;
    }
    this.reviewingPostAppointmentOrderIds.update((orderIds) => {
      const next = new Set(orderIds);
      next.add(item.order_id);
      return next;
    });
    this.errorMessage.set(null);
    try {
      await this.api.reviewPostAppointment(item.order_id);
      let payload = await this.api.getPostAppointmentFollowups(this.postAppointmentQuery(false));
      if (payload.items.length === 0 && this.postAppointmentPage() > 1) {
        this.postAppointmentPage.update((page) => page - 1);
        payload = await this.api.getPostAppointmentFollowups(this.postAppointmentQuery(false));
      }
      this.setPostAppointmentPayload(payload);
      this.lastUpdatedAt.set(this.formatClock(new Date()));
      this.showToast('Seguimiento post-cita actualizado');
    } catch (error) {
      this.errorMessage.set(this.readError(error));
    } finally {
      this.reviewingPostAppointmentOrderIds.update((orderIds) => {
        const next = new Set(orderIds);
        next.delete(item.order_id);
        return next;
      });
    }
  }

  public isPostAppointmentReviewing(orderId: string): boolean {
    return this.reviewingPostAppointmentOrderIds().has(orderId);
  }

  public postAppointmentOutcomeDetail(item: PostAppointmentFollowup): string {
    const details: Record<string, string> = {
      upcoming: 'La cita todavía no ocurre; puede revisarse más adelante.',
      awaiting_update: 'La fecha pasó, pero el portal aún no muestra avance posterior.',
      in_progress: 'El portal ya registra actividad posterior a la cita.',
      completed: 'La etapa final figura atendida o completada.',
      observation_with_progress: 'Hubo una observación y también avance posterior.',
      observation_no_progress: 'Hubo una observación y no aparece avance posterior.',
      access_lost:
        'Archivado: el cliente cambió sus credenciales. Se conserva el último historial sin programar nuevas revisiones.',
      portal_unavailable: 'La consulta no pudo completarse por un error del portal.',
      review_required: 'Todavía no existe una revisión post-cita concluyente.',
    };
    return details[item.outcome] ?? 'Estado pendiente de interpretación.';
  }

  public postAppointmentStageTone(
    item: PostAppointmentFollowup,
    stage: { stage_date: string | null; status_text: string | null; message_class: string },
  ): string {
    if (stage.message_class === 'observation' && !item.later_progress_observed) {
      return 'followup-stage--bad';
    }
    if (stage.message_class === 'observation' && item.later_progress_observed) {
      return 'followup-stage--good';
    }
    const status = normalizeDashboardText(stage.status_text);
    if (
      ['rechazado', 'cancelado', 'observado', 'no atendido', 'desaprobado'].includes(status)
    ) {
      return 'followup-stage--bad';
    }
    if (
      stage.message_class === 'ok' ||
      stage.stage_date ||
      ['atendido', 'programado', 'por programar', 'aprobado', 'completado'].includes(status)
    ) {
      return 'followup-stage--good';
    }
    return 'followup-stage--neutral';
  }

  public postAppointmentMessageTone(
    item: PostAppointmentFollowup,
    messageClass: string,
  ): string {
    return messageClass === 'observation' && !item.later_progress_observed
      ? 'stage-observation'
      : 'stage-ok';
  }

  public requestSplitPrograms(): void {
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
        service_orders: this.filteredOrders().map((order) => this.snapshotOrder(order)),
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

  public orderLabel(order: ServiceOrder | null): string {
    if (!order) {
      return 'Sin orden seleccionada';
    }
    return `${order.order_id} | ${order.applicant_name ?? order.document_number_masked}`;
  }

  public paymentLabel(order: ServiceOrder): string {
    if (!order.charge_required) {
      return 'Sin cobro';
    }
    return this.statusLabel(order.payment_status, 'Sin pago');
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

  public closureReasonLabel(reason: string | null | undefined): string {
    const labels: Record<ClosureReason, string> = {
      completed_by_us: 'Realizado por nosotros',
      family_no_charge: 'Familiar sin cobro',
      client_withdrew: 'Cliente retirado',
      external_slot: 'Cupo por tercero',
      duplicate: 'Duplicado',
      not_serviceable: 'No gestionable',
      uncollectible: 'Incobrable',
    };
    if (!reason) {
      return 'sin cierre';
    }
    return labels[reason as ClosureReason] ?? reason.replaceAll('_', ' ');
  }

  public closureDisplay(order: ServiceOrder): string {
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

  public manualSessionOrderLabel(session: ManualSession): string {
    const order = this.orders().find((item) => item.order_id === session.order_id);
    if (!order) {
      return session.order_id;
    }
    return `${session.order_id} | ${order.applicant_name ?? order.document_number_masked}`;
  }

  public manualSessionMode(order: ServiceOrder): ManualSessionMode {
    return order.status === 'ready' ? 'appointment' : 'portal';
  }

  public manualSessionActionLabel(order: ServiceOrder): string {
    return this.manualSessionMode(order) === 'appointment' ? 'Sesión manual' : 'Abrir portal';
  }

  public manualSessionTypeLabel(session: ManualSession): string {
    if (session.mode === 'diagnostic') {
      return 'Diagnóstico protegido';
    }
    return session.mode === 'appointment' ? 'Operativa' : 'Consulta';
  }

  public hasActiveChildOrders(order: ServiceOrder): boolean {
    return this.orders().some(
      (item) =>
        item.parent_order_id === order.order_id &&
        ['ready', 'paused', 'reserved_payment_pending'].includes(item.status),
    );
  }

  public programChildCount(order: ServiceOrder): number {
    return this.orders().filter((item) => item.parent_order_id === order.order_id).length;
  }

  public orderStatusDisplay(order: ServiceOrder): string {
    const childCount = this.programChildCount(order);
    if (childCount) {
      return `Contenedor · ${childCount} trámite${childCount === 1 ? '' : 's'}`;
    }
    return this.statusLabel(order.status);
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

  private showToast(title: string): void {
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

  private postAppointmentQuery(includeUpcoming: boolean): PostAppointmentQuery {
    return {
      filter: this.postAppointmentFilter(),
      search: this.postAppointmentSearch().trim(),
      sort: this.postAppointmentSortKey(),
      direction: this.postAppointmentSortDirection(),
      limit: this.postAppointmentPageSize(),
      offset: (this.postAppointmentPage() - 1) * this.postAppointmentPageSize(),
      include_upcoming: includeUpcoming,
    };
  }

  private schedulePostAppointmentReload(delay = 0): void {
    if (this.postAppointmentSearchTimer !== null) {
      window.clearTimeout(this.postAppointmentSearchTimer);
    }
    this.postAppointmentSearchTimer = window.setTimeout(() => {
      this.postAppointmentSearchTimer = null;
      void this.reloadPostAppointmentFollowups();
    }, delay);
  }

  private async reloadPostAppointmentFollowups(): Promise<void> {
    if (this.activeView() !== 'followups') {
      return;
    }
    this.postAppointmentRequestScope?.cancel();
    const scope = new RequestScope();
    this.postAppointmentRequestScope = scope;
    try {
      const payload = await this.api.getPostAppointmentFollowups(
        this.postAppointmentQuery(false),
        scope,
      );
      if (this.postAppointmentRequestScope === scope) {
        this.setPostAppointmentPayload(payload);
      }
    } catch (error) {
      if (!isRequestCancelled(error) && this.postAppointmentRequestScope === scope) {
        this.errorMessage.set(this.readError(error));
      }
    } finally {
      if (this.postAppointmentRequestScope === scope) {
        this.postAppointmentRequestScope = null;
      }
    }
  }

  private setPostAppointmentPayload(payload: PostAppointmentPayload): void {
    const current = this.postAppointmentPayload();
    this.postAppointmentPayload.set({
      ...payload,
      upcoming: payload.upcoming ?? current?.upcoming ?? [],
    });
    const totalPages = Math.max(
      1,
      Math.ceil(payload.pagination.total / this.postAppointmentPageSize()),
    );
    if (this.postAppointmentPage() > totalPages) {
      this.postAppointmentPage.set(totalPages);
      this.schedulePostAppointmentReload();
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
      if (key === 'reservation') {
        const compared = compareOptionalTimestamps(
          peruDateTimeSortValue(left.reservation_date, left.reservation_hour),
          peruDateTimeSortValue(right.reservation_date, right.reservation_hour),
          direction,
        );
        if (compared !== 0) {
          return compared;
        }
        return left.order_id.localeCompare(right.order_id, 'es', { numeric: true });
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
      return peruDateTimeSortValue(order.created_at) ?? 0;
    }
    if (key === 'updated_at') {
      return peruDateTimeSortValue(order.updated_at) ?? 0;
    }
    if (key === 'status') {
      return order.status;
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
    const createdCompare =
      (peruDateTimeSortValue(left.created_at) ?? 0) -
      (peruDateTimeSortValue(right.created_at) ?? 0);
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
    this.contactWhatsappUsername.set(detail?.contact_whatsapp_username ?? '');
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
    this.newContactWhatsappUsername.set('');
    this.newContactSource.set('');
    this.newServicePackage.set('standard');
    this.newCustomReservationPrice.set('');
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
    this.financeClosureReconciledBy.set(payload.closure?.reconciled_by ?? '');
    this.financeClosureNotes.set(payload.closure?.notes ?? '');
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
