import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  DASHBOARD_EDIT_ORDER_MODAL_FINANCE,
  DASHBOARD_EDIT_ORDER_MODAL_ORDERS,
  DASHBOARD_EDIT_ORDER_MODAL_PRESENTATION,
  DASHBOARD_EDIT_ORDER_MODAL_UI,
} from '../dashboard-domain.ports';

import {
  ProgramResolutionPanelComponent,
} from '../program-resolution/program-resolution-panel.component';
import {
  ReservationRulesEditorComponent,
} from '../reservation-rules-editor/reservation-rules-editor.component';

@Component({
  selector: 'app-edit-order-modal',
  standalone: true,
  imports: [
    FormsModule,
    ProgramResolutionPanelComponent,
    ReservationRulesEditorComponent,
  ],
  templateUrl: './edit-order-modal.component.html',
})
export class EditOrderModalComponent {
  protected readonly uiDomain = inject(DASHBOARD_EDIT_ORDER_MODAL_UI);
  protected readonly ordersDomain = inject(DASHBOARD_EDIT_ORDER_MODAL_ORDERS);
  protected readonly presentationDomain = inject(DASHBOARD_EDIT_ORDER_MODAL_PRESENTATION);
  protected readonly financeDomain = inject(DASHBOARD_EDIT_ORDER_MODAL_FINANCE);

}
