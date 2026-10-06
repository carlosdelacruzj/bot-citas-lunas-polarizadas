import { FocusBoundaryDirective } from '../focus-boundary.directive';
import { Component, computed, inject } from '@angular/core';
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
import type { ProgramResolutionProgram } from '../program-resolution/program-resolution';
import {
  ReservationRulesEditorComponent,
} from '../reservation-rules-editor/reservation-rules-editor.component';

@Component({
  selector: 'app-edit-order-modal',
  standalone: true,
  imports: [FocusBoundaryDirective,
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
  protected readonly programAssessments = computed(() => {
    const details = this.ordersDomain.selectedOrderDetail()?.preflight_details;
    const rows = (details as Record<string, unknown> | null)?.['program_assessments'];
    return Array.isArray(rows) ? rows as ProgramResolutionProgram[] : [];
  });

}
