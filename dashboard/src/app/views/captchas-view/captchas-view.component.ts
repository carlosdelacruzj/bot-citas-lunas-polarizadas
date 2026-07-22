import { ChangeDetectionStrategy, Component, ViewEncapsulation, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { DASHBOARD_VIEW_FACADE } from '../../dashboard-view.facade';
import { ViewStateComponent } from '../../view-state/view-state.component';

@Component({
  selector: 'app-captchas-view',
  imports: [FormsModule, ViewStateComponent],
  templateUrl: './captchas-view.component.html',
  styleUrl: './captchas-view.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
})
export class CaptchasViewComponent {
  protected readonly dashboard = inject(DASHBOARD_VIEW_FACADE);
}
