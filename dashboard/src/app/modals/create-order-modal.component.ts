import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  DASHBOARD_CREATE_ORDER_MODAL_ORDERS,
  DASHBOARD_CREATE_ORDER_MODAL_PRESENTATION,
  DASHBOARD_CREATE_ORDER_MODAL_UI,
} from '../dashboard-domain.ports';

import {
  ReservationRulesEditorComponent,
} from '../reservation-rules-editor/reservation-rules-editor.component';

@Component({
  selector: 'app-create-order-modal',
  standalone: true,
  imports: [FormsModule, ReservationRulesEditorComponent],
  templateUrl: './create-order-modal.component.html',
})
export class CreateOrderModalComponent {
  protected readonly uiDomain = inject(DASHBOARD_CREATE_ORDER_MODAL_UI);
  protected readonly ordersDomain = inject(DASHBOARD_CREATE_ORDER_MODAL_ORDERS);
  protected readonly presentationDomain = inject(DASHBOARD_CREATE_ORDER_MODAL_PRESENTATION);

}
