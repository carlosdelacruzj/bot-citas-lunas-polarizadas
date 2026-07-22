import { Component, Input, ViewEncapsulation } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { DashboardViewFacade } from '../../dashboard-view.facade';

@Component({
  selector: 'app-captchas-view',
  imports: [FormsModule],
  templateUrl: './captchas-view.component.html',
  encapsulation: ViewEncapsulation.None,
})
export class CaptchasViewComponent {
  @Input({ required: true }) dashboard!: DashboardViewFacade;
}
