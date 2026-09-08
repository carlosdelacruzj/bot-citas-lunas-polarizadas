import { OrdersListFacade, type OrdersListView } from '../../domains/orders/orders-list.facade';
import { ChangeDetectionStrategy, Component, ViewEncapsulation, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { DASHBOARD_VIEW_FACADE } from '../../dashboard-view.facade';
import { ViewStateComponent } from '../../view-state/view-state.component';

@Component({
  selector: 'app-orders-view',
  imports: [FormsModule, ViewStateComponent],
  templateUrl: './orders-view.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
})
export class OrdersViewComponent {
  protected readonly orders: OrdersListView = inject(OrdersListFacade);
  protected readonly dashboard = inject(DASHBOARD_VIEW_FACADE);
}
