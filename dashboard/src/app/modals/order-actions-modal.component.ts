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
  protected readonly shellDomain = inject(DASHBOARD_ORDER_ACTIONS_MODAL_SHELL);
  protected readonly ordersDomain = inject(DASHBOARD_ORDER_ACTIONS_MODAL_ORDERS);

}
