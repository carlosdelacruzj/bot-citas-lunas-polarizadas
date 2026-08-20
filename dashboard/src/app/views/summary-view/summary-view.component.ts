import { ChangeDetectionStrategy, Component, ViewEncapsulation, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { DASHBOARD_VIEW_FACADE } from '../../dashboard-view.facade';

@Component({
  selector: 'app-summary-view',
  imports: [FormsModule, RouterLink],
  templateUrl: './summary-view.component.html',
  styleUrl: './summary-view.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
})
export class SummaryViewComponent {
  protected readonly dashboard = inject(DASHBOARD_VIEW_FACADE);
}
