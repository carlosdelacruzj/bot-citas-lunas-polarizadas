import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  DASHBOARD_WHATSAPP_MODAL_MESSAGES,
  DASHBOARD_WHATSAPP_MODAL_PRESENTATION,
  DASHBOARD_WHATSAPP_MODAL_UI,
} from '../dashboard-domain.ports';


@Component({
  selector: 'app-whatsapp-modal',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './whatsapp-modal.component.html',
})
export class WhatsappModalComponent {
  protected readonly uiDomain = inject(DASHBOARD_WHATSAPP_MODAL_UI);
  protected readonly messagesDomain = inject(DASHBOARD_WHATSAPP_MODAL_MESSAGES);
  protected readonly presentationDomain = inject(DASHBOARD_WHATSAPP_MODAL_PRESENTATION);

}
