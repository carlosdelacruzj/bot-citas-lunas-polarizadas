import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  DASHBOARD_PAYMENT_MODAL_ORDERS,
  DASHBOARD_PAYMENT_MODAL_SHELL,
} from '../dashboard-domain.ports';


@Component({
  selector: 'app-payment-modal',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './payment-modal.component.html',
})
export class PaymentModalComponent {
  protected readonly shell = inject(DASHBOARD_PAYMENT_MODAL_SHELL);
  protected readonly orders = inject(DASHBOARD_PAYMENT_MODAL_ORDERS);

}
