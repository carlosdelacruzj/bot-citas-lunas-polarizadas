import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { DASHBOARD_VIEW_FACADE } from '../dashboard-view.facade';

@Component({
  selector: 'app-finance-entry-modal',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './finance-entry-modal.component.html',
})
export class FinanceEntryModalComponent {
  protected readonly view = inject(DASHBOARD_VIEW_FACADE);
}
