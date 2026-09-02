import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { DASHBOARD_VIEW_FACADE } from '../dashboard-view.facade';

@Component({
  selector: 'app-order-actions-modal',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './order-actions-modal.component.html',
})
export class OrderActionsModalComponent {
  protected readonly view = inject(DASHBOARD_VIEW_FACADE);
}
