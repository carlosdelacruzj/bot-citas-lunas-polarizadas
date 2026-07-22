import { ChangeDetectionStrategy, Component, ViewEncapsulation, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { DASHBOARD_VIEW_FACADE } from '../../dashboard-view.facade';

@Component({
  selector: 'app-orders-view',
  imports: [FormsModule],
  templateUrl: './orders-view.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
})
export class OrdersViewComponent {
  protected readonly dashboard = inject(DASHBOARD_VIEW_FACADE);
}
