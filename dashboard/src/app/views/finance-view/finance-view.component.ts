import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { DASHBOARD_VIEW_FACADE } from '../../dashboard-view.facade';
import { ViewStateComponent } from '../../view-state/view-state.component';

@Component({
  selector: 'app-finance-view',
  imports: [FormsModule, ViewStateComponent],
  templateUrl: './finance-view.component.html',
  styleUrl: './finance-view.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FinanceViewComponent {
  protected readonly dashboard = inject(DASHBOARD_VIEW_FACADE);
}
