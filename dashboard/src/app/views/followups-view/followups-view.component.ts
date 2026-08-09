import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { DASHBOARD_VIEW_FACADE } from '../../dashboard-view.facade';
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
}
