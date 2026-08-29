import { FormsModule } from '@angular/forms';
import {
  ChangeDetectionStrategy,
  Component,
  ViewEncapsulation,
  computed,
  inject,
  signal,
} from '@angular/core';

import { DASHBOARD_VIEW_FACADE } from '../../dashboard-view.facade';
import { ViewStateComponent } from '../../view-state/view-state.component';

@Component({
  selector: 'app-inbox-view',
  imports: [FormsModule, ViewStateComponent],
  templateUrl: './inbox-view.component.html',
  styleUrl: './inbox-view.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
})
export class InboxViewComponent {
  protected readonly dashboard = inject(DASHBOARD_VIEW_FACADE);
  protected readonly taskSearch = signal('');
  protected readonly taskFilter = signal<'all' | 'access' | 'paused' | 'payment' | 'messages'>('all');

  protected readonly filters = computed(() => [
    { key: 'all' as const, label: 'Todos', count: this.dashboard.inboxPendingTotal() },
    { key: 'access' as const, label: 'Accesos', count: this.dashboard.inboxAccessCount() },
    { key: 'paused' as const, label: 'Pausados', count: this.dashboard.inboxPausedCount() },
    { key: 'payment' as const, label: 'Pagos', count: this.dashboard.inboxPaymentCount() },
    { key: 'messages' as const, label: 'Mensajes', count: this.dashboard.inboxMessageCount() },
  ]);

  protected readonly visibleTasks = computed(() => {
    const search = this.taskSearch().trim().toLocaleLowerCase('es');
    const filter = this.taskFilter();
    const severity = { bad: 0, warn: 1, neutral: 2 } as const;
    return [...this.dashboard.inboxOrderTasks()]
      .filter((task) => {
        const matchesFilter =
          filter === 'all' ||
          (filter === 'access' && task.kind === 'preflight') ||
          (filter === 'paused' && task.kind === 'paused') ||
          (filter === 'payment' && task.kind === 'payment') ||
          (filter === 'messages' && ['contact', 'whatsapp', 'followup', 'review'].includes(task.kind));
        if (!matchesFilter || !search) return matchesFilter;
        return [
          task.title,
          task.description,
          task.label,
          task.applicantName,
          task.documentNumberMasked,
          task.orderId,
        ]
          .filter(Boolean)
          .some((value) => String(value).toLocaleLowerCase('es').includes(search));
      })
      .sort((left, right) =>
        severity[left.tone as keyof typeof severity] -
          severity[right.tone as keyof typeof severity] ||
        left.updatedAt.localeCompare(right.updatedAt) ||
        left.key.localeCompare(right.key),
      );
  });

  protected chooseFilter(filter: 'all' | 'access' | 'paused' | 'payment' | 'messages'): void {
    this.taskFilter.set(filter);
  }

  protected taskAgeLabel(value: string): string {
    const timestamp = Date.parse(value);
    if (!Number.isFinite(timestamp)) return 'Actualización sin fecha';
    const minutes = Math.max(0, Math.floor((Date.now() - timestamp) / 60_000));
    if (minutes < 60) return minutes <= 1 ? 'Último cambio hace un momento' : `Último cambio hace ${minutes} min`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `Último cambio hace ${hours} h`;
    const days = Math.floor(hours / 24);
    return `Último cambio hace ${days} ${days === 1 ? 'día' : 'días'}`;
  }
}
