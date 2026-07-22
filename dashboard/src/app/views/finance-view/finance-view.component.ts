import { Component, Input, ViewEncapsulation } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { DashboardViewFacade } from '../../dashboard-view.facade';

@Component({
  selector: 'app-finance-view',
  imports: [FormsModule],
  templateUrl: './finance-view.component.html',
  encapsulation: ViewEncapsulation.None,
})
export class FinanceViewComponent {
  @Input({ required: true }) dashboard!: DashboardViewFacade;
}
