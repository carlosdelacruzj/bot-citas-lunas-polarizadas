import { ChangeDetectionStrategy, Component, ViewEncapsulation, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  DASHBOARD_RUNS_VIEW_OPERATIONS,
  DASHBOARD_RUNS_VIEW_PRESENTATION,
} from '../../dashboard-domain.ports';
import { LoadStatusComponent } from '../../load-status/load-status.component';

import { ViewStateComponent } from '../../view-state/view-state.component';

@Component({
  selector: 'app-runs-view',
  imports: [LoadStatusComponent, FormsModule, ViewStateComponent],
  templateUrl: './runs-view.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
})
export class RunsViewComponent {
  protected readonly operationsDomain = inject(DASHBOARD_RUNS_VIEW_OPERATIONS);
  protected readonly presentationDomain = inject(DASHBOARD_RUNS_VIEW_PRESENTATION);

}
