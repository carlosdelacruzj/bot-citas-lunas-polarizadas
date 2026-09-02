import { ChangeDetectionStrategy, Component, EventEmitter, Input, Output } from '@angular/core';

export type ViewStateKind = 'loading' | 'empty' | 'error' | 'stale' | 'refreshing';

@Component({
  selector: 'app-view-state',
  templateUrl: './view-state.component.html',
  styleUrl: './view-state.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ViewStateComponent {
  @Input({ required: true }) state: ViewStateKind = 'loading';
  @Input() title = '';
  @Input() message = '';
  @Input() retryLabel = 'Reintentar';
  @Input() skeletonRows = 3;
  @Input() compact = false;

  @Output() readonly retry = new EventEmitter<void>();

  protected skeletonItems(): number[] {
    return Array.from({ length: Math.max(1, this.skeletonRows) }, (_, index) => index);
  }
}
