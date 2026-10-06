import type { CaptchaQualityCaseType } from './api/captchas/captchas.contracts';
import type {
  HealthPayload,
  OperatorInboxTask,
  RunSummary,
  WorkerCommand,
  WorkerStatus,
} from './api/operations/operations.contracts';
import type { ServiceOrder } from './api/orders/orders.contracts';
import type { ApiActionResponse } from './api/shared/shared.contracts';

export type LoadState = 'idle' | 'loading' | 'ready' | 'error';

export type ViewKey =
  | 'inbox'
  | 'summary'
  | 'finance'
  | 'messageTemplates'
  | 'orders'
  | 'followups'
  | 'runs'
  | 'captchas';

export type CaptchaAgreementFilter = 'all' | 'match' | 'mismatch' | 'pending';

export type CaptchaPortalFilter = 'all' | 'accepted' | 'rejected' | 'unverified';

export type CaptchaSourceFilter = 'all' | 'reservation' | 'observer';

export type CaptchaReviewFilter = 'all' | 'validated' | 'pending';

export type CaptchaWorkspaceMode = 'review' | 'history' | 'quality';

export type CaptchaPredictionOption = { answer: string; modelNames: string[] };

export type CaptchaPendingCorrection = {
  eventId: string;
  previousAnswer: string;
  nextAnswer: string;
};

export const CAPTCHA_QUALITY_CASE_FILTERS: Array<{
  value: CaptchaQualityCaseType;
  label: string;
}> = [
    { value: 'wrong', label: 'Errores' },
    { value: 'high_confidence_wrong', label: 'Error con confianza alta' },
    { value: 'majority_wrong', label: 'Mayoría incorrecta' },
    { value: 'unanimous_wrong', label: 'Consenso incorrecto' },
    { value: 'disagreement', label: 'Desacuerdos' },
  ];

export type ModalKind =
  | 'edit-order'
  | 'payment'
  | 'order-actions'
  | 'create-order'
  | 'worker-restart'
  | 'finance-entry'
  | 'whatsapp'
  | null;

export type PostAppointmentFilter =
  | 'active'
  | 'attention'
  | 'observations'
  | 'access_lost'
  | 'progressed'
  | 'history';

export type PostAppointmentSortKey = 'priority' | 'appointment_date' | 'last_reviewed_at' | 'applicant';

export type ClosureReason =
  | 'completed_by_us'
  | 'family_no_charge'
  | 'client_withdrew'
  | 'external_slot'
  | 'duplicate'
  | 'not_serviceable'
  | 'uncollectible';

export type SortDirection = 'asc' | 'desc';

export type StatusTone = 'good' | 'warn' | 'bad' | 'neutral';

export type StatusPresentation = { label: string; tone: StatusTone };

export type DashboardSnapshotHealth = Pick<
  HealthPayload,
  'status' | 'worker_running' | 'reason' | 'captcha_shadow_enabled'
>;

export type DashboardSnapshotWorker = Pick<
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

export type DashboardSnapshotOrder = Pick<
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

export type DashboardSnapshotRun = Pick<
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

export type DashboardSnapshotWorkerCommand = Pick<
  WorkerCommand,
  'command_id' | 'command' | 'status' | 'requested_at' | 'claimed_at' | 'processed_at'
>;

export type PendingAction = {
  title: string;
  message: string;
  execute: () => Promise<ApiActionResponse>;
  successMessage?: string | ((response: ApiActionResponse) => string);
  onSuccess?: (response: ApiActionResponse) => void;
  afterRefresh?: (response: ApiActionResponse) => void | Promise<void>;
  onSettled?: () => void;
};

export type OrderNextAction = {
  key:
  | 'manual-session'
  | 'activate'
  | 'payment'
  | 'post-payment-whatsapp'
  | 'program-resolution'
  | 'review'
  | 'none';
  label: string;
  description: string;
  disabled: boolean;
};

export type InboxOrderTask = {
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

export const ERROR_MESSAGE_DURATION_MS = 8_000;

export const POST_APPOINTMENT_PAGE_SIZES = [5, 10, 20] as const;

export const STATUS_PRESENTATIONS: Record<string, StatusPresentation> = {
  active: { label: 'Activo', tone: 'good' },
  actual: { label: 'Real', tone: 'good' },
  archived: { label: 'Archivada', tone: 'neutral' },
  available: { label: 'Disponible', tone: 'warn' },
  blocked: { label: 'Bloqueado', tone: 'warn' },
  cancelled: { label: 'Cancelado', tone: 'neutral' },
  claimed: { label: 'En proceso', tone: 'warn' },
  closing: { label: 'Cerrando', tone: 'warn' },
  close_timeout: { label: 'Cierre demorado', tone: 'bad' },
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

export const WEEKDAY_NAMES = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];

export const SPANISH_LIST_FORMAT = new Intl.ListFormat('es-PE', {
  style: 'long',
  type: 'conjunction',
});

export const INITIAL_MONTH = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Lima',
  year: 'numeric',
  month: '2-digit',
}).format(new Date());

export const INITIAL_DATE = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Lima',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
}).format(new Date());

export const VIEW_LABELS: Record<ViewKey, { label: string; group: string }> = {
  inbox: { label: 'Pendientes', group: 'Operación' },
  summary: { label: 'Resumen', group: 'Operación' },
  orders: { label: 'Órdenes', group: 'Operación' },
  followups: { label: 'Citas y recordatorios', group: 'Operación' },
  runs: { label: 'Runs y actividad', group: 'Operación' },
  finance: { label: 'Finanzas', group: 'Administración' },
  messageTemplates: { label: 'Mensajes de WhatsApp', group: 'Administración' },
  captchas: { label: 'Control de CAPTCHA', group: 'Automatización' },
};

export function normalizeDashboardText(value: unknown): string {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .trim()
    .toLocaleLowerCase('es');
}
