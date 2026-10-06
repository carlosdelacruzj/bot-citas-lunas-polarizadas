import { HttpErrorResponse } from '@angular/common/http';
import { Injectable, computed, effect, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { MessagesApiClient } from '../../api/messages/messages-api.client';
import type { WhatsAppMessageTemplate } from '../../api/messages/messages.contracts';
import { apiErrorMessage } from '../../api/shared/api-error';

import {
  DASHBOARD_MESSAGE_TEMPLATES_VIEW_MESSAGES,
  DASHBOARD_MESSAGE_TEMPLATES_VIEW_PRESENTATION,
  DASHBOARD_MESSAGE_TEMPLATES_VIEW_UI,
} from '../../dashboard-domain.ports';
type PreviewState = 'ready' | 'loading' | 'error';

@Injectable()
export class MessageTemplateEditorFacade {
  public readonly messagesDomain = inject(DASHBOARD_MESSAGE_TEMPLATES_VIEW_MESSAGES);

  public readonly uiDomain = inject(DASHBOARD_MESSAGE_TEMPLATES_VIEW_UI);

  public readonly presentationDomain = inject(DASHBOARD_MESSAGE_TEMPLATES_VIEW_PRESENTATION);

  private readonly messagesApi = inject(MessagesApiClient);

  private readonly route = inject(ActivatedRoute);

  private previewTimer: number | null = null;

  private previewGeneration = 0;

  private hydratedRevision = 0;

  public readonly maxTemplateLength = 1500;

  public readonly selectedTemplateKey = signal(
    this.route.snapshot.queryParamMap.get('template') ?? '',
  );

  public readonly draft = signal('');

  public readonly preview = signal('');

  public readonly previewContext = signal<Record<string, string>>({});

  public readonly previewState = signal<PreviewState>('ready');

  public readonly previewError = signal<string | null>(null);

  public readonly saving = signal(false);

  public readonly saveReviewOpen = signal(false);

  public readonly saveError = signal<string | null>(null);

  public readonly saveSuccess = signal<string | null>(null);

  public readonly conflictCurrent = signal<WhatsAppMessageTemplate | null>(null);

  public readonly selectedTemplate = computed<WhatsAppMessageTemplate | null>(() => {
    const key = this.selectedTemplateKey();
    return (
      this.messagesDomain.whatsappMessageTemplates()
        .find((item: WhatsAppMessageTemplate) => item.template_key === key) ?? null
    );
  });

  public readonly isDirty = computed(
    () => this.draft() !== (this.selectedTemplate()?.message_template ?? ''),
  );

  public readonly previewContextEntries = computed(() =>
    Object.entries(this.previewContext()),
  );

  constructor() {
    effect(() => {
      const templates = this.messagesDomain.whatsappMessageTemplates() as WhatsAppMessageTemplate[];
      const editingPaused = this.uiDomain.formDirty();
      if (!templates.length || editingPaused) {
        return;
      }
      const selected =
        templates.find((item) => item.template_key === this.selectedTemplateKey()) ?? templates[0];
      if (
        selected.template_key !== this.selectedTemplateKey() ||
        selected.revision !== this.hydratedRevision
      ) {
        this.hydrate(selected);
      }
    });
  }

  ngOnDestroy(): void {
    if (this.previewTimer !== null) {
      window.clearTimeout(this.previewTimer);
    }
    this.previewGeneration += 1;
    this.uiDomain.formDirty.set(false);
  }

  public chooseTemplate(templateKey: string): void {
    const template = this.messagesDomain.whatsappMessageTemplates()
      .find((item: WhatsAppMessageTemplate) => item.template_key === templateKey);
    if (!template || templateKey === this.selectedTemplateKey()) {
      return;
    }
    if (
      this.isDirty() &&
      !window.confirm('Hay cambios sin guardar. ¿Quieres descartarlos y abrir otro mensaje?')
    ) {
      return;
    }
    this.uiDomain.formDirty.set(false);
    this.hydrate(template);
  }

  public onDraftChange(value: string): void {
    this.draft.set(value);
    this.saveReviewOpen.set(false);
    this.saveError.set(null);
    this.saveSuccess.set(null);
    this.conflictCurrent.set(null);
    this.uiDomain.formDirty.set(this.isDirty());
    this.schedulePreview();
  }

  public restoreRecommended(): void {
    const template = this.selectedTemplate();
    if (!template) {
      return;
    }
    this.onDraftChange(template.recommended_template);
  }

  public async requestSave(): Promise<void> {
    if (!this.selectedTemplate() || this.saving()) {
      return;
    }
    this.saveError.set(null);
    this.saveSuccess.set(null);
    if (!this.isDirty()) {
      this.saveSuccess.set('No hay cambios pendientes para guardar.');
      return;
    }
    const previewReady = await this.refreshPreview();
    if (previewReady) {
      this.saveReviewOpen.set(true);
    }
  }

  public cancelSaveReview(): void {
    this.saveReviewOpen.set(false);
  }

  public async confirmSave(): Promise<void> {
    const template = this.selectedTemplate();
    if (!template || this.saving()) {
      return;
    }
    this.saving.set(true);
    this.saveError.set(null);
    this.saveSuccess.set(null);
    try {
      const updated = await this.messagesApi.updateWhatsAppMessageTemplate(
        template.template_key,
        this.draft(),
        template.revision,
      );
      this.replaceTemplate(updated);
      this.uiDomain.formDirty.set(false);
      this.hydrate(updated);
      this.saveSuccess.set(
        `Revisión ${updated.revision} guardada. No se preparó ni envió ningún WhatsApp.`,
      );
    } catch (error) {
      if (error instanceof HttpErrorResponse && error.status === 409 && error.error?.current) {
        this.conflictCurrent.set(error.error.current as WhatsAppMessageTemplate);
        this.saveError.set(
          'Este mensaje cambió en otra ventana. Elige qué versión conservar antes de guardar.',
        );
      } else {
        this.saveError.set(apiErrorMessage(error));
      }
    } finally {
      this.saving.set(false);
      this.saveReviewOpen.set(false);
    }
  }

  public loadCurrentVersion(): void {
    const current = this.conflictCurrent();
    if (!current) {
      return;
    }
    this.replaceTemplate(current);
    this.uiDomain.formDirty.set(false);
    this.hydrate(current);
    this.saveSuccess.set(`Se cargó la revisión vigente ${current.revision}.`);
  }

  public keepDraftWithCurrentRevision(): void {
    const current = this.conflictCurrent();
    if (!current) {
      return;
    }
    this.replaceTemplate(current);
    this.hydratedRevision = current.revision;
    this.conflictCurrent.set(null);
    this.saveError.set(null);
    this.uiDomain.formDirty.set(this.draft() !== current.message_template);
    this.saveSuccess.set(
      `Tu borrador se conserva sobre la revisión ${current.revision}. Revísalo antes de guardar.`,
    );
  }

  public appliesFromLabel(value: WhatsAppMessageTemplate['applies_from']): string {
    return {
      next_prepared_job: 'Siguiente aviso preparado',
      next_prepared_message: 'Siguiente paquete preparado',
      next_prepared_followup: 'Siguiente postpago preparado',
      next_reconciliation: 'Siguiente revisión pre-cita',
    }[value];
  }

  public templateCode(templateKey: string): string {
    if (templateKey.startsWith('registration_')) return 'RG';
    if (templateKey === 'reservation_confirmation') return 'CITA';
    if (templateKey === 'reservation_payment') return 'S/';
    if (templateKey === 'post_payment_confirmation') return 'PDF';
    return '24H';
  }

  public isRequired(variable: string, template: WhatsAppMessageTemplate): boolean {
    return template.required_variables.includes(variable);
  }

  public refreshPreviewNow(): void {
    void this.refreshPreview();
  }

  private schedulePreview(): void {
    if (this.previewTimer !== null) {
      window.clearTimeout(this.previewTimer);
    }
    this.previewTimer = window.setTimeout(() => {
      this.previewTimer = null;
      void this.refreshPreview();
    }, 350);
  }

  private async refreshPreview(): Promise<boolean> {
    const template = this.selectedTemplate();
    if (!template) {
      return false;
    }
    const generation = ++this.previewGeneration;
    this.previewState.set('loading');
    this.previewError.set(null);
    try {
      const response = await this.messagesApi.previewWhatsAppMessageTemplate(
        template.template_key,
        this.draft(),
      );
      if (generation !== this.previewGeneration) {
        return false;
      }
      this.preview.set(response.preview);
      this.previewContext.set(response.preview_context);
      this.previewState.set('ready');
      return true;
    } catch (error) {
      if (generation !== this.previewGeneration) {
        return false;
      }
      this.previewState.set('error');
      this.previewError.set(apiErrorMessage(error));
      return false;
    }
  }

  private hydrate(template: WhatsAppMessageTemplate): void {
    this.previewGeneration += 1;
    if (this.previewTimer !== null) {
      window.clearTimeout(this.previewTimer);
      this.previewTimer = null;
    }
    this.selectedTemplateKey.set(template.template_key);
    this.draft.set(template.message_template);
    this.preview.set(template.preview);
    this.previewContext.set(template.preview_context);
    this.previewState.set('ready');
    this.previewError.set(null);
    this.saveReviewOpen.set(false);
    this.saveError.set(null);
    this.saveSuccess.set(null);
    this.conflictCurrent.set(null);
    this.hydratedRevision = template.revision;
    this.uiDomain.formDirty.set(false);
  }

  private replaceTemplate(updated: WhatsAppMessageTemplate): void {
    this.messagesDomain.whatsappMessageTemplates.update((templates: WhatsAppMessageTemplate[]) =>
      templates.map((item) =>
        item.template_key === updated.template_key ? updated : item,
      ),
    );
  }

}

export type MessageTemplateEditorFacadeView = Pick<MessageTemplateEditorFacade,
  "draft"
  | "onDraftChange"
  | "messagesDomain"
  | "selectedTemplate"
  | "chooseTemplate"
  | "templateCode"
  | "appliesFromLabel"
  | "presentationDomain"
  | "previewState"
  | "saveReviewOpen"
  | "restoreRecommended"
  | "isRequired"
  | "previewError"
  | "maxTemplateLength"
  | "preview"
  | "previewContextEntries"
  | "conflictCurrent"
  | "saveError"
  | "loadCurrentVersion"
  | "keepDraftWithCurrentRevision"
  | "saveSuccess"
  | "saving"
  | "cancelSaveReview"
  | "confirmSave"
  | "isDirty"
  | "refreshPreviewNow"
  | "requestSave"
>;
