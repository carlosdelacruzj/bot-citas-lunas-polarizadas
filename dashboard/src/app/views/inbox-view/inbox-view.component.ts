import { ChangeDetectionStrategy, Component, ViewEncapsulation, inject } from '@angular/core';

import { DASHBOARD_VIEW_FACADE } from '../../dashboard-view.facade';

@Component({
  selector: 'app-inbox-view',
  templateUrl: './inbox-view.component.html',
  styleUrl: './inbox-view.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
})
export class InboxViewComponent {
  protected readonly dashboard = inject(DASHBOARD_VIEW_FACADE);
}
