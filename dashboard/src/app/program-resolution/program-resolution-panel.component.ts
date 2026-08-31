import { Component, computed, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ServiceOrder } from '../appointment-api.service';
import { DASHBOARD_VIEW_FACADE } from '../dashboard-view.facade';
import { ViewStateComponent } from '../view-state/view-state.component';
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
} from './program-resolution';

@Component({
  selector: 'app-program-resolution-panel',
  standalone: true,
  imports: [FormsModule, ViewStateComponent],
  templateUrl: './program-resolution-panel.component.html',
  styleUrl: './program-resolution-panel.component.css',
})
export class ProgramResolutionPanelComponent {
  protected readonly view = inject(DASHBOARD_VIEW_FACADE);
  readonly order = input.required<ServiceOrder>();

  protected readonly programResolutionChoice = signal<ProgramResolutionChoice>('');
  protected readonly programResolutionSelectedExpediente = signal('');
  protected readonly programResolutionCommercialMode = signal<ProgramResolutionCommercialMode>('');
  protected readonly programResolutionSameTermsConfirmed = signal(false);
  protected readonly programResolutionCustomInheritanceConfirmed = signal(false);
  protected readonly programResolutionCommunicationDecision = signal<
    '' | ProgramResolutionCommunicationDecision
  >('');
  protected readonly programResolutionChildren = signal<Record<string, ProgramResolutionChildDraft>>(
    {},
  );
  protected readonly programResolutionResult = signal<ProgramResolutionResponse | null>(null);
  protected readonly programResolutionDetails = computed(() =>
    readProgramResolutionDetails(this.view.selectedOrderDetail()?.preflight_details),
  );
  protected readonly pendingResolutionPrograms = computed(() =>
    filterPendingResolutionPrograms(this.programResolutionDetails()),
  );

  constructor() {
    this.resetProgramResolutionForm();
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

  protected chooseCommunicationDecision(
    value: ProgramResolutionCommunicationDecision,
  ): void {
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
    return (
      this.programResolutionChildren()[expediente] ?? {
        reservationPrice: this.order().reservation_price,
        chargeRequired: this.order().charge_required,
      }
    );
  }

  protected canSubmitProgramResolution(): boolean {
    return buildProgramResolution(this.programResolutionDraftInput()).ok;
  }

  protected requestProgramResolution(): void {
    const result = buildProgramResolution(this.programResolutionDraftInput());
    if (!result.ok) {
      this.view.errorMessage.set(result.error);
      return;
    }
    this.view.requestProgramResolution(result.payload, result.confirmationLabel, (response) => {
      this.programResolutionResult.set(response);
    });
  }

  private programResolutionDraftInput(): ProgramResolutionDraftInput {
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
      order: this.order(),
    };
  }

  private hydrateProgramResolutionChildren(): void {
    this.programResolutionChildren.set(
      defaultProgramResolutionChildren(
        this.pendingResolutionPrograms(),
        this.order(),
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
