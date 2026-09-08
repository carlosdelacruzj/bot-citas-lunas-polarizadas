import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  DASHBOARD_ORDER_ACTIONS_MODAL_ORDERS,
  DASHBOARD_ORDER_ACTIONS_MODAL_SHELL,
} from '../dashboard-domain.ports';


@Component({
  selector: 'app-order-actions-modal',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './order-actions-modal.component.html',
})
export class OrderActionsModalComponent {
  protected readonly shell = inject(DASHBOARD_ORDER_ACTIONS_MODAL_SHELL);
  protected readonly orders = inject(DASHBOARD_ORDER_ACTIONS_MODAL_ORDERS);

}
