import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { DASHBOARD_VIEW_FACADE } from '../dashboard-view.facade';

@Component({
  selector: 'app-whatsapp-modal',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './whatsapp-modal.component.html',
})
export class WhatsappModalComponent {
  protected readonly view = inject(DASHBOARD_VIEW_FACADE);
}
