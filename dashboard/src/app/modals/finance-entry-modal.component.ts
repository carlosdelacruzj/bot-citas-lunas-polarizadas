import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  DASHBOARD_FINANCE_ENTRY_MODAL_FINANCE,
  DASHBOARD_FINANCE_ENTRY_MODAL_ORDERLIST,
  DASHBOARD_FINANCE_ENTRY_MODAL_UI,
} from '../dashboard-domain.ports';


@Component({
  selector: 'app-finance-entry-modal',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './finance-entry-modal.component.html',
})
export class FinanceEntryModalComponent {
  protected readonly uiDomain = inject(DASHBOARD_FINANCE_ENTRY_MODAL_UI);
  protected readonly financeDomain = inject(DASHBOARD_FINANCE_ENTRY_MODAL_FINANCE);
  protected readonly orderList = inject(DASHBOARD_FINANCE_ENTRY_MODAL_ORDERLIST);

}
