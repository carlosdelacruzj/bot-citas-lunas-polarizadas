import { ChangeDetectionStrategy, Component, ViewEncapsulation, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import {
  DASHBOARD_SUMMARY_VIEW_ORDERLIST,
  DASHBOARD_SUMMARY_VIEW_SHELL,
} from '../../dashboard-domain.ports';


@Component({
  selector: 'app-summary-view',
  imports: [FormsModule, RouterLink],
  templateUrl: './summary-view.component.html',
  styleUrl: './summary-view.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
})
export class SummaryViewComponent {
  protected readonly shell = inject(DASHBOARD_SUMMARY_VIEW_SHELL);
  protected readonly orderList = inject(DASHBOARD_SUMMARY_VIEW_ORDERLIST);

}
