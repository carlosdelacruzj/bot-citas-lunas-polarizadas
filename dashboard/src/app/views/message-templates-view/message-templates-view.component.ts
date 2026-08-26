import { HttpErrorResponse } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  OnDestroy,
  ViewChild,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  AppointmentApiService,
  WhatsAppMessageTemplate,
  apiErrorMessage,
} from '../../appointment-api.service';
import { DASHBOARD_VIEW_FACADE } from '../../dashboard-view.facade';

type PreviewState = 'ready' | 'loading' | 'error';

@Component({
  selector: 'app-message-templates-view',
  imports: [FormsModule],
  templateUrl: './message-templates-view.component.html',
  styleUrl: './message-templates-view.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MessageTemplatesViewComponent implements OnDestroy {
  @ViewChild('templateEditor') private templateEditor?: ElementRef<HTMLTextAreaElement>;

  protected readonly dashboard = inject(DASHBOARD_VIEW_FACADE);
  private readonly api = inject(AppointmentApiService);
  private previewTimer: number | null = null;
  private previewGeneration = 0;
  private hydratedRevision = 0;

  protected readonly maxTemplateLength = 1500;
  protected readonly selectedTemplateKey = signal('');
  protected readonly draft = signal('');
  protected readonly preview = signal('');
  protected readonly previewContext = signal<Record<string, string>>({});
  protected readonly previewState = signal<PreviewState>('ready');
  protected readonly previewError = signal<string | null>(null);
  protected readonly saving = signal(false);
  protected readonly saveReviewOpen = signal(false);
  protected readonly saveError = signal<string | null>(null);
  protected readonly saveSuccess = signal<string | null>(null);
  protected readonly conflictCurrent = signal<WhatsAppMessageTemplate | null>(null);

  protected readonly selectedTemplate = computed<WhatsAppMessageTemplate | null>(() => {
    const key = this.selectedTemplateKey();
    return (
      this.dashboard
        .whatsappMessageTemplates()
        .find((item: WhatsAppMessageTemplate) => item.template_key === key) ?? null
    );
  });
  protected readonly isDirty = computed(
    () => this.draft() !== (this.selectedTemplate()?.message_template ?? ''),
  );
  protected readonly previewContextEntries = computed(() =>
    Object.entries(this.previewContext()),
  );

  constructor() {
    effect(() => {
      const templates = this.dashboard.whatsappMessageTemplates() as WhatsAppMessageTemplate[];
      const editingPaused = this.dashboard.formDirty();
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
    this.dashboard.formDirty.set(false);
  }

  protected chooseTemplate(templateKey: string): void {
    const template = this.dashboard
      .whatsappMessageTemplates()
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
    this.dashboard.formDirty.set(false);
    this.hydrate(template);
  }

  protected onDraftChange(value: string): void {
    this.draft.set(value);
    this.saveReviewOpen.set(false);
    this.saveError.set(null);
    this.saveSuccess.set(null);
    this.conflictCurrent.set(null);
    this.dashboard.formDirty.set(this.isDirty());
    this.schedulePreview();
  }

  protected insertVariable(variable: string): void {
    const editor = this.templateEditor?.nativeElement;
    const current = this.draft();
    if (!editor) {
      this.onDraftChange(`${current}${current.endsWith(' ') ? '' : ' '}${variable}`);
      return;
    }
    const start = editor.selectionStart ?? current.length;
    const end = editor.selectionEnd ?? start;
    const next = current.slice(0, start) + variable + current.slice(end);
    this.onDraftChange(next);
    window.setTimeout(() => {
      editor.focus();
      editor.setSelectionRange(start + variable.length, start + variable.length);
    });
  }

  protected restoreRecommended(): void {
    const template = this.selectedTemplate();
    if (!template) {
      return;
    }
    this.onDraftChange(template.recommended_template);
  }

  protected async requestSave(): Promise<void> {
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

  protected cancelSaveReview(): void {
    this.saveReviewOpen.set(false);
  }

  protected async confirmSave(): Promise<void> {
    const template = this.selectedTemplate();
    if (!template || this.saving()) {
      return;
    }
    this.saving.set(true);
    this.saveError.set(null);
    this.saveSuccess.set(null);
    try {
      const updated = await this.api.updateWhatsAppMessageTemplate(
        template.template_key,
        this.draft(),
        template.revision,
      );
      this.replaceTemplate(updated);
      this.dashboard.formDirty.set(false);
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

  protected loadCurrentVersion(): void {
    const current = this.conflictCurrent();
    if (!current) {
      return;
    }
    this.replaceTemplate(current);
    this.dashboard.formDirty.set(false);
    this.hydrate(current);
    this.saveSuccess.set(`Se cargó la revisión vigente ${current.revision}.`);
  }

  protected keepDraftWithCurrentRevision(): void {
    const current = this.conflictCurrent();
    if (!current) {
      return;
    }
    this.replaceTemplate(current);
    this.hydratedRevision = current.revision;
    this.conflictCurrent.set(null);
    this.saveError.set(null);
    this.dashboard.formDirty.set(this.draft() !== current.message_template);
    this.saveSuccess.set(
      `Tu borrador se conserva sobre la revisión ${current.revision}. Revísalo antes de guardar.`,
    );
  }

  protected appliesFromLabel(value: WhatsAppMessageTemplate['applies_from']): string {
    return {
      next_prepared_job: 'Siguiente aviso preparado',
      next_prepared_message: 'Siguiente paquete preparado',
      next_prepared_followup: 'Siguiente postpago preparado',
      next_reconciliation: 'Siguiente revisión pre-cita',
    }[value];
  }

  protected templateCode(templateKey: string): string {
    if (templateKey.startsWith('registration_')) return 'RG';
    if (templateKey === 'reservation_confirmation') return 'CITA';
    if (templateKey === 'reservation_payment') return 'S/';
    if (templateKey === 'post_payment_confirmation') return 'PDF';
    return '24H';
  }

  protected isRequired(variable: string, template: WhatsAppMessageTemplate): boolean {
    return template.required_variables.includes(variable);
  }

  protected refreshPreviewNow(): void {
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
      const response = await this.api.previewWhatsAppMessageTemplate(
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
    this.dashboard.formDirty.set(false);
  }

  private replaceTemplate(updated: WhatsAppMessageTemplate): void {
    this.dashboard.whatsappMessageTemplates.update((templates: WhatsAppMessageTemplate[]) =>
      templates.map((item) =>
        item.template_key === updated.template_key ? updated : item,
      ),
    );
  }
}
