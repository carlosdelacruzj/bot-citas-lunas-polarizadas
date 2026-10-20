import { ChangeDetectionStrategy, Component, inject, input } from '@angular/core';
import {
  DASHBOARD_ORDERS_VIEW_ORDERS, DASHBOARD_ORDERS_VIEW_MESSAGES,
  DASHBOARD_ORDERS_VIEW_PRESENTATION, DASHBOARD_ORDERS_VIEW_UI,
  DASHBOARD_ORDERS_VIEW_FINANCE,
} from '../dashboard-domain.ports';
import { FocusBoundaryDirective } from '../focus-boundary.directive';
import { LoadStatusComponent } from '../load-status/load-status.component';

@Component({
  selector: 'app-order-detail-panel',
  imports: [FocusBoundaryDirective, LoadStatusComponent],
  templateUrl: './order-detail-panel.component.html',
  styleUrl: './order-detail-panel.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class OrderDetailPanelComponent {
  readonly docked = input(false);
  protected readonly ordersDomain = inject(DASHBOARD_ORDERS_VIEW_ORDERS);
  protected readonly messagesDomain = inject(DASHBOARD_ORDERS_VIEW_MESSAGES);
  protected readonly presentationDomain = inject(DASHBOARD_ORDERS_VIEW_PRESENTATION);
  protected readonly uiDomain = inject(DASHBOARD_ORDERS_VIEW_UI);
  protected readonly financeDomain = inject(DASHBOARD_ORDERS_VIEW_FINANCE);
}
