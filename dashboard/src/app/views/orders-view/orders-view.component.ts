import { ChangeDetectionStrategy, Component, ViewEncapsulation, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  DASHBOARD_ORDERS_VIEW_FINANCE,
  DASHBOARD_ORDERS_VIEW_MESSAGES,
  DASHBOARD_ORDERS_VIEW_ORDERLIST,
  DASHBOARD_ORDERS_VIEW_ORDERS,
  DASHBOARD_ORDERS_VIEW_PRESENTATION,
  DASHBOARD_ORDERS_VIEW_UI,
} from '../../dashboard-domain.ports';

import { ViewStateComponent } from '../../view-state/view-state.component';

@Component({
  selector: 'app-orders-view',
  imports: [FormsModule, ViewStateComponent],
  templateUrl: './orders-view.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
})
export class OrdersViewComponent {
  protected readonly messagesDomain = inject(DASHBOARD_ORDERS_VIEW_MESSAGES);
  protected readonly ordersDomain = inject(DASHBOARD_ORDERS_VIEW_ORDERS);
  protected readonly presentationDomain = inject(DASHBOARD_ORDERS_VIEW_PRESENTATION);
  protected readonly uiDomain = inject(DASHBOARD_ORDERS_VIEW_UI);
  protected readonly financeDomain = inject(DASHBOARD_ORDERS_VIEW_FINANCE);
  protected readonly orderList = inject(DASHBOARD_ORDERS_VIEW_ORDERLIST);

}
