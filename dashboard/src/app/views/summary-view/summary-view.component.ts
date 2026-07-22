import { Component, Input, ViewEncapsulation } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { DashboardViewFacade } from '../../dashboard-view.facade';

@Component({
  selector: 'app-summary-view',
  imports: [FormsModule],
  templateUrl: './summary-view.component.html',
  encapsulation: ViewEncapsulation.None,
})
export class SummaryViewComponent {
  @Input({ required: true }) dashboard!: DashboardViewFacade;
}
