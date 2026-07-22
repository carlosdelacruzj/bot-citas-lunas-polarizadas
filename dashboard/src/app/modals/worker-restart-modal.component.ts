import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { DASHBOARD_VIEW_FACADE } from '../dashboard-view.facade';

@Component({
  selector: 'app-worker-restart-modal',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './worker-restart-modal.component.html',
})
export class WorkerRestartModalComponent {
  protected readonly view = inject(DASHBOARD_VIEW_FACADE);
}
