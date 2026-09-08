import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  DASHBOARD_FINANCE_ENTRY_MODAL_ORDERLIST,
  DASHBOARD_FINANCE_ENTRY_MODAL_SHELL,
} from '../dashboard-domain.ports';


@Component({
  selector: 'app-finance-entry-modal',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './finance-entry-modal.component.html',
})
export class FinanceEntryModalComponent {
  protected readonly shell = inject(DASHBOARD_FINANCE_ENTRY_MODAL_SHELL);
  protected readonly orderList = inject(DASHBOARD_FINANCE_ENTRY_MODAL_ORDERLIST);

}
