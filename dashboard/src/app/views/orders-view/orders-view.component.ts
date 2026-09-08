import { ChangeDetectionStrategy, Component, ViewEncapsulation, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  DASHBOARD_ORDERS_VIEW_ORDERLIST,
  DASHBOARD_ORDERS_VIEW_ORDERS,
  DASHBOARD_ORDERS_VIEW_SHELL,
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
  protected readonly shell = inject(DASHBOARD_ORDERS_VIEW_SHELL);
  protected readonly orders = inject(DASHBOARD_ORDERS_VIEW_ORDERS);
  protected readonly orderList = inject(DASHBOARD_ORDERS_VIEW_ORDERLIST);

}
