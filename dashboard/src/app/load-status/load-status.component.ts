import { ChangeDetectionStrategy, Component, input } from '@angular/core';
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
export class LoadStatusComponent {
  readonly section = input<LoadSection>();
  protected formatUpdated(value: Date): string {
    return formatPeruDateTime(value.toISOString());
  }
}
