import { computed, inject, Injectable, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { FollowupsApiClient } from '../../api/followups/followups-api.client';
import type {
  AppointmentReminderStatus,
  PostAppointmentFollowup,
  PostAppointmentPayload,
} from '../../api/followups/followups.contracts';
import { apiErrorMessage } from '../../api/shared/api-error';

import {
  DASHBOARD_FOLLOWUPS_VIEW_FOLLOWUPS,
  DASHBOARD_FOLLOWUPS_VIEW_PRESENTATION,
} from '../../dashboard-domain.ports';
type FollowupWorkspace = 'upcoming' | 'post_appointment' | 'history';

type ReminderMode = AppointmentReminderStatus['control']['mode'];

type ReminderLeadDays = AppointmentReminderStatus['control']['lead_days'];

type ReminderFilter = 'all' | 'pending' | 'missing_contact' | 'sent';

type ReminderSort = 'soonest' | 'latest' | 'applicant' | 'status';

type PostAppointmentSort = 'attention' | 'appointment_soonest' | 'recent' | 'applicant';

type ReminderCandidate = AppointmentReminderStatus['candidates'][number];

type UpcomingFollowup = NonNullable<PostAppointmentPayload['upcoming']>[number];

interface UpcomingAppointment {
  order_id: string;
  applicant_name: string | null;
  appointment_day: string;
  appointment_date_label: string;
  appointment_hour: string | null;
  site: string | null;
  recipient: string | null;
  status: string;
  document_number_masked: string | null;
  program_expediente: string | null;
  program_plate: string | null;
  stage_messages: Array<string | null>;
}

const PERU_DATE_FORMATTER = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Lima',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

const REMINDER_CANDIDATE_PAGE_SIZES = [5, 10, 20] as const;

function paginationWindow(current: number, total: number): number[] {
  const start = Math.max(1, Math.min(current - 2, total - 4));
  const end = Math.min(total, start + 4);
  return Array.from({ length: Math.max(0, end - start + 1) }, (_, index) => start + index);
}

@Injectable()
export class FollowupWorkspaceFacade {
  public readonly followupsDomain = inject(DASHBOARD_FOLLOWUPS_VIEW_FOLLOWUPS);

  public readonly presentationDomain = inject(DASHBOARD_FOLLOWUPS_VIEW_PRESENTATION);

  private readonly followupsApi = inject(FollowupsApiClient);

  private readonly route = inject(ActivatedRoute);

  private readonly router = inject(Router);

  public readonly followupWorkspace = signal<FollowupWorkspace>(this.readInitialWorkspace());

  public readonly reminderStatus = signal<AppointmentReminderStatus | null>(this.followupsDomain.appointmentReminderStatus());

  public readonly reminderStatusLoading = signal(this.reminderStatus() === null);

  public readonly reminderStatusError = signal(false);

  public readonly reminderEditorOpen = signal(false);

  public readonly reminderMode = signal<ReminderMode>('disabled');

  public readonly reminderLeadDays = signal<ReminderLeadDays>(1);

  public readonly reminderSaving = signal(false);

  public readonly reminderSaveError = signal<string | null>(null);

  public readonly reminderSaveSuccess = signal<string | null>(null);

  public readonly reminderActivationReview = signal(false);

  public readonly reminderCandidateSearch = signal('');

  public readonly reminderCandidateFilter = signal<ReminderFilter>('all');

  public readonly reminderCandidateSort = signal<ReminderSort>('soonest');

  public readonly reminderCandidatePage = signal(1);

  public readonly reminderCandidatePageSize = signal(10);

  public readonly postAppointmentSort = signal<PostAppointmentSort>('attention');

  public readonly reminderLeadDayOptions: readonly ReminderLeadDays[] = [1, 2, 3];

  public readonly postAppointmentOperationalCount = computed(() =>
    this.followupsDomain.postAppointmentPayload()?.filter_counts.active ?? 0,
  );

  public readonly postAppointmentHistoryCount = computed(() =>
    this.followupsDomain.postAppointmentPayload()?.filter_counts.history ?? 0,
  );

  public readonly postAppointmentCompletedCount = computed(() =>
    this.followupsDomain.postAppointmentPayload()?.filter_counts.completed ?? 0,
  );

  public readonly upcomingAppointments = computed<UpcomingAppointment[]>(() => {
    const reminderCandidates = this.reminderStatus()?.candidates ?? [];
    const reminderByOrder = new Map<string, ReminderCandidate>(
      reminderCandidates.map((candidate) => [candidate.order_id, candidate]),
    );
    const future = (this.followupsDomain.postAppointmentPayload()?.upcoming ?? [])
      .filter((item: UpcomingFollowup) => this.isTodayOrFuture(item.appointment_date))
      .map((item: UpcomingFollowup): UpcomingAppointment => {
        const reminder = reminderByOrder.get(item.order_id);
        reminderByOrder.delete(item.order_id);
        return {
          order_id: item.order_id,
          applicant_name: item.applicant_name,
          appointment_day: item.appointment_date ?? reminder?.appointment_day ?? '',
          appointment_date_label: reminder?.appointment_date_label ?? item.appointment_date ?? '',
          appointment_hour: item.appointment_hour ?? reminder?.appointment_hour ?? null,
          site: item.site ?? reminder?.site ?? null,
          recipient: reminder?.recipient ?? null,
          status: reminder?.status ?? 'scheduled',
          document_number_masked: item.document_number_masked,
          program_expediente: item.program_expediente,
          program_plate: item.program_plate,
          stage_messages: [],
        };
      });
    const reminderOnly = [...reminderByOrder.values()]
      .filter((candidate) => this.isTodayOrFuture(candidate.appointment_day))
      .map((candidate): UpcomingAppointment => ({
        ...candidate,
        document_number_masked: null,
        program_expediente: null,
        program_plate: null,
        stage_messages: [],
      }));
    return [...future, ...reminderOnly];
  });

  public readonly filteredReminderCandidates = computed(() => {
    const search = this.reminderCandidateSearch().trim().toLocaleLowerCase('es');
    const filter = this.reminderCandidateFilter();
    const candidates = this.upcomingAppointments().filter((candidate) => {
      const matchesSearch = !search || [
        candidate.applicant_name,
        candidate.order_id,
        candidate.site,
        candidate.recipient,
        candidate.status,
        candidate.appointment_date_label,
        candidate.appointment_hour,
        candidate.document_number_masked,
        candidate.program_expediente,
        candidate.program_plate,
        ...candidate.stage_messages,
      ].filter(Boolean).some((value) => String(value).toLocaleLowerCase('es').includes(search));
      if (!matchesSearch || filter === 'all') return matchesSearch;
      if (filter === 'pending') {
        return ['eligible', 'blocked', 'queued', 'running'].includes(candidate.status);
      }
      return candidate.status === filter;
    });

    return [...candidates].sort((left, right) => {
      const sort = this.reminderCandidateSort();
      let compared = 0;
      if (sort === 'soonest' || sort === 'latest') {
        compared = `${left.appointment_day} ${left.appointment_hour ?? '99:99'}`.localeCompare(
          `${right.appointment_day} ${right.appointment_hour ?? '99:99'}`,
        );
        if (sort === 'latest') compared *= -1;
      } else if (sort === 'applicant') {
        compared = (left.applicant_name ?? '').localeCompare(right.applicant_name ?? '', 'es', {
          numeric: true,
          sensitivity: 'base',
        });
      } else {
        compared = left.status.localeCompare(right.status, 'es');
      }
      return compared || left.order_id.localeCompare(right.order_id, 'es', { numeric: true });
    });
  });

  public readonly reminderCandidateTotalPages = computed(() =>
    Math.max(1, Math.ceil(this.filteredReminderCandidates().length / this.reminderCandidatePageSize())),
  );

  public readonly currentReminderCandidatePage = computed(() =>
    Math.min(this.reminderCandidatePage(), this.reminderCandidateTotalPages()),
  );

  public readonly reminderCandidates = computed(() => {
    const start = (this.currentReminderCandidatePage() - 1) * this.reminderCandidatePageSize();
    return this.filteredReminderCandidates().slice(start, start + this.reminderCandidatePageSize());
  });

  public readonly reminderCandidatePageStart = computed(() =>
    this.filteredReminderCandidates().length === 0
      ? 0
      : (this.currentReminderCandidatePage() - 1) * this.reminderCandidatePageSize() + 1,
  );

  public readonly reminderCandidatePageEnd = computed(() =>
    Math.min(
      this.currentReminderCandidatePage() * this.reminderCandidatePageSize(),
      this.filteredReminderCandidates().length,
    ),
  );

  public readonly reminderCandidatePageNumbers = computed(() =>
    paginationWindow(this.currentReminderCandidatePage(), this.reminderCandidateTotalPages()),
  );

  public readonly reminderFilterCounts = computed(() => {
    const candidates = this.upcomingAppointments();
    return {
      all: candidates.length,
      pending: candidates.filter((candidate) => ['eligible', 'blocked', 'queued', 'running'].includes(candidate.status)).length,
      missing_contact: candidates.filter((candidate) => candidate.status === 'missing_contact').length,
      sent: candidates.filter((candidate) => candidate.status === 'sent').length,
    };
  });

  public readonly reminderDraftAppliesNextDay = computed(() => {
    const status = this.reminderStatus();
    return Boolean(
      status?.day
      && this.reminderLeadDays() !== status.configuration.effective_lead_days,
    );
  });

  public readonly reminderDraftServiceDate = computed(() => {
    const status = this.reminderStatus();
    if (!status) return '';
    return this.addIsoDays(status.service_date, this.reminderDraftAppliesNextDay() ? 1 : 0);
  });

  public readonly reminderTargetExample = computed(() => {
    const status = this.reminderStatus();
    if (!status) return '';
    return this.addIsoDays(this.reminderDraftServiceDate(), this.reminderLeadDays());
  });

  constructor() {
    this.followupsDomain.setPostAppointmentFilter(this.followupWorkspace() === 'history' ? 'history' : 'active');
    void this.loadReminderStatus();
  }

  public setFollowupWorkspace(workspace: FollowupWorkspace): void {
    this.followupWorkspace.set(workspace);
    this.followupsDomain.setPostAppointmentFilter(workspace === 'history' ? 'history' : 'active');
    void this.router.navigate([], { relativeTo: this.route, queryParams: { tab: workspace }, replaceUrl: true });
  }

  public setReminderCandidateSearch(value: string): void {
    this.reminderCandidateSearch.set(value);
    this.reminderCandidatePage.set(1);
  }

  public chooseReminderFilter(filter: ReminderFilter): void {
    this.reminderCandidateFilter.set(filter);
    this.reminderCandidatePage.set(1);
  }

  public chooseReminderSort(sort: ReminderSort): void {
    this.reminderCandidateSort.set(sort);
    this.reminderCandidatePage.set(1);
  }

  public changeReminderCandidatePageSize(value: number | string): void {
    const pageSize = Number(value);
    if (!REMINDER_CANDIDATE_PAGE_SIZES.includes(
      pageSize as (typeof REMINDER_CANDIDATE_PAGE_SIZES)[number],
    )) return;
    this.reminderCandidatePageSize.set(pageSize);
    this.reminderCandidatePage.set(1);
  }

  public goToReminderCandidatePage(page: number): void {
    const target = Math.min(Math.max(1, page), this.reminderCandidateTotalPages());
    if (target === this.currentReminderCandidatePage()) return;
    this.reminderCandidatePage.set(target);
    window.requestAnimationFrame(() => {
      document.querySelector('.followups-controls')?.scrollIntoView({ behavior: 'smooth' });
    });
  }

  public choosePostAppointmentSort(sort: PostAppointmentSort): void {
    this.postAppointmentSort.set(sort);
    const choices: Record<PostAppointmentSort, {
      key: 'priority' | 'appointment_date' | 'last_reviewed_at' | 'applicant';
      direction: 'asc' | 'desc';
    }> = {
      attention: { key: 'priority', direction: 'asc' },
      appointment_soonest: { key: 'appointment_date', direction: 'asc' },
      recent: { key: 'last_reviewed_at', direction: 'desc' },
      applicant: { key: 'applicant', direction: 'asc' },
    };
    const choice = choices[sort];
    this.followupsDomain.choosePostAppointmentSort(choice.key);
    if (this.followupsDomain.postAppointmentSortDirection() !== choice.direction) {
      this.followupsDomain.togglePostAppointmentSortDirection();
    }
  }

  public reminderCandidateStatusLabel(status: string): string {
    const labels: Record<string, string> = {
      eligible: 'Pendiente', missing_contact: 'Sin contacto', blocked: 'Espera el resumen',
      queued: 'En cola', running: 'Enviando', sent: 'Enviado', failed: 'Falló',
      uncertain: 'Envío incierto', skipped: 'Omitido al revalidar',
      scheduled: 'Cita programada',
    };
    return labels[status] ?? this.presentationDomain.statusLabel(status);
  }

  public reminderCandidateNextAction(status: string): string {
    const labels: Record<string, string> = {
      eligible: 'Se preparará en la próxima revisión', missing_contact: 'Agregar un contacto válido',
      blocked: 'Esperar que termine el resumen diario', queued: 'Esperar turno de envío',
      running: 'Envío en curso', sent: 'Sin acción pendiente', failed: 'Revisar el detalle del fallo',
      uncertain: 'Verificar manualmente; no reenviar', skipped: 'Revisar la cita o el contacto',
      scheduled: 'Aún fuera de la fecha de recordatorio',
    };
    return labels[status] ?? 'Revisar el estado de la cita';
  }

  public postAppointmentDisplayOutcome(item: PostAppointmentFollowup): string {
    return this.isExpiredUpcoming(item) ? 'review_required' : item.outcome;
  }

  public postAppointmentDisplayDetail(item: PostAppointmentFollowup): string {
    if (this.isExpiredUpcoming(item)) {
      return 'La cita ya pasó y todavía no existe una revisión post-cita concluyente.';
    }
    return this.followupsDomain.postAppointmentOutcomeDetail(item);
  }

  public postAppointmentFreshnessLabel(item: PostAppointmentFollowup): string {
    if (item.review_freshness === 'not_applicable') {
      return item.last_reviewed_at
        ? `Seguimiento finalizado · última revisión: ${this.presentationDomain.formatDateTime(item.last_reviewed_at)}`
        : 'Seguimiento finalizado';
    }
    if (item.review_freshness === 'not_reviewed' || !item.last_reviewed_at) {
      return 'Nunca revisado';
    }
    const prefix = item.review_freshness === 'current' ? 'Actualizada hoy' : 'Desactualizada';
    return `${prefix} · última revisión: ${this.presentationDomain.formatDateTime(item.last_reviewed_at)}`;
  }

  public postAppointmentFreshnessTone(item: PostAppointmentFollowup): 'current' | 'stale' | 'neutral' {
    if (item.review_freshness === 'current') return 'current';
    if (item.review_freshness === 'stale' || item.review_freshness === 'not_reviewed') return 'stale';
    return 'neutral';
  }

  public postAppointmentNextReviewLabel(item: PostAppointmentFollowup): string | null {
    if (!item.next_automatic_review_at) return null;
    return `Elegible para revisión automática desde: ${this.presentationDomain.formatDateTime(item.next_automatic_review_at)}`;
  }

  public handleReminderDialogClosed(): void {
    this.reminderEditorOpen.set(false);
    this.reminderActivationReview.set(false);
  }

  public chooseReminderMode(mode: ReminderMode): void {
    this.reminderMode.set(mode);
    this.reminderActivationReview.set(false);
  }

  public chooseReminderLeadDays(days: ReminderLeadDays): void {
    this.reminderLeadDays.set(days);
    this.reminderActivationReview.set(false);
  }

  public requestReminderSave(): void {
    this.reminderSaveError.set(null);
    if (this.reminderMode() === 'live') {
      this.reminderActivationReview.set(true);
      return;
    }
    void this.saveReminderControl();
  }

  public confirmReminderSave(): void { void this.saveReminderControl(); }

  private async saveReminderControl(): Promise<void> {
    const current = this.reminderStatus();
    if (!current || this.reminderSaving()) return;
    this.reminderSaving.set(true);
    this.reminderSaveError.set(null);
    this.reminderSaveSuccess.set(null);
    try {
      const updated = await this.followupsApi.updateAppointmentReminders({
        mode: this.reminderMode(),
        lead_days: this.reminderLeadDays(),
        expected_revision: current.control.revision,
      });
      this.reminderStatus.set(updated);
      this.syncReminderEditor(updated);
      this.reminderSaveSuccess.set(`Configuración guardada: ${updated.control.lead_days} ${updated.control.lead_days === 1 ? 'día' : 'días'} antes.`);
    } catch (error) {
      this.reminderSaveError.set(apiErrorMessage(error));
    } finally {
      this.reminderSaving.set(false);
      this.reminderActivationReview.set(false);
    }
  }

  private readInitialWorkspace(): FollowupWorkspace {
    const tab = this.route.snapshot.queryParamMap.get('tab');
    return tab === 'post_appointment' || tab === 'history' ? tab : 'upcoming';
  }

  private async loadReminderStatus(): Promise<void> {
    try {
      const status = await this.followupsApi.getAppointmentReminders();
      this.reminderStatus.set(status);
      this.syncReminderEditor(status);
    } catch {
      this.reminderStatusError.set(true);
      this.reminderStatus.set(null);
    } finally {
      this.reminderStatusLoading.set(false);
    }
  }

  private syncReminderEditor(status: AppointmentReminderStatus): void {
    this.reminderMode.set(status.control.mode);
    this.reminderLeadDays.set(status.control.lead_days);
  }

  private addIsoDays(value: string, days: number): string {
    const parts = value.split('-').map(Number);
    if (parts.length !== 3 || parts.some((part) => !Number.isFinite(part))) return value;
    const target = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2]));
    target.setUTCDate(target.getUTCDate() + days);
    return target.toISOString().slice(0, 10);
  }

  private isExpiredUpcoming(item: PostAppointmentFollowup): boolean {
    return item.outcome === 'upcoming' && !this.isTodayOrFuture(item.appointment_date);
  }

  private isTodayOrFuture(value: string | null): boolean {
    return Boolean(value && value >= PERU_DATE_FORMATTER.format(new Date()));
  }

  public prepareReminderEditor(): void {
    const status = this.reminderStatus();
    if (status) this.syncReminderEditor(status);
    this.reminderSaveError.set(null);
    this.reminderSaveSuccess.set(null);
    this.reminderActivationReview.set(false);
    this.reminderEditorOpen.set(true);
  }
}

export type FollowupWorkspaceFacadeView = Pick<FollowupWorkspaceFacade,
  "prepareReminderEditor"
  | "followupWorkspace"
  | "setFollowupWorkspace"
  | "upcomingAppointments"
  | "postAppointmentOperationalCount"
  | "postAppointmentHistoryCount"
  | "followupsDomain"
  | "reminderStatus"
  | "reminderCandidateSearch"
  | "setReminderCandidateSearch"
  | "reminderCandidateFilter"
  | "chooseReminderFilter"
  | "reminderFilterCounts"
  | "reminderCandidateSort"
  | "chooseReminderSort"
  | "filteredReminderCandidates"
  | "presentationDomain"
  | "reminderCandidates"
  | "reminderCandidateStatusLabel"
  | "reminderCandidateNextAction"
  | "reminderCandidatePageStart"
  | "reminderCandidatePageEnd"
  | "currentReminderCandidatePage"
  | "reminderCandidateTotalPages"
  | "reminderCandidatePageSize"
  | "changeReminderCandidatePageSize"
  | "goToReminderCandidatePage"
  | "reminderCandidatePageNumbers"
  | "handleReminderDialogClosed"
  | "reminderLeadDayOptions"
  | "reminderLeadDays"
  | "chooseReminderLeadDays"
  | "reminderDraftAppliesNextDay"
  | "reminderDraftServiceDate"
  | "reminderTargetExample"
  | "reminderMode"
  | "chooseReminderMode"
  | "reminderActivationReview"
  | "reminderSaving"
  | "confirmReminderSave"
  | "reminderSaveError"
  | "reminderSaveSuccess"
  | "requestReminderSave"
  | "reminderStatusLoading"
  | "reminderStatusError"
  | "postAppointmentSort"
  | "choosePostAppointmentSort"
  | "postAppointmentCompletedCount"
  | "postAppointmentDisplayOutcome"
  | "postAppointmentDisplayDetail"
  | "postAppointmentFreshnessTone"
  | "postAppointmentFreshnessLabel"
  | "postAppointmentNextReviewLabel"
>;
