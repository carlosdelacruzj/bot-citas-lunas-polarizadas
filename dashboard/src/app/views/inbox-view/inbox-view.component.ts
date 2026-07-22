import { ChangeDetectionStrategy, Component, Input, ViewEncapsulation } from '@angular/core';

import { DashboardViewFacade } from '../../dashboard-view.facade';

@Component({
  selector: 'app-inbox-view',
  templateUrl: './inbox-view.component.html',
  styleUrl: './inbox-view.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
})
export class InboxViewComponent {
  @Input({ required: true }) dashboard!: DashboardViewFacade;
}
