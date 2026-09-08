import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  DASHBOARD_ORDER_ACTIONS_MODAL_ORDERS,
  DASHBOARD_ORDER_ACTIONS_MODAL_PRESENTATION,
  DASHBOARD_ORDER_ACTIONS_MODAL_UI,
} from '../dashboard-domain.ports';


@Component({
  selector: 'app-order-actions-modal',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './order-actions-modal.component.html',
})
export class OrderActionsModalComponent {
  protected readonly uiDomain = inject(DASHBOARD_ORDER_ACTIONS_MODAL_UI);
  protected readonly ordersDomain = inject(DASHBOARD_ORDER_ACTIONS_MODAL_ORDERS);
  protected readonly presentationDomain = inject(DASHBOARD_ORDER_ACTIONS_MODAL_PRESENTATION);

}
