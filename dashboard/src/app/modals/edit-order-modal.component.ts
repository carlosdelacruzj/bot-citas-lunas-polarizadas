import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { DASHBOARD_VIEW_FACADE } from '../dashboard-view.facade';
import { ReservationRulesEditorComponent } from '../reservation-rules-editor/reservation-rules-editor.component';

@Component({
  selector: 'app-edit-order-modal',
  standalone: true,
  imports: [FormsModule, ReservationRulesEditorComponent],
  templateUrl: './edit-order-modal.component.html',
})
export class EditOrderModalComponent {
  protected readonly view = inject(DASHBOARD_VIEW_FACADE);
}

