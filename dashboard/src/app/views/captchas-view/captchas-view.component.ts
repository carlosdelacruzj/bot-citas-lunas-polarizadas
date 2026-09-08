import { ChangeDetectionStrategy, Component, ViewEncapsulation, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  DASHBOARD_CAPTCHAS_VIEW_CAPTCHAS,
  DASHBOARD_CAPTCHAS_VIEW_PRESENTATION,
} from '../../dashboard-domain.ports';
import { LoadStatusComponent } from '../../load-status/load-status.component';

import { ViewStateComponent } from '../../view-state/view-state.component';

@Component({
  selector: 'app-captchas-view',
  imports: [LoadStatusComponent, FormsModule, ViewStateComponent],
  templateUrl: './captchas-view.component.html',
  styleUrl: './captchas-view.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
})
export class CaptchasViewComponent {
  protected readonly captchasDomain = inject(DASHBOARD_CAPTCHAS_VIEW_CAPTCHAS);
  protected readonly presentationDomain = inject(DASHBOARD_CAPTCHAS_VIEW_PRESENTATION);

}
