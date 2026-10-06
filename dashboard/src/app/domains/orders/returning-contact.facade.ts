import { Injectable, computed, inject, signal } from '@angular/core';
import { OrdersApiClient } from '../../api/orders/orders-api.client';
import type { ServiceOrderDetail } from '../../api/orders/orders.contracts';
import { RequestScope } from '../../request-cancellation';

function phoneKey(value: string): string {
  if (!/^[+\d ()-]*$/.test(value)) return '';
  const digits = value.replace(/\D/g, '');
  if (value.trim().startsWith('+') && digits.length >= 8 && digits.length <= 15) return `+${digits}`;
  if (digits.length === 9 && digits.startsWith('9')) return `+51${digits}`;
  return digits.length >= 10 && digits.length <= 15 ? `+${digits}` : '';
}

@Injectable({ providedIn: 'root' })
export class ReturningContactFacade {
  private readonly api = inject(OrdersApiClient);
  private generation = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private credentialScope: RequestScope | null = null;
  public readonly matches = signal<ServiceOrderDetail[]>([]);
  public readonly loading = signal(false);
  public readonly message = signal('');
  public readonly selectedContact = signal<ServiceOrderDetail | null>(null);
  public readonly selectedAccount = signal<ServiceOrderDetail | null>(null);
  public readonly accountLoading = signal(false);
  public readonly accounts = computed(() => {
    const contact = this.selectedContact();
    if (!contact) return [];
    const unique = new Map<string, ServiceOrderDetail>();
    for (const order of this.matches()) {
      const key = `${order.document_type}:${order.document_number}`;
      if (!unique.has(key)) unique.set(key, order);
    }
    return [...unique.values()];
  });

  public clear(): void {
    this.generation++;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.credentialScope?.cancel();
    this.credentialScope = null;
    this.matches.set([]);
    this.selectedContact.set(null);
    this.selectedAccount.set(null);
    this.loading.set(false);
    this.accountLoading.set(false);
    this.message.set('');
  }

  public search(phone: string, username: string): void {
    this.clear();
    const key = phone.trim() ? phoneKey(phone) : username.trim().toLowerCase();
    if (!key || (!phone.trim() && !/^@\S{1,99}$/.test(key))) return;
    const generation = this.generation;
    this.loading.set(true);
    this.timer = setTimeout(async () => {
      try {
        const orders = await this.api.searchContacts(key);
        if (generation !== this.generation) return;
        const matches = orders.filter(order => phone.trim()
          ? phoneKey(order.contact_whatsapp ?? '') === key
          : (order.contact_whatsapp_username ?? '').trim().toLowerCase() === key);
        matches.sort((a, b) => b.created_at.localeCompare(a.created_at));
        this.matches.set(matches);
        this.message.set(matches.length ? '' : 'Sin coincidencias. Continúa con el registro normal.');
      } catch {
        if (generation === this.generation) this.message.set('No se pudo consultar el historial. Puedes completar los datos manualmente.');
      } finally {
        if (generation === this.generation) this.loading.set(false);
      }
    }, 400);
  }

  public cancelAccount(): void {
    this.credentialScope?.cancel();
    this.credentialScope = null;
    this.accountLoading.set(false);
    this.selectedAccount.set(null);
  }

  public async credentials(order: ServiceOrderDetail) {
    this.credentialScope?.cancel();
    const scope = new RequestScope();
    this.credentialScope = scope;
    const generation = this.generation;
    this.accountLoading.set(true);
    try {
      const credentials = await this.api.getSavedCredentials(order.order_id, scope);
      if (generation !== this.generation || scope.isCancelled || this.credentialScope !== scope) return null;
      this.selectedAccount.set(order);
      return credentials;
    } catch {
      if (generation === this.generation && !scope.isCancelled) this.message.set('No se pudo recuperar la cuenta. Ingresa el usuario y la contraseña actuales.');
      return null;
    } finally {
      if (this.credentialScope === scope) { this.accountLoading.set(false); this.credentialScope = null; }
      scope.cancel();
    }
  }
}
