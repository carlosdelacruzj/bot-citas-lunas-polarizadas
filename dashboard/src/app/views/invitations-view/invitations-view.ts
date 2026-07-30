import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  AppointmentApiService,
  CreatedHostedInvitation,
  HostedInvitation,
  apiErrorMessage,
} from '../../appointment-api.service';
import { formatPeruDateTime } from '../../peru-date-time';

interface PendingInvitationAction {
  type: 'replace' | 'revoke';
  invitation: HostedInvitation;
}

@Component({
  selector: 'app-invitations-view',
  imports: [FormsModule],
  templateUrl: './invitations-view.html',
  styleUrl: './invitations-view.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InvitationsView implements OnInit {
  private readonly api = inject(AppointmentApiService);

  protected readonly invitations = signal<HostedInvitation[]>([]);
  protected readonly displayName = signal('');
  protected readonly whatsappPhone = signal('');
  protected readonly issuedInvitation = signal<CreatedHostedInvitation | null>(null);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly error = signal('');
  protected readonly copied = signal<'link' | 'message' | null>(null);
  protected readonly duplicateMatches = signal<HostedInvitation[]>([]);
  protected readonly pendingAction = signal<PendingInvitationAction | null>(null);
  protected readonly editingContactRef = signal<string | null>(null);
  protected readonly editingName = signal('');
  protected readonly formatDateTime = formatPeruDateTime;

  ngOnInit(): void {
    void this.refresh();
  }

  protected async createInvitation(skipDuplicateWarning = false): Promise<void> {
    const name = this.displayName().trim();
    const phone = this.whatsappPhone().trim();
    if (!phone) {
      this.error.set('Escribe el WhatsApp para crear la invitación.');
      return;
    }
    if (!skipDuplicateWarning) {
      const normalizedPhone = this.normalizePhone(phone);
      const matches = this.invitations().filter(
        (invitation) => this.normalizePhone(invitation.whatsapp_phone) === normalizedPhone,
      );
      if (matches.length) {
        this.duplicateMatches.set(matches);
        return;
      }
    }
    this.busy.set(true);
    this.error.set('');
    this.issuedInvitation.set(null);
    this.duplicateMatches.set([]);
    try {
      this.issuedInvitation.set(await this.api.createHostedInvitation(name || null, phone));
      this.displayName.set('');
      this.whatsappPhone.set('');
      this.copied.set(null);
      await this.refresh(false);
    } catch (error) {
      this.error.set(apiErrorMessage(error));
    } finally {
      this.busy.set(false);
    }
  }

  protected requestRevoke(invitation: HostedInvitation): void {
    if (!invitation.invitation_id) {
      return;
    }
    this.pendingAction.set({ type: 'revoke', invitation });
  }

  protected requestReissue(invitation: HostedInvitation): void {
    if (!invitation.invitation_id) {
      return;
    }
    this.pendingAction.set({ type: 'replace', invitation });
  }

  protected async confirmPendingAction(): Promise<void> {
    const pending = this.pendingAction();
    const invitationId = pending?.invitation.invitation_id;
    if (!pending || !invitationId) {
      return;
    }
    this.pendingAction.set(null);
    if (pending.type === 'revoke') {
      await this.runAction(() => this.api.revokeHostedInvitation(invitationId));
      return;
    }
    await this.runAction(async () => {
      this.issuedInvitation.set(await this.api.reissueHostedInvitation(invitationId));
      this.copied.set(null);
    });
  }

  protected closePendingAction(): void {
    if (!this.busy()) {
      this.pendingAction.set(null);
    }
  }

  protected async copyIssuedUrl(): Promise<void> {
    const url = this.issuedInvitation()?.url;
    if (!url) {
      return;
    }
    await this.copyText(url, 'link');
  }

  protected async copyIssuedMessage(): Promise<void> {
    const invitation = this.issuedInvitation();
    if (!invitation) {
      return;
    }
    const message = [
      'Hola, te envío tu enlace privado para completar el registro:',
      invitation.url,
      '',
      `Está disponible hasta ${this.formatDateTime(invitation.expires_at, invitation.expires_at)}.`,
      'El enlace es personal. No lo compartas con otras personas.',
    ].join('\n');
    await this.copyText(message, 'message');
  }

  protected closeIssuedInvitation(): void {
    this.issuedInvitation.set(null);
    this.copied.set(null);
  }

  protected startEditingName(invitation: HostedInvitation): void {
    this.editingContactRef.set(invitation.contact_ref);
    this.editingName.set(invitation.display_name ?? '');
  }

  protected cancelEditingName(): void {
    this.editingContactRef.set(null);
    this.editingName.set('');
  }

  protected async saveName(invitation: HostedInvitation): Promise<void> {
    const name = this.editingName().trim();
    const saved = await this.runAction(() =>
      this.api.updateHostedInvitationName(invitation.contact_ref, name || null),
    );
    if (saved) {
      this.cancelEditingName();
    }
  }

  protected statusLabel(status: string): string {
    const labels: Record<string, string> = {
      issued: 'Emitida',
      opened: 'Abierta',
      submitted: 'Registro enviado',
      leased: 'Validando',
      accepted: 'Aceptada',
      awaiting_restrictions: 'Faltan restricciones',
      credentials_invalid: 'Acceso incorrecto',
      retry_wait: 'Reintento pendiente',
      revoked: 'Revocada',
      expired: 'Vencida',
      cancelled: 'Cancelada',
      rejected: 'Rechazada',
      local_pending: 'Preparando',
    };
    return labels[status] ?? status.replaceAll('_', ' ');
  }

  protected canReplace(invitation: HostedInvitation): boolean {
    return ['issued', 'opened', 'revoked', 'expired', 'credentials_invalid'].includes(
      invitation.status,
    );
  }

  protected canRevoke(invitation: HostedInvitation): boolean {
    return ['issued', 'opened'].includes(invitation.status);
  }

  protected statusDetail(invitation: HostedInvitation): string {
    const details: Record<string, string> = {
      issued: 'Todavía no se ha abierto.',
      opened: 'El cliente abrió el enlace.',
      submitted: 'El cliente envió el registro.',
      leased: 'La PC local está validando el registro.',
      accepted: 'Validación aceptada.',
      awaiting_restrictions: 'Debes coordinar las fechas por WhatsApp.',
      credentials_invalid: 'Necesita un enlace nuevo para corregir el acceso.',
      retry_wait: 'El sistema intentará validar nuevamente.',
      revoked: 'El enlace anterior ya no funciona.',
      expired: 'Terminó su vigencia de 24 horas.',
      cancelled: 'La solicitud fue cancelada.',
      rejected: 'La solicitud no fue aceptada.',
      local_pending: 'Preparando la referencia local.',
    };
    return details[invitation.status] ?? 'Consulta el detalle antes de continuar.';
  }

  protected invitationName(invitation: HostedInvitation): string {
    return invitation.display_name || 'Sin nombre todavía';
  }

  protected async refresh(showLoading = true): Promise<void> {
    if (showLoading) {
      this.loading.set(true);
    }
    this.error.set('');
    try {
      this.invitations.set(await this.api.getHostedInvitations());
    } catch (error) {
      this.error.set(apiErrorMessage(error));
    } finally {
      this.loading.set(false);
    }
  }

  private async runAction(action: () => Promise<unknown>): Promise<boolean> {
    this.busy.set(true);
    this.error.set('');
    try {
      await action();
      await this.refresh(false);
      return true;
    } catch (error) {
      this.error.set(apiErrorMessage(error));
      return false;
    } finally {
      this.busy.set(false);
    }
  }

  private async copyText(value: string, copied: 'link' | 'message'): Promise<void> {
    try {
      await navigator.clipboard.writeText(value);
      this.copied.set(copied);
      window.setTimeout(() => {
        if (this.copied() === copied) {
          this.copied.set(null);
        }
      }, 1800);
    } catch {
      this.error.set('No se pudo copiar automáticamente. Selecciona el enlace y cópialo.');
    }
  }

  private normalizePhone(value: string): string {
    const digits = value.replaceAll(/\D/gu, '');
    return digits.startsWith('51') && digits.length === 11 ? digits.slice(2) : digits;
  }
}
