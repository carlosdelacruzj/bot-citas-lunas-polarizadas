import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  DASHBOARD_FINANCE_VIEW_FINANCE,
  DASHBOARD_FINANCE_VIEW_SHELL,
} from '../../dashboard-domain.ports';

import { ViewStateComponent } from '../../view-state/view-state.component';

@Component({
  selector: 'app-finance-view',
  imports: [FormsModule, ViewStateComponent],
  templateUrl: './finance-view.component.html',
  styleUrl: './finance-view.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FinanceViewComponent {
  protected readonly financeDomain = inject(DASHBOARD_FINANCE_VIEW_FINANCE);
  protected readonly shellDomain = inject(DASHBOARD_FINANCE_VIEW_SHELL);

}
