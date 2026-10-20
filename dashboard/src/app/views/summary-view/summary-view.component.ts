import { ChangeDetectionStrategy, Component, ViewEncapsulation, DestroyRef, computed, signal, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import {
  DASHBOARD_SUMMARY_VIEW_CAPTCHAS,
  DASHBOARD_SUMMARY_VIEW_FINANCE,
  DASHBOARD_SUMMARY_VIEW_FOLLOWUPS,
  DASHBOARD_SUMMARY_VIEW_NAVIGATION,
  DASHBOARD_SUMMARY_VIEW_OPERATIONS,
  DASHBOARD_SUMMARY_VIEW_ORDERLIST,
  DASHBOARD_SUMMARY_VIEW_ORDERS,
  DASHBOARD_SUMMARY_VIEW_PRESENTATION,
  DASHBOARD_SUMMARY_VIEW_UI,
} from '../../dashboard-domain.ports';
import { LoadStatusComponent } from '../../load-status/load-status.component';

@Component({
  selector: 'app-summary-view',
  imports: [LoadStatusComponent, FormsModule, RouterLink],
  templateUrl: './summary-view.component.html',
  styleUrl: './summary-view.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
})
export class SummaryViewComponent {
  private readonly now = signal(Date.now());
  private readonly destroyRef = inject(DestroyRef);

  constructor() {
    const clock = window.setInterval(() => this.now.set(Date.now()), 1000);
    this.destroyRef.onDestroy(() => window.clearInterval(clock));
  }

  protected readonly waiting = computed(() => {
    const worker = this.operationsDomain.worker();
    if (!worker?.worker_running || worker.paused ||
        !['retry_wait', 'backoff', 'recovery_backoff', 'outside_hot_window'].includes(worker.phase ?? '')) {
      return null;
    }
    const now = this.now();
    const next = Date.parse(worker.next_check_at ?? '');
    const last = Date.parse(worker.last_check_at ?? '');
    const loaded = this.operationsDomain.loads.worker.updatedAt();
    const stale = !!this.operationsDomain.loads.worker.error() || !loaded || now - loaded.getTime() > 60000;
    const remaining = Number.isFinite(next) ? Math.max(0, Math.ceil((next - now) / 1000)) : null;
    return {
      message: stale ? 'Esperando actualizar el estado de la búsqueda'
        : remaining === null ? 'Próxima revisión sin hora confirmada'
        : remaining === 0 ? 'Tiempo cumplido; esperando confirmar la nueva revisión'
        : 'Próxima revisión en ' + this.duration(remaining),
      elapsed: Number.isFinite(last) ? this.duration(Math.max(0, Math.floor((now - last) / 1000))) : null,
    };
  });

  private duration(seconds: number): string {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const rest = seconds % 60;
    return hours > 0 ? `${hours} h ${minutes} min ${rest} s`
      : minutes > 0 ? `${minutes} min ${rest} s` : `${rest} s`;
  }

  protected readonly ordersDomain = inject(DASHBOARD_SUMMARY_VIEW_ORDERS);
  protected readonly financeDomain = inject(DASHBOARD_SUMMARY_VIEW_FINANCE);
  protected readonly followupsDomain = inject(DASHBOARD_SUMMARY_VIEW_FOLLOWUPS);
  protected readonly presentationDomain = inject(DASHBOARD_SUMMARY_VIEW_PRESENTATION);
  protected readonly operationsDomain = inject(DASHBOARD_SUMMARY_VIEW_OPERATIONS);
  protected readonly orderList = inject(DASHBOARD_SUMMARY_VIEW_ORDERLIST);
  protected readonly captchasDomain = inject(DASHBOARD_SUMMARY_VIEW_CAPTCHAS);
  protected readonly uiDomain = inject(DASHBOARD_SUMMARY_VIEW_UI);
  protected readonly navigationDomain = inject(DASHBOARD_SUMMARY_VIEW_NAVIGATION);

}
