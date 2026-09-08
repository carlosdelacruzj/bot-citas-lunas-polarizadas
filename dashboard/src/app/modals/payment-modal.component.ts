import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  DASHBOARD_PAYMENT_MODAL_FINANCE,
  DASHBOARD_PAYMENT_MODAL_ORDERS,
  DASHBOARD_PAYMENT_MODAL_PRESENTATION,
  DASHBOARD_PAYMENT_MODAL_UI,
} from '../dashboard-domain.ports';


@Component({
  selector: 'app-payment-modal',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './payment-modal.component.html',
})
export class PaymentModalComponent {
  protected readonly uiDomain = inject(DASHBOARD_PAYMENT_MODAL_UI);
  protected readonly ordersDomain = inject(DASHBOARD_PAYMENT_MODAL_ORDERS);
  protected readonly presentationDomain = inject(DASHBOARD_PAYMENT_MODAL_PRESENTATION);
  protected readonly financeDomain = inject(DASHBOARD_PAYMENT_MODAL_FINANCE);

}
