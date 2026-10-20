import { ChangeDetectionStrategy, Component, ElementRef, inject, ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import {
  FollowupWorkspaceFacade,
  type FollowupWorkspaceFacadeView,
} from '../../domains/followups/followup-workspace.facade';
import { LoadStatusComponent } from '../../load-status/load-status.component';
import { ViewStateComponent } from '../../view-state/view-state.component';

@Component({
  providers: [FollowupWorkspaceFacade],
  selector: 'app-followups-view',
  imports: [LoadStatusComponent, FormsModule, ViewStateComponent],
  templateUrl: './followups-view.component.html',
  styleUrl: './followups-view.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FollowupsViewComponent {
  protected readonly editor: FollowupWorkspaceFacadeView = inject(FollowupWorkspaceFacade);
  @ViewChild('reminderDialog') private reminderDialog?: ElementRef<HTMLDialogElement>;

  protected openReminderEditor(): void { this.editor.prepareReminderEditor(); this.reminderDialog?.nativeElement.showModal(); }

  protected closeReminderEditor(): void { this.reminderDialog?.nativeElement.close(); }

  protected openReminderMessageEditor(): void {
    this.closeReminderEditor();
    void this.router.navigate(['/mensajes'], { queryParams: { template: 'appointment_reminder' } });
  }

  private readonly router = inject(Router);
}
