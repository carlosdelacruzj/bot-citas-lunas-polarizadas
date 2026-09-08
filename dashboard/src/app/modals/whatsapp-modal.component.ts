import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DASHBOARD_WHATSAPP_MODAL_SHELL } from '../dashboard-domain.ports';


@Component({
  selector: 'app-whatsapp-modal',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './whatsapp-modal.component.html',
})
export class WhatsappModalComponent {
  protected readonly shellDomain = inject(DASHBOARD_WHATSAPP_MODAL_SHELL);

}
