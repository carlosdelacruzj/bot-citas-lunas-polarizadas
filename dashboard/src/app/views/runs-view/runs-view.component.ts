import { ChangeDetectionStrategy, Component, ViewEncapsulation, inject, signal, DestroyRef } from '@angular/core';
import { ApiTransport } from '../../api/shared/api-transport';
import type { RunDetail } from '../../api/operations/operations.contracts';
import { FocusBoundaryDirective } from '../../focus-boundary.directive';
import { RequestScope } from '../../request-cancellation';
import { FormsModule } from '@angular/forms';
import {
  DASHBOARD_RUNS_VIEW_OPERATIONS,
  DASHBOARD_RUNS_VIEW_PRESENTATION,
} from '../../dashboard-domain.ports';
import { LoadStatusComponent } from '../../load-status/load-status.component';

import { ViewStateComponent } from '../../view-state/view-state.component';

@Component({
  selector: 'app-runs-view',
  imports: [LoadStatusComponent, FormsModule, ViewStateComponent, FocusBoundaryDirective],
  templateUrl: './runs-view.component.html',
  styleUrl: './runs-view.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
})
export class RunsViewComponent {
  protected readonly operationsDomain = inject(DASHBOARD_RUNS_VIEW_OPERATIONS);
  protected readonly presentationDomain = inject(DASHBOARD_RUNS_VIEW_PRESENTATION);

  private readonly transport = inject(ApiTransport);
  private evidenceScope: RequestScope | null = null;
  protected readonly evidenceRun = signal<RunDetail | null>(null);
  protected readonly evidenceIndex = signal(0);
  protected readonly evidenceUrl = signal('');
  protected readonly evidenceLoading = signal(false);
  protected readonly evidenceError = signal('');
  protected readonly evidenceZoom = signal(false);

  constructor() {
    inject(DestroyRef).onDestroy(() => this.closeEvidence());
  }

  protected readonly expandedDatesRun = signal<string | null>(null);

  protected availabilityDates(run: RunDetail): Array<{
    date: string; queried: boolean; hours: Array<{ hour: string; slots: string | null; site: string }>;
  }> {
    const details = run.details ?? {};
    type Appointment = { date?: string; hour?: string; slots?: string; site?: string };
    const collection = details['observer_evidence_collection'] as
      { session_captures?: Appointment[]; session_schedule?: Array<{ date?: string; hours?: string[] }> } | undefined;
    const observation = details['selection_observation'] as
      { visible_dates?: string[]; observed_appointments?: Appointment[] } | undefined;
    const rawDates = details['date_options'] ?? observation?.visible_dates ?? [];
    const dates = new Set<string>();
    const validDate = (value: unknown): value is string =>
      typeof value === 'string' && /^\d{2}\/\d{2}\/\d{4}$/.test(value);
    if (Array.isArray(rawDates)) rawDates.filter(validDate).forEach(date => dates.add(date));
    const captures = Array.isArray(collection?.session_captures) ? collection.session_captures : [];
    const observed = Array.isArray(observation?.observed_appointments) ? observation.observed_appointments : [];
    [...captures, ...observed].forEach(item => { if (validDate(item.date)) dates.add(item.date); });
    const schedule = Array.isArray(collection?.session_schedule) ? collection.session_schedule : [];
    schedule.forEach(item => { if (validDate(item.date)) dates.add(item.date); });
    const primary = run.availability;
    if (validDate(primary?.date)) dates.add(primary.date);
    const sortDate = (value: string) => value.split('/').reverse().join('-');
    return [...dates].sort((a, b) => sortDate(a).localeCompare(sortDate(b))).map(date => {
      const hours = new Map<string, { hour: string; slots: string | null; site: string }>();
      const addHour = (hour: unknown, slots: unknown, site: unknown) => {
        if (typeof hour !== 'string' || !/^\d{2}:\d{2}$/.test(hour)) return;
        const verified = Number.isFinite(Number(slots)) && Number(slots) > 0;
        const previous = hours.get(hour);
        if (previous?.slots && !verified) return;
        hours.set(hour, { hour, slots: verified ? String(slots) : null,
          site: typeof site === 'string' ? site : '' });
      };
      schedule.filter(item => item.date === date).forEach(item => {
        if (Array.isArray(item.hours)) item.hours.forEach(hour => addHour(hour, null, primary?.site));
      });
      observed.filter(item => item.date === date).forEach(item => addHour(item.hour, null, primary?.site));
      if (primary?.date === date) {
        const listedHours = details['hour_options'];
        if (Array.isArray(listedHours)) listedHours.forEach(hour => addHour(hour, null, primary.site));
        addHour(primary.hour, primary.slots, primary.site);
      }
      captures.filter(item => item.date === date).forEach(item => addHour(item.hour, item.slots, item.site));
      return { date, queried: schedule.some(item => item.date === date), hours: [...hours.values()].sort((a, b) => a.hour.localeCompare(b.hour)) };
    });
  }

  protected scheduleStatusMessage(run: RunDetail): string {
    const collection = run.details?.['observer_evidence_collection'] as { schedule_status?: string } | undefined;
    const messages: Record<string, string> = {
      interrupted: 'La lectura de horarios se interrumpió para atender trabajo pendiente o cerrar la sesión.',
      time_limit: 'La lectura alcanzó su límite de tiempo. Se muestran los horarios obtenidos.',
      timeout: 'El portal no confirmó la actualización de una fecha. Se conservaron los horarios leídos y una captura del fallo.',
    };
    return messages[collection?.schedule_status ?? ''] ?? '';
  }

  protected hasVerifiedAvailability(run: RunDetail): boolean {
    return Number(run.availability?.slots) > 0 && !!run.availability?.hour;
  }

  protected dateParts(date: string): { day: string; month: string; weekday: string } {
    const [day, month, year] = date.split('/').map(Number);
    const value = new Date(year, month - 1, day);
    return { day: String(day).padStart(2, '0'),
      month: value.toLocaleDateString('es-PE', { month: 'short', year: 'numeric' }),
      weekday: value.toLocaleDateString('es-PE', { weekday: 'long' }) };
  }

  protected async openEvidence(run: RunDetail, index: number): Promise<void> {
    this.releaseEvidence();
    this.evidenceRun.set(run);
    this.evidenceIndex.set(index);
    this.evidenceError.set('');
    this.evidenceZoom.set(false);
    this.evidenceLoading.set(true);
    const scope = new RequestScope();
    this.evidenceScope = scope;
    try {
      const blob = await this.transport.blob(`/api/v1/runs/${encodeURIComponent(run.run_id)}/screenshots/${index}`, scope);
      if (scope.isCancelled || this.evidenceScope !== scope) return;
      const dataUrl = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(blob);
      });
      if (scope.isCancelled || this.evidenceScope !== scope) return;
      this.evidenceUrl.set(dataUrl);
    } catch {
      if (!scope.isCancelled) this.evidenceError.set('No se pudo abrir la captura. Puede haber sido eliminada; vuelve a seleccionar la imagen para intentar de nuevo.');
    } finally {
      if (this.evidenceScope === scope) this.evidenceLoading.set(false);
    }
  }

  protected moveEvidence(delta: number): void {
    const run = this.evidenceRun();
    if (run) void this.openEvidence(run, this.evidenceIndex() + delta);
  }

  protected closeEvidence(): void {
    this.releaseEvidence();
    this.evidenceRun.set(null);
  }

  private releaseEvidence(): void {
    this.evidenceScope?.cancel();
    this.evidenceScope = null;
    this.evidenceUrl.set('');
  }
}
