import { Injectable, Injector, computed, inject, signal } from '@angular/core';
import { FollowupsApiClient } from '../../api/followups/followups-api.client';
import type {
  AppointmentReminderStatus,
  PostAppointmentFollowup,
  PostAppointmentPayload,
  PostAppointmentQuery,
} from '../../api/followups/followups.contracts';
import { LoadSection, loadSections } from '../../load-section';

import {
  POST_APPOINTMENT_PAGE_SIZES,
  PostAppointmentFilter,
  PostAppointmentSortKey,
  SortDirection,
  normalizeDashboardText,
} from '../../dashboard-domain.contracts';
import {
  DASHBOARD_FOLLOWUPS_NAVIGATION,
  DASHBOARD_FOLLOWUPS_PRESENTATION,
  DASHBOARD_FOLLOWUPS_UI,
} from '../../dashboard-domain.ports';
import { paginationWindow } from '../../pagination';
import { RequestScope } from '../../request-cancellation';

@Injectable()
export class FollowupsFacade {
  public readonly loads = {
    appointments: new LoadSection('Seguimiento post-cita'),
    reminders: new LoadSection('Recordatorios'),
  };

  private readonly injector = inject(Injector);
  private readonly followupsApi = inject(FollowupsApiClient);

  private postAppointmentSearchTimer: number | null = null;

  private postAppointmentRequestScope: RequestScope | null = null;

  public readonly postAppointmentPayload = signal<PostAppointmentPayload | null>(null);

  public readonly reviewingPostAppointmentOrderIds = signal<ReadonlySet<string>>(new Set());

  public readonly postAppointmentFilter = signal<PostAppointmentFilter>('active');

  public readonly postAppointmentSearch = signal('');

  public readonly postAppointmentSortKey = signal<PostAppointmentSortKey>('priority');

  public readonly postAppointmentSortDirection = signal<SortDirection>('asc');

  public readonly postAppointmentPage = signal(1);

  public readonly postAppointmentPageSize = signal(10);

  public readonly appointmentReminderStatus = signal<AppointmentReminderStatus | null>(null);

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
    this.ui.errorMessage.set(null);
    try {
      await this.followupsApi.reviewPostAppointment(item.order_id);
      await this.reloadPostAppointmentFollowups();
      if (this.navigation.activeView() === 'followups' && !this.loads.appointments.error()) {
        this.navigation.lastUpdatedAt.set(this.presentation.formatClock(new Date()));
        this.ui.showToast('Seguimiento post-cita actualizado');
      }
    } catch (error) {
      this.ui.errorMessage.set(this.presentation.readError(error));
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
    this.postAppointmentRequestScope?.cancel();
    this.loads.appointments.reset();
    if (this.postAppointmentSearchTimer !== null) {
      window.clearTimeout(this.postAppointmentSearchTimer);
    }
    this.postAppointmentSearchTimer = window.setTimeout(() => {
      this.postAppointmentSearchTimer = null;
      void this.reloadPostAppointmentFollowups();
    }, delay);
  }

  private async reloadPostAppointmentFollowups(): Promise<void> {
    if (this.navigation.activeView() !== 'followups') return;
    this.postAppointmentRequestScope?.cancel();
    const scope = new RequestScope(); this.postAppointmentRequestScope = scope;
    try {
      await this.loads.appointments.load(scope, () => this.followupsApi.getPostAppointmentFollowups(this.postAppointmentQuery(false), scope), value => { this.setPostAppointmentPayload(value); });
    } finally { if (this.postAppointmentRequestScope === scope) this.postAppointmentRequestScope = null; scope.cancel(); }
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

  public async loadFollowupsView(scope: RequestScope): Promise<void> {
    this.postAppointmentRequestScope?.cancel();
    await loadSections(scope, [this.loads.appointments.load(scope, () => this.followupsApi.getPostAppointmentFollowups(this.postAppointmentQuery(true), scope), value => { this.setPostAppointmentPayload(value); })]);
  }

  public disposeFollowupRequests(): void {
    if (this.postAppointmentSearchTimer !== null) window.clearTimeout(this.postAppointmentSearchTimer);
    this.postAppointmentRequestScope?.cancel();
  }

  private get ui() { return this.injector.get(DASHBOARD_FOLLOWUPS_UI); }

  private get navigation() { return this.injector.get(DASHBOARD_FOLLOWUPS_NAVIGATION); }

  private get presentation() { return this.injector.get(DASHBOARD_FOLLOWUPS_PRESENTATION); }

  public loadReminders(scope: RequestScope): Promise<boolean> {
    return this.loads.reminders.load(scope, () => this.followupsApi.getAppointmentReminders(scope), value => { this.appointmentReminderStatus.set(value); });
  }
}
