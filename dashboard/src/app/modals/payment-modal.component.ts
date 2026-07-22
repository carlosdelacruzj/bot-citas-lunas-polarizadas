import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { DASHBOARD_VIEW_FACADE } from '../dashboard-view.facade';

@Component({
  selector: 'app-payment-modal',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './payment-modal.component.html',
})
export class PaymentModalComponent {
  protected readonly view = inject(DASHBOARD_VIEW_FACADE);
}
