import { ChangeDetectionStrategy, Component, Input, ViewEncapsulation } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { DashboardViewFacade } from '../../dashboard-view.facade';

@Component({
  selector: 'app-runs-view',
  imports: [FormsModule],
  templateUrl: './runs-view.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
})
export class RunsViewComponent {
  @Input({ required: true }) dashboard!: DashboardViewFacade;
}
