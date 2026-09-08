import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  DASHBOARD_FINANCE_VIEW_FINANCE,
  DASHBOARD_FINANCE_VIEW_PRESENTATION,
  DASHBOARD_FINANCE_VIEW_UI,
} from '../../dashboard-domain.ports';
import { LoadStatusComponent } from '../../load-status/load-status.component';

import { ViewStateComponent } from '../../view-state/view-state.component';

@Component({
  selector: 'app-finance-view',
  imports: [LoadStatusComponent, FormsModule, ViewStateComponent],
  templateUrl: './finance-view.component.html',
  styleUrl: './finance-view.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FinanceViewComponent {
  protected readonly financeDomain = inject(DASHBOARD_FINANCE_VIEW_FINANCE);
  protected readonly presentationDomain = inject(DASHBOARD_FINANCE_VIEW_PRESENTATION);
  protected readonly uiDomain = inject(DASHBOARD_FINANCE_VIEW_UI);

}
