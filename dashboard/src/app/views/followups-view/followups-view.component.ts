import { ChangeDetectionStrategy, Component, ViewEncapsulation, inject } from '@angular/core';

import { DASHBOARD_VIEW_FACADE } from '../../dashboard-view.facade';
import { ViewStateComponent } from '../../view-state/view-state.component';

@Component({
  selector: 'app-followups-view',
  imports: [ViewStateComponent],
  templateUrl: './followups-view.component.html',
  styleUrl: './followups-view.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
})
export class FollowupsViewComponent {
  protected readonly dashboard = inject(DASHBOARD_VIEW_FACADE);
}
