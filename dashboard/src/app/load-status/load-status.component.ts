import { ChangeDetectionStrategy, Component, OnDestroy, input, signal } from '@angular/core';
import type { LoadSection } from '../load-section';
import { formatPeruDateTime } from '../peru-date-time';

@Component({
  selector: 'app-load-status',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (section(); as state) {
      <p class="load-status" [class.load-error]="state.error()" role="status">
        <strong>{{ state.label }}:</strong>
        @if (state.loading()) { actualizando. }
        @if (state.error(); as error) { {{ error }} }
        @if (state.updatedAt(); as updated) {
          {{ state.error() ? 'Datos anteriores del' : 'Actualizado el' }}
          {{ formatUpdated(updated) }}.
        } @else if (!state.loading()) { Sin datos actualizados. }
      </p>
    }
  `,
  styles: `
    :host { display: block; }
    .load-status { margin: .35rem 0; font-size: .8rem; color: #475569; }
    .load-error { color: #9a3412; }
  `,
})
export class LoadStatusComponent implements OnDestroy {
  private readonly currentTime = signal(Date.now());
  private readonly clock = window.setInterval(() => this.currentTime.set(Date.now()), 30_000);
  ngOnDestroy(): void { window.clearInterval(this.clock); }
  readonly section = input<LoadSection>();
  protected formatUpdated(value: Date): string {
    const minutes = Math.max(0, Math.floor((this.currentTime() - value.getTime()) / 60_000));
    const age = minutes === 0 ? 'hace un momento' : minutes < 60 ? `hace ${minutes} min` : `hace ${Math.floor(minutes / 60)} h`;
    return `${formatPeruDateTime(value.toISOString())} (${age})`;
  }
}
