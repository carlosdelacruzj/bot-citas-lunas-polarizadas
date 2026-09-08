import { Injectable, Injector, WritableSignal, effect, inject, signal } from '@angular/core';
import {
  ERROR_MESSAGE_DURATION_MS,
  ModalKind,
  PendingAction,
} from '../../dashboard-domain.contracts';
import {
  DASHBOARD_UI_FINANCE,
  DASHBOARD_UI_MESSAGES,
  DASHBOARD_UI_NAVIGATION,
  DASHBOARD_UI_ORDERS,
  DASHBOARD_UI_PRESENTATION,
} from '../../dashboard-domain.ports';

@Injectable()
export class DashboardUi {
  private readonly injector = inject(Injector);

  private sweetAlertPromise: Promise<typeof import('sweetalert2').default> | null = null;

  private errorMessageTimer: number | null = null;

  private lastFocusedElement: HTMLElement | null = null;

  public readonly activeModal = signal<ModalKind>(null);

  public readonly formDirty = signal(false);

  public readonly errorMessage = signal<string | null>(null);

  public readonly copiedLabel = signal<string | null>(null);

  public readonly actionBusy = signal(false);

  public readonly pendingAction = signal<PendingAction | null>(null);

  public handleEscape(): void {
    if (this.actionBusy()) {
      return;
    }
    if (this.pendingAction()) {
      void this.getSweetAlert().then((sweetAlert) => sweetAlert.close());
      return;
    }
    if (this.navigation.mobileMenuOpen()) {
      this.navigation.mobileMenuOpen.set(false);
      return;
    }
    if (this.activeModal()) {
      this.closeModal();
      return;
    }
    if (this.orders.orderPanelOpen()) {
      this.orders.closeOrderPanel();
    }
  }

  public closeModal(): void {
    if (this.actionBusy()) {
      return;
    }
    const modal = this.activeModal();
    this.activeModal.set(null);
    this.pendingAction.set(null);
    this.formDirty.set(false);
    this.orders.hydrateSelectedOrderForms();
    if (modal === 'create-order') {
      this.orders.clearCreateOrderForm();
    }
    if (modal === 'finance-entry') {
      this.finance.clearFinanceForm();
    }
    if (modal === 'whatsapp') {
      this.messages.clearWhatsAppForm();
    }
    this.restoreFocus();
  }

  public editField<T>(field: WritableSignal<T>, value: T): void {
    field.set(value);
    this.formDirty.set(true);
  }

  public markCopied(label: string): void {
    this.copiedLabel.set(label);
    window.setTimeout(() => {
      if (this.copiedLabel() === label) {
        this.copiedLabel.set(null);
      }
    }, 1600);
  }

  public async setPendingAction(action: PendingAction): Promise<void> {
    this.errorMessage.set(null);
    this.captureFocus();
    this.pendingAction.set(action);
    const result = await (await this.getSweetAlert()).fire({
      title: action.title,
      text: action.message,
      icon: action.title.toLowerCase().includes('cerrar') ? 'warning' : 'question',
      showCancelButton: true,
      confirmButtonText: 'Sí, continuar',
      cancelButtonText: 'Cancelar',
      reverseButtons: true,
      focusCancel: true,
      allowOutsideClick: !this.actionBusy(),
    });
    if (!result.isConfirmed) {
      this.pendingAction.set(null);
      action.onSettled?.();
      this.restoreFocus();
      return;
    }
    this.actionBusy.set(true);
    try {
      const response = await action.execute();
      this.pendingAction.set(null);
      this.formDirty.set(false);
      action.onSuccess?.(response);
      await this.navigation.refreshAll();
      await action.afterRefresh?.(response);
      const successMessage =
        typeof action.successMessage === 'function'
          ? action.successMessage(response)
          : action.successMessage;
      this.showToast(successMessage ?? `${action.title}: completado`);
    } catch (error) {
      const message = this.presentation.readError(error);
      this.errorMessage.set(message);
      await (await this.getSweetAlert()).fire({
        icon: 'error',
        title: 'No se pudo completar',
        text: message,
      });
    } finally {
      action.onSettled?.();
      this.pendingAction.set(null);
      this.actionBusy.set(false);
      this.restoreFocus();
    }
  }

  public showToast(title: string): void {
    void this.getSweetAlert()
      .then((sweetAlert) =>
        sweetAlert.fire({
          toast: true,
          position: 'top-end',
          icon: 'success',
          title,
          showConfirmButton: false,
          timer: 2200,
          timerProgressBar: true,
        }),
      )
      .catch(() => undefined);
  }

  public getSweetAlert(): Promise<typeof import('sweetalert2').default> {
    this.sweetAlertPromise ??= import('sweetalert2').then((module) => module.default);
    return this.sweetAlertPromise;
  }

  public openModal(modal: Exclude<ModalKind, null>): void {
    this.captureFocus();
    this.activeModal.set(modal);
    this.focusModal();
  }

  public captureFocus(): void {
    const activeElement = document.activeElement;
    this.lastFocusedElement = activeElement instanceof HTMLElement ? activeElement : null;
  }

  private focusModal(): void {
    window.setTimeout(() => {
      document.querySelector<HTMLElement>('[data-modal-initial-focus]')?.focus();
    });
  }

  public restoreFocus(): void {
    const target = this.lastFocusedElement;
    const activeAtClose = document.activeElement;
    this.lastFocusedElement = null;
    window.setTimeout(() => {
      if (document.activeElement !== activeAtClose && document.activeElement !== document.body) return;
      if (target?.isConnected) {
        target.focus();
        return;
      }
      document
        .querySelector<HTMLElement>(`[data-order-row="${CSS.escape(this.orders.selectedOrderId())}"]`)
        ?.focus();
    });
  }

  constructor() {
    effect(() => {
      const message = this.errorMessage();
      if (this.errorMessageTimer !== null) {
        window.clearTimeout(this.errorMessageTimer);
        this.errorMessageTimer = null;
      }
      if (message) {
        this.errorMessageTimer = window.setTimeout(() => {
          this.errorMessage.set(null);
          this.errorMessageTimer = null;
        }, ERROR_MESSAGE_DURATION_MS);
      }
    });
  }

  public disposeNotifications(): void {
    if (this.errorMessageTimer !== null) window.clearTimeout(this.errorMessageTimer);
  }

  private get navigation() { return this.injector.get(DASHBOARD_UI_NAVIGATION); }

  private get orders() { return this.injector.get(DASHBOARD_UI_ORDERS); }

  private get finance() { return this.injector.get(DASHBOARD_UI_FINANCE); }

  private get messages() { return this.injector.get(DASHBOARD_UI_MESSAGES); }

  private get presentation() { return this.injector.get(DASHBOARD_UI_PRESENTATION); }
}
