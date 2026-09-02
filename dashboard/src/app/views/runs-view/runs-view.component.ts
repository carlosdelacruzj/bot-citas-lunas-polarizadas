import { ChangeDetectionStrategy, Component, ViewEncapsulation, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { DASHBOARD_VIEW_FACADE } from '../../dashboard-view.facade';
import { ViewStateComponent } from '../../view-state/view-state.component';

@Component({
  selector: 'app-runs-view',
  imports: [FormsModule, ViewStateComponent],
  templateUrl: './runs-view.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
})
export class RunsViewComponent {
  protected readonly dashboard = inject(DASHBOARD_VIEW_FACADE);
}
