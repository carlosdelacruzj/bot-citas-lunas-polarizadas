import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  DASHBOARD_WORKER_RESTART_MODAL_OPERATIONS,
  DASHBOARD_WORKER_RESTART_MODAL_UI,
} from '../dashboard-domain.ports';


@Component({
  selector: 'app-worker-restart-modal',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './worker-restart-modal.component.html',
})
export class WorkerRestartModalComponent {
  protected readonly uiDomain = inject(DASHBOARD_WORKER_RESTART_MODAL_UI);
  protected readonly operationsDomain = inject(DASHBOARD_WORKER_RESTART_MODAL_OPERATIONS);

}
