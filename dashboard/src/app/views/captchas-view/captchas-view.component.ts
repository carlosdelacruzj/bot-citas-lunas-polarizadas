import { ChangeDetectionStrategy, Component, ViewEncapsulation, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DASHBOARD_CAPTCHAS_VIEW_SHELL } from '../../dashboard-domain.ports';

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
  protected readonly shellDomain = inject(DASHBOARD_CAPTCHAS_VIEW_SHELL);

}
