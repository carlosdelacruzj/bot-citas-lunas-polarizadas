import { ChangeDetectionStrategy, Component, ElementRef, ViewChild, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  MessageTemplateEditorFacade,
  type MessageTemplateEditorFacadeView,
} from '../../domains/messages/message-template-editor.facade';
import { LoadStatusComponent } from '../../load-status/load-status.component';

@Component({
  providers: [MessageTemplateEditorFacade],
  selector: 'app-message-templates-view',
  imports: [LoadStatusComponent, FormsModule],
  templateUrl: './message-templates-view.component.html',
  styleUrl: './message-templates-view.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MessageTemplatesViewComponent {
  protected readonly editor: MessageTemplateEditorFacadeView = inject(MessageTemplateEditorFacade);
  @ViewChild('templateEditor') private templateEditor?: ElementRef<HTMLTextAreaElement>;

  protected insertVariable(variable: string): void {
    const editor = this.templateEditor?.nativeElement;
    const current = this.editor.draft();
    if (!editor) {
      this.editor.onDraftChange(`${current}${current.endsWith(' ') ? '' : ' '}${variable}`);
      return;
    }
    const start = editor.selectionStart ?? current.length;
    const end = editor.selectionEnd ?? start;
    const next = current.slice(0, start) + variable + current.slice(end);
    this.editor.onDraftChange(next);
    window.setTimeout(() => {
      editor.focus();
      editor.setSelectionRange(start + variable.length, start + variable.length);
    });
  }
}
