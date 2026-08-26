import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';

import { DASHBOARD_VIEW_FACADE } from '../../dashboard-view.facade';
import {
  apiErrorMessage,
  AppointmentApiService,
  AppointmentReminderStatus,
} from '../../appointment-api.service';
import { ViewStateComponent } from '../../view-state/view-state.component';

@Component({
  selector: 'app-followups-view',
  imports: [FormsModule, ViewStateComponent],
  templateUrl: './followups-view.component.html',
  styleUrl: './followups-view.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FollowupsViewComponent {
  protected readonly dashboard = inject(DASHBOARD_VIEW_FACADE);
  private readonly api = inject(AppointmentApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  protected readonly followupWorkspace = signal<'upcoming' | 'post_appointment' | 'history'>(
    this.readInitialWorkspace(),
  );
  protected readonly reminderStatus = signal<AppointmentReminderStatus | null>(
    this.dashboard.appointmentReminderStatus(),
  );
  protected readonly reminderStatusLoading = signal(this.reminderStatus() === null);
  protected readonly reminderStatusError = signal(false);
  protected readonly reminderEditorOpen = signal(false);
  protected readonly reminderMode = signal<'disabled' | 'dry_run' | 'canary' | 'live'>(
    'disabled',
  );
  protected readonly reminderCanaryOrderIds = signal<string[]>([]);
  protected readonly reminderSaving = signal(false);
  protected readonly reminderSaveError = signal<string | null>(null);
  protected readonly reminderSaveSuccess = signal<string | null>(null);
  protected readonly reminderActivationReview = signal(false);
  protected readonly postAppointmentOperationalCount = computed(
    () =>
      (this.dashboard.postAppointmentPayload()?.items ?? []).filter(
        (item: { outcome: string }) =>
          !['upcoming', 'completed', 'access_lost'].includes(item.outcome),
      ).length,
  );
  protected readonly postAppointmentHistoryCount = computed(
    () =>
      (this.dashboard.postAppointmentPayload()?.items ?? []).filter(
        (item: { outcome: string }) => ['completed', 'access_lost'].includes(item.outcome),
      ).length,
  );
  protected readonly postAppointmentCompletedCount = computed(
    () =>
      (this.dashboard.postAppointmentPayload()?.items ?? []).filter(
        (item: { outcome: string }) => item.outcome === 'completed',
      ).length,
  );
  protected readonly reminderCandidateSearch = signal('');
  protected readonly reminderCandidateSortKey = signal<
    'appointment_hour' | 'applicant' | 'site' | 'status'
  >('appointment_hour');
  protected readonly reminderCandidateSortDirection = signal<'asc' | 'desc'>('asc');
  protected readonly reminderCandidates = computed(() => {
    const search = this.reminderCandidateSearch().trim().toLocaleLowerCase('es');
    const direction = this.reminderCandidateSortDirection() === 'asc' ? 1 : -1;
    const candidates = (this.reminderStatus()?.candidates ?? []).filter(
      (candidate: {
        applicant_name: string | null;
        order_id: string;
        site: string | null;
        recipient: string;
        status: string;
      }) =>
        !search ||
        [
          candidate.applicant_name,
          candidate.order_id,
          candidate.site,
          candidate.recipient,
          candidate.status,
        ]
          .filter(Boolean)
          .some((value) => String(value).toLocaleLowerCase('es').includes(search)),
    );
    return [...candidates].sort((left, right) => {
      const key = this.reminderCandidateSortKey();
      let compared = 0;
      if (key === 'appointment_hour') {
        compared = (left.appointment_hour ?? '99:99').localeCompare(
          right.appointment_hour ?? '99:99',
        );
      } else if (key === 'applicant') {
        compared = (left.applicant_name ?? '').localeCompare(right.applicant_name ?? '', 'es', {
          numeric: true,
          sensitivity: 'base',
        });
      } else if (key === 'site') {
        compared = (left.site ?? '').localeCompare(right.site ?? '', 'es', {
          sensitivity: 'base',
        });
      } else {
        compared = left.status.localeCompare(right.status, 'es');
      }
      if (compared !== 0) {
        return compared * direction;
      }
      return left.order_id.localeCompare(right.order_id, 'es', { numeric: true });
    });
  });

  constructor() {
    this.dashboard.setPostAppointmentFilter(
      this.followupWorkspace() === 'history' ? 'history' : 'active',
    );
    void this.loadReminderStatus();
  }

  protected setFollowupWorkspace(
    workspace: 'upcoming' | 'post_appointment' | 'history',
  ): void {
    this.followupWorkspace.set(workspace);
    this.dashboard.setPostAppointmentFilter(workspace === 'history' ? 'history' : 'active');
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { tab: workspace },
      replaceUrl: true,
    });
  }

  protected setReminderCandidateSearch(value: string): void {
    this.reminderCandidateSearch.set(value);
  }

  protected chooseReminderCandidateSort(
    key: 'appointment_hour' | 'applicant' | 'site' | 'status',
  ): void {
    this.reminderCandidateSortKey.set(key);
    this.reminderCandidateSortDirection.set('asc');
  }

  protected toggleReminderCandidateSortDirection(): void {
    this.reminderCandidateSortDirection.set(
      this.reminderCandidateSortDirection() === 'asc' ? 'desc' : 'asc',
    );
  }

  protected reminderCandidateStatusLabel(status: string): string {
    const labels: Record<string, string> = {
      eligible: 'Elegible',
      missing_contact: 'Sin contacto',
      blocked: 'En espera del resumen',
      queued: 'En cola',
      running: 'Enviando',
      sent: 'Enviado',
      failed: 'Fallido',
      uncertain: 'Envío incierto',
      skipped: 'Omitido al revalidar',
    };
    return labels[status] ?? this.dashboard.statusLabel(status);
  }

  protected openReminderEditor(): void {
    this.reminderEditorOpen.set(!this.reminderEditorOpen());
    this.reminderActivationReview.set(false);
  }

  protected openReminderMessageEditor(): void {
    void this.router.navigate(['/mensajes'], {
      queryParams: { template: 'appointment_reminder' },
    });
  }

  protected chooseReminderMode(mode: 'disabled' | 'dry_run' | 'canary' | 'live'): void {
    this.reminderMode.set(mode);
    this.reminderActivationReview.set(false);
  }

  protected toggleReminderCanary(orderId: string): void {
    this.reminderCanaryOrderIds.update((values) =>
      values.includes(orderId)
        ? values.filter((value) => value !== orderId)
        : values.length < 2
          ? [...values, orderId]
          : values,
    );
    this.reminderActivationReview.set(false);
  }

  protected requestReminderSave(): void {
    this.reminderSaveError.set(null);
    if (this.reminderMode() === 'canary' && this.reminderCanaryOrderIds().length === 0) {
      this.reminderSaveError.set('Selecciona 1 o 2 citas para el modo canario.');
      return;
    }
    if (this.reminderMode() === 'canary' || this.reminderMode() === 'live') {
      this.reminderActivationReview.set(true);
      return;
    }
    void this.saveReminderControl();
  }

  protected confirmReminderSave(): void {
    void this.saveReminderControl();
  }

  private async saveReminderControl(): Promise<void> {
    const current = this.reminderStatus();
    if (!current || this.reminderSaving()) return;
    this.reminderSaving.set(true);
    this.reminderSaveError.set(null);
    this.reminderSaveSuccess.set(null);
    try {
      const updated = await this.api.updateAppointmentReminders({
        mode: this.reminderMode(),
        canary_order_ids:
          this.reminderMode() === 'canary' ? this.reminderCanaryOrderIds() : [],
        expected_revision: current.control.revision,
      });
      this.reminderStatus.set(updated);
      this.syncReminderEditor(updated);
      this.reminderSaveSuccess.set('Activación guardada. Se aplicará en la próxima revisión.');
    } catch (error) {
      this.reminderSaveError.set(apiErrorMessage(error));
    } finally {
      this.reminderSaving.set(false);
      this.reminderActivationReview.set(false);
    }
  }

  private readInitialWorkspace(): 'upcoming' | 'post_appointment' | 'history' {
    const tab = this.route.snapshot.queryParamMap.get('tab');
    return tab === 'post_appointment' || tab === 'history' ? tab : 'upcoming';
  }

  private async loadReminderStatus(): Promise<void> {
    try {
      const status = await this.api.getAppointmentReminders();
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
    this.reminderCanaryOrderIds.set(status.control.canary_order_ids);
  }
}
