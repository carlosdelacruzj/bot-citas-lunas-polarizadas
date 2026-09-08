import { ChangeDetectionStrategy, Component, ViewEncapsulation, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import {
  DASHBOARD_SUMMARY_VIEW_CAPTCHAS,
  DASHBOARD_SUMMARY_VIEW_FINANCE,
  DASHBOARD_SUMMARY_VIEW_FOLLOWUPS,
  DASHBOARD_SUMMARY_VIEW_NAVIGATION,
  DASHBOARD_SUMMARY_VIEW_OPERATIONS,
  DASHBOARD_SUMMARY_VIEW_ORDERLIST,
  DASHBOARD_SUMMARY_VIEW_ORDERS,
  DASHBOARD_SUMMARY_VIEW_PRESENTATION,
  DASHBOARD_SUMMARY_VIEW_UI,
} from '../../dashboard-domain.ports';
import { LoadStatusComponent } from '../../load-status/load-status.component';

@Component({
  selector: 'app-summary-view',
  imports: [LoadStatusComponent, FormsModule, RouterLink],
  templateUrl: './summary-view.component.html',
  styleUrl: './summary-view.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
})
export class SummaryViewComponent {
  protected readonly ordersDomain = inject(DASHBOARD_SUMMARY_VIEW_ORDERS);
  protected readonly financeDomain = inject(DASHBOARD_SUMMARY_VIEW_FINANCE);
  protected readonly followupsDomain = inject(DASHBOARD_SUMMARY_VIEW_FOLLOWUPS);
  protected readonly presentationDomain = inject(DASHBOARD_SUMMARY_VIEW_PRESENTATION);
  protected readonly operationsDomain = inject(DASHBOARD_SUMMARY_VIEW_OPERATIONS);
  protected readonly orderList = inject(DASHBOARD_SUMMARY_VIEW_ORDERLIST);
  protected readonly captchasDomain = inject(DASHBOARD_SUMMARY_VIEW_CAPTCHAS);
  protected readonly uiDomain = inject(DASHBOARD_SUMMARY_VIEW_UI);
  protected readonly navigationDomain = inject(DASHBOARD_SUMMARY_VIEW_NAVIGATION);

}
