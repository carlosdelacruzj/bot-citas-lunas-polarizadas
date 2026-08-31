import { Component, computed, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { DASHBOARD_VIEW_FACADE } from '../dashboard-view.facade';
import {
  buildProgramResolution,
  defaultProgramResolutionChildren,
  pendingResolutionPrograms as filterPendingResolutionPrograms,
  programResolutionDetails as readProgramResolutionDetails,
  ProgramResolutionChildDraft,
  ProgramResolutionChoice,
  ProgramResolutionCommercialMode,
  ProgramResolutionCommunicationDecision,
  ProgramResolutionDraftInput,
  ProgramResolutionResponse,
} from '../program-resolution/program-resolution';
import { ReservationRulesEditorComponent } from '../reservation-rules-editor/reservation-rules-editor.component';
import { ViewStateComponent } from '../view-state/view-state.component';

@Component({
  selector: 'app-edit-order-modal',
  standalone: true,
  imports: [FormsModule, ReservationRulesEditorComponent, ViewStateComponent],
  templateUrl: './edit-order-modal.component.html',
  styleUrl: './edit-order-modal.component.css',
})
export class EditOrderModalComponent {
  protected readonly view = inject(DASHBOARD_VIEW_FACADE);
  protected readonly programResolutionChoice = signal<ProgramResolutionChoice>('');
  protected readonly programResolutionSelectedExpediente = signal('');
  protected readonly programResolutionCommercialMode = signal<ProgramResolutionCommercialMode>('');
  protected readonly programResolutionSameTermsConfirmed = signal(false);
  protected readonly programResolutionCustomInheritanceConfirmed = signal(false);
  protected readonly programResolutionCommunicationDecision = signal<
    '' | ProgramResolutionCommunicationDecision
  >('');
  protected readonly programResolutionChildren = signal<
    Record<string, ProgramResolutionChildDraft>
  >({});
  protected readonly programResolutionResult = signal<ProgramResolutionResponse | null>(null);
  protected readonly programResolutionDetails = computed(() =>
    readProgramResolutionDetails(this.view.selectedOrderDetail()?.preflight_details),
  );
  protected readonly pendingResolutionPrograms = computed(() =>
    filterPendingResolutionPrograms(this.programResolutionDetails()),
  );

  private resolutionModalWasOpen = false;

  constructor() {
    effect(() => {
      const isOpen =
        this.view.activeModal() === 'edit-order' &&
        this.view.editOrderSection() === 'program-resolution';
      if (isOpen && !this.resolutionModalWasOpen) {
        this.resetProgramResolutionForm();
      }
      this.resolutionModalWasOpen = isOpen;
    });
  }

  protected chooseProgramResolution(value: ProgramResolutionChoice): void {
    this.programResolutionChoice.set(value);
    this.programResolutionSelectedExpediente.set('');
    this.programResolutionCommercialMode.set('');
    this.programResolutionSameTermsConfirmed.set(false);
    this.programResolutionCustomInheritanceConfirmed.set(false);
    this.programResolutionResult.set(null);
    this.view.formDirty.set(true);
  }

  protected chooseProgramExpediente(value: string): void {
    this.programResolutionSelectedExpediente.set(value);
    this.view.formDirty.set(true);
  }

  protected chooseProgramResolutionCommercialMode(
    value: ProgramResolutionCommercialMode,
  ): void {
    this.programResolutionCommercialMode.set(value);
    this.programResolutionSameTermsConfirmed.set(false);
    this.programResolutionCustomInheritanceConfirmed.set(false);
    this.programResolutionResult.set(null);
    this.view.formDirty.set(true);
    if (value === 'custom') {
      this.hydrateProgramResolutionChildren();
    }
  }

  protected setSameTermsConfirmed(value: boolean): void {
    this.programResolutionSameTermsConfirmed.set(value);
    this.view.formDirty.set(true);
  }

  protected setCustomInheritanceConfirmed(value: boolean): void {
    this.programResolutionCustomInheritanceConfirmed.set(value);
    this.view.formDirty.set(true);
  }

  protected chooseCommunicationDecision(value: ProgramResolutionCommunicationDecision): void {
    this.programResolutionCommunicationDecision.set(value);
    this.view.formDirty.set(true);
  }

  protected updateProgramResolutionChildPrice(expediente: string, value: string): void {
    this.programResolutionChildren.update((children) => ({
      ...children,
      [expediente]: {
        ...this.programResolutionChildDraft(expediente),
        reservationPrice: value,
      },
    }));
    this.view.formDirty.set(true);
  }

  protected updateProgramResolutionChildCharge(expediente: string, value: boolean): void {
    this.programResolutionChildren.update((children) => ({
      ...children,
      [expediente]: {
        ...this.programResolutionChildDraft(expediente),
        chargeRequired: value,
      },
    }));
    this.view.formDirty.set(true);
  }

  protected programResolutionChildDraft(expediente: string): ProgramResolutionChildDraft {
    const order = this.view.selectedOrder();
    return (
      this.programResolutionChildren()[expediente] ?? {
        reservationPrice: order?.reservation_price ?? '',
        chargeRequired: order?.charge_required ?? true,
      }
    );
  }

  protected canSubmitProgramResolution(): boolean {
    const input = this.programResolutionDraftInput();
    return input !== null && buildProgramResolution(input).ok;
  }

  protected requestProgramResolution(): void {
    const input = this.programResolutionDraftInput();
    if (!input) {
      this.view.errorMessage.set('Selecciona la orden antes de configurar sus trámites.');
      return;
    }
    const result = buildProgramResolution(input);
    if (!result.ok) {
      this.view.errorMessage.set(result.error);
      return;
    }
    this.view.requestProgramResolution(result.payload, result.confirmationLabel, (response) => {
      this.programResolutionResult.set(response);
    });
  }

  private programResolutionDraftInput(): ProgramResolutionDraftInput | null {
    const order = this.view.selectedOrder();
    if (!order) {
      return null;
    }
    return {
      details: this.programResolutionDetails(),
      programs: this.pendingResolutionPrograms(),
      resolution: this.programResolutionChoice(),
      selectedExpediente: this.programResolutionSelectedExpediente(),
      commercialMode: this.programResolutionCommercialMode(),
      sameTermsConfirmed: this.programResolutionSameTermsConfirmed(),
      customInheritanceConfirmed: this.programResolutionCustomInheritanceConfirmed(),
      communicationDecision: this.programResolutionCommunicationDecision(),
      children: this.programResolutionChildren(),
      order,
    };
  }

  private hydrateProgramResolutionChildren(): void {
    const order = this.view.selectedOrder();
    if (!order) {
      return;
    }
    this.programResolutionChildren.set(
      defaultProgramResolutionChildren(
        this.pendingResolutionPrograms(),
        order,
        this.programResolutionChildren(),
      ),
    );
  }

  private resetProgramResolutionForm(): void {
    this.programResolutionChoice.set('');
    this.programResolutionSelectedExpediente.set('');
    this.programResolutionCommercialMode.set('');
    this.programResolutionSameTermsConfirmed.set(false);
    this.programResolutionCustomInheritanceConfirmed.set(false);
    this.programResolutionCommunicationDecision.set('');
    this.programResolutionChildren.set({});
    this.programResolutionResult.set(null);
    this.view.formDirty.set(false);
  }
}
