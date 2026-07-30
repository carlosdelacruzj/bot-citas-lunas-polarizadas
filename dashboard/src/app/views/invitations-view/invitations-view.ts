import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  AppointmentApiService,
  CreatedHostedInvitation,
  HostedInvitation,
  apiErrorMessage,
} from '../../appointment-api.service';

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
  protected readonly copied = signal(false);

  ngOnInit(): void {
    void this.refresh();
  }

  protected async createInvitation(): Promise<void> {
    const name = this.displayName().trim();
    const phone = this.whatsappPhone().trim();
    if (!name || !phone) {
      this.error.set('Completa el nombre de referencia y el WhatsApp.');
      return;
    }
    this.busy.set(true);
    this.error.set('');
    this.issuedInvitation.set(null);
    try {
      this.issuedInvitation.set(await this.api.createHostedInvitation(name, phone));
      this.displayName.set('');
      this.whatsappPhone.set('');
      await this.refresh(false);
    } catch (error) {
      this.error.set(apiErrorMessage(error));
    } finally {
      this.busy.set(false);
    }
  }

  protected async revoke(invitation: HostedInvitation): Promise<void> {
    if (!invitation.invitation_id || !confirm('¿Revocar esta invitación?')) {
      return;
    }
    await this.runAction(() => this.api.revokeHostedInvitation(invitation.invitation_id!));
  }

  protected async reissue(invitation: HostedInvitation): Promise<void> {
    if (!invitation.invitation_id || !confirm('¿Revocar el enlace anterior y crear uno nuevo?')) {
      return;
    }
    await this.runAction(async () => {
      this.issuedInvitation.set(
        await this.api.reissueHostedInvitation(invitation.invitation_id!),
      );
    });
  }

  protected async copyIssuedUrl(): Promise<void> {
    const url = this.issuedInvitation()?.url;
    if (!url) {
      return;
    }
    try {
      await navigator.clipboard.writeText(url);
      this.copied.set(true);
      window.setTimeout(() => this.copied.set(false), 1800);
    } catch {
      this.error.set('No se pudo copiar. Selecciona el enlace y cópialo manualmente.');
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

  protected canReissue(invitation: HostedInvitation): boolean {
    return ['revoked', 'expired', 'credentials_invalid'].includes(invitation.status);
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

  private async runAction(action: () => Promise<unknown>): Promise<void> {
    this.busy.set(true);
    this.error.set('');
    try {
      await action();
      await this.refresh(false);
    } catch (error) {
      this.error.set(apiErrorMessage(error));
    } finally {
      this.busy.set(false);
    }
  }
}
