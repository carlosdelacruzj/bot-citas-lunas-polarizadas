import { Injectable, Injector, inject, signal } from '@angular/core';
import { MessagesApiClient } from '../../api/messages/messages-api.client';
import type {
  WhatsAppFollowUpPackage,
  WhatsAppMessagePackage,
  WhatsAppMessageTemplate,
  WhatsAppReviewPayload,
  WhatsAppReviewResolution,
  WhatsAppWebDraftResponse,
} from '../../api/messages/messages.contracts';
import type { ServiceOrder, ServiceOrderDetail } from '../../api/orders/orders.contracts';

import {
  DASHBOARD_MESSAGES_NAVIGATION,
  DASHBOARD_MESSAGES_ORDERS,
  DASHBOARD_MESSAGES_PRESENTATION,
  DASHBOARD_MESSAGES_UI,
} from '../../dashboard-domain.ports';
import { RequestScope } from '../../request-cancellation';

@Injectable()
export class MessagesFacade {
  private readonly injector = inject(Injector);
  private readonly messagesApi = inject(MessagesApiClient);

  public readonly whatsappMessageTemplates = signal<WhatsAppMessageTemplate[]>([]);

  public readonly whatsappPackage = signal<WhatsAppMessagePackage | null>(null);

  public readonly whatsappFollowUpPackage = signal<WhatsAppFollowUpPackage | null>(null);

  public readonly whatsappPackageLoading = signal(false);

  public readonly whatsappFollowUpLoading = signal(false);

  public readonly whatsappTestRecipient = signal('');

  public readonly whatsappTestMode = signal(false);

  public readonly whatsappFollowUpMode = signal(false);

  public readonly whatsappReviewMode = signal(false);

  public readonly whatsappReview = signal<WhatsAppReviewPayload | null>(null);

  public readonly whatsappReviewNote = signal('');

  public readonly whatsappWebBusy = signal(false);

  public readonly whatsappWebResult = signal<WhatsAppWebDraftResponse | null>(null);

  public readonly whatsappManualFallbackOpen = signal(false);

  public readonly whatsappSessionBusy = signal(false);

  public readonly whatsappSessionState = signal<
    'unknown' | 'ready' | 'login_required' | 'error'
  >('unknown');

  public openWhatsAppTest(): void {
    this.whatsappPackage.set(null);
    this.whatsappFollowUpPackage.set(null);
    this.whatsappTestRecipient.set('');
    this.whatsappTestMode.set(true);
    this.whatsappFollowUpMode.set(true);
    this.whatsappReviewMode.set(false);
    this.whatsappReview.set(null);
    this.whatsappWebResult.set(null);
    this.whatsappManualFallbackOpen.set(true);
    this.ui.openModal('whatsapp');
  }

  public openWhatsAppEvidenceTest(): void {
    this.whatsappPackage.set(null);
    this.whatsappFollowUpPackage.set(null);
    this.whatsappTestRecipient.set('');
    this.whatsappTestMode.set(true);
    this.whatsappFollowUpMode.set(false);
    this.whatsappReviewMode.set(false);
    this.whatsappReview.set(null);
    this.whatsappWebResult.set(null);
    this.whatsappManualFallbackOpen.set(true);
    this.ui.openModal('whatsapp');
  }

  public async validateWhatsAppSession(): Promise<boolean> {
    if (this.whatsappSessionBusy()) {
      return false;
    }
    this.whatsappSessionBusy.set(true);
    this.ui.errorMessage.set(null);
    try {
      for (let attempt = 0;attempt < 3;attempt += 1) {
        const response = await this.messagesApi.validateWhatsAppWebSession();
        if (response.status === 'session_ready') {
          this.whatsappSessionState.set('ready');
          this.ui.showToast('WhatsApp vinculado y listo');
          return true;
        }
        if (response.status !== 'login_required') {
          this.whatsappSessionState.set('error');
          await (await this.ui.getSweetAlert()).fire({
            icon: 'warning',
            title: 'WhatsApp no está disponible',
            text: response.message,
            confirmButtonText: 'Entendido',
          });
          return false;
        }
        this.whatsappSessionState.set('login_required');
        const scanResult = await (await this.ui.getSweetAlert()).fire({
          icon: 'info',
          title: 'Vincular WhatsApp',
          text: response.message,
          imageUrl: response.qr_image_data_url ?? undefined,
          imageAlt: 'Código QR para vincular WhatsApp Web',
          imageWidth: 280,
          imageHeight: 280,
          showCancelButton: true,
          confirmButtonText: 'Comprobar vinculación',
          cancelButtonText: 'Cancelar',
          allowOutsideClick: false,
        });
        if (!scanResult.isConfirmed) {
          return false;
        }
      }
      this.whatsappSessionState.set('error');
      await (await this.ui.getSweetAlert()).fire({
        icon: 'warning',
        title: 'Vinculación pendiente',
        text: 'WhatsApp todavía no confirmó el QR. Vuelve a validar la sesión.',
        confirmButtonText: 'Entendido',
      });
      return false;
    } catch (error) {
      this.whatsappSessionState.set('error');
      this.ui.errorMessage.set(this.presentation.readError(error));
      await (await this.ui.getSweetAlert()).fire({
        icon: 'error',
        title: 'No se pudo validar WhatsApp',
        text: this.ui.errorMessage() ?? 'Error desconocido.',
        confirmButtonText: 'Entendido',
      });
      return false;
    } finally {
      this.whatsappSessionBusy.set(false);
    }
  }

  public async prepareWhatsAppTest(): Promise<void> {
    const recipient = this.whatsappTestRecipient().trim();
    if (!recipient) {
      this.ui.errorMessage.set('Ingresa tu WhatsApp con codigo de pais, por ejemplo +51987654321.');
      return;
    }
    if (this.whatsappFollowUpMode()) {
      await this.loadWhatsAppFollowUpPackage(() =>
        this.messagesApi.prepareWhatsAppFollowUpTest(recipient),
      );
      this.whatsappManualFallbackOpen.set(false);
      this.ui.showToast('Prueba preparada: revisa el contenido antes de enviarlo');
      return;
    }
    await this.loadWhatsAppPackage(() => this.messagesApi.prepareWhatsAppTest(recipient));
    this.whatsappManualFallbackOpen.set(false);
    this.ui.showToast('Prueba preparada: revisa las imágenes y el texto antes de enviarla');
  }

  public async openOrderWhatsApp(order: ServiceOrder, allowResend = false): Promise<void> {
    this.whatsappPackage.set(null);
    this.whatsappFollowUpPackage.set(null);
    this.whatsappTestMode.set(false);
    this.whatsappFollowUpMode.set(false);
    this.whatsappReviewMode.set(false);
    this.whatsappReview.set(null);
    this.whatsappWebResult.set(null);
    this.whatsappManualFallbackOpen.set(false);
    this.ui.openModal('whatsapp');
    try {
      await this.loadWhatsAppPackage(() =>
        this.messagesApi.prepareOrderWhatsApp(order.order_id, allowResend),
      );
      this.whatsappManualFallbackOpen.set(false);
      this.ui.showToast('Paquete preparado: revisa las imágenes y el texto antes de enviarlo');
    } catch {
      if (!allowResend && order.whatsapp_message_status === 'sent') {
        const result = await (await this.ui.getSweetAlert()).fire({
          icon: 'warning',
          title: 'Mensaje ya enviado',
          text: 'Esta orden ya tiene un envio confirmado. ¿Deseas preparar un reenvio?',
          showCancelButton: true,
          confirmButtonText: 'Preparar reenvio',
          cancelButtonText: 'Cancelar',
        });
        if (result.isConfirmed) {
          await this.openOrderWhatsApp(order, true);
        }
      }
    }
  }

  public async openPostPaymentWhatsApp(order: ServiceOrder, allowResend = false): Promise<void> {
    this.whatsappPackage.set(null);
    this.whatsappFollowUpPackage.set(null);
    this.whatsappTestMode.set(false);
    this.whatsappFollowUpMode.set(true);
    this.whatsappReviewMode.set(false);
    this.whatsappReview.set(null);
    this.whatsappWebResult.set(null);
    this.whatsappManualFallbackOpen.set(true);
    this.ui.openModal('whatsapp');
    try {
      const message = await this.loadWhatsAppFollowUpPackage(() =>
        this.messagesApi.preparePostPaymentWhatsApp(order.order_id, allowResend),
      );
      await this.prepareWhatsAppFollowUpWebDraft(message);
    } catch {
      if (!allowResend && order.whatsapp_followup_status === 'sent') {
        const result = await (await this.ui.getSweetAlert()).fire({
          icon: 'warning',
          title: 'Post-pago ya enviado',
          text: 'Esta orden ya tiene un seguimiento post-pago confirmado. ¿Deseas preparar un reenvio?',
          showCancelButton: true,
          confirmButtonText: 'Preparar reenvio',
          cancelButtonText: 'Cancelar',
        });
        if (result.isConfirmed) {
          await this.openPostPaymentWhatsApp(order, true);
        }
      }
    }
  }

  public async openWhatsAppReview(order: ServiceOrder): Promise<void> {
    const isFollowUp =
      this.isPostPaymentWhatsAppCandidate(order) &&
      ['failed', 'uncertain'].includes(order.whatsapp_followup_action_state);
    this.whatsappPackage.set(null);
    this.whatsappFollowUpPackage.set(null);
    this.whatsappTestMode.set(false);
    this.whatsappFollowUpMode.set(isFollowUp);
    this.whatsappReviewMode.set(true);
    this.whatsappReview.set(null);
    this.whatsappReviewNote.set('');
    this.whatsappWebResult.set(null);
    this.whatsappManualFallbackOpen.set(true);
    this.ui.openModal('whatsapp');
    this.whatsappFollowUpLoading.set(true);
    this.ui.errorMessage.set(null);
    try {
      const review = await this.messagesApi.getWhatsAppReview(
        order.order_id,
        isFollowUp ? 'whatsapp-followup' : 'whatsapp',
      );
      this.whatsappReview.set(review);
      this.whatsappFollowUpPackage.set(review.message);
    } catch (error) {
      this.ui.errorMessage.set(this.presentation.readError(error));
    } finally {
      this.whatsappFollowUpLoading.set(false);
    }
  }

  public async resolveWhatsAppReview(resolution: WhatsAppReviewResolution): Promise<void> {
    const review = this.whatsappReview();
    if (!review || this.ui.actionBusy()) {
      return;
    }
    const note = this.whatsappReviewNote().trim();
    if (resolution === 'dismissed' && !note) {
      this.ui.errorMessage.set('Indica el motivo para cerrar el pendiente sin envío.');
      return;
    }
    const labels: Record<WhatsAppReviewResolution, { title: string; text: string }> = {
      confirmed_complete: {
        title: 'Confirmar paquete completo',
        text: 'Úsalo solo si verificaste en el chat que todo el paquete ya fue enviado.',
      },
      completed_missing: {
        title: 'Confirmar contenido completado',
        text: 'Confirma solo después de enviar manualmente únicamente lo que faltaba.',
      },
      dismissed: {
        title: 'Cerrar pendiente sin envío',
        text: 'El intento seguirá registrado como incierto o fallido y se guardará tu motivo.',
      },
    };
    const copy = labels[resolution];
    const confirmation = await (await this.ui.getSweetAlert()).fire({
      icon: resolution === 'dismissed' ? 'warning' : 'question',
      title: copy.title,
      text: copy.text,
      showCancelButton: true,
      confirmButtonText: 'Sí, registrar resolución',
      cancelButtonText: 'Cancelar',
      focusCancel: true,
    });
    if (!confirmation.isConfirmed) {
      return;
    }
    this.ui.actionBusy.set(true);
    try {
      await this.messagesApi.resolveWhatsAppReview(review.job.job_key, resolution, note || null);
      await this.navigation.refreshAll();
      this.ui.actionBusy.set(false);
      this.ui.closeModal();
      this.ui.showToast('Pendiente de WhatsApp resuelto y auditado');
    } catch (error) {
      this.ui.errorMessage.set(this.presentation.readError(error));
    } finally {
      this.ui.actionBusy.set(false);
    }
  }

  public canPrepareOrderWhatsApp(order: ServiceOrder): boolean {
    const baseEligible =
      order.status === 'reserved_payment_pending' &&
      order.reservation_status === 'confirmed' &&
      order.payment_status === 'pending' &&
      !!order.amount_agreed &&
      order.charge_required;
    if (!baseEligible) {
      return false;
    }
    if (order.whatsapp_message_action_state === 'resolved') {
      return false;
    }
    const detail = this.orders.selectedOrderDetail();
    if (!detail || detail.order_id !== order.order_id) {
      return false;
    }
    return this.hasWhatsAppRecipient(detail);
  }

  public whatsappPreparationHint(order: ServiceOrder): string {
    if (order.whatsapp_message_action_state === 'resolved') {
      return 'El resultado fue conciliado y cerrado por el operador.';
    }
    if (
      order.status !== 'reserved_payment_pending' ||
      order.reservation_status !== 'confirmed' ||
      order.payment_status !== 'pending' ||
      !order.amount_agreed ||
      !order.charge_required
    ) {
      return 'Requiere reserva confirmada, pago pendiente y monto acordado.';
    }
    const detail = this.orders.selectedOrderDetail();
    if (!detail || detail.order_id !== order.order_id) {
      return 'Cargando contacto protegido...';
    }
    if (!this.hasWhatsAppRecipient(detail)) {
      return 'Registra un numero internacional o un @usuario de WhatsApp valido.';
    }
    return order.whatsapp_message_status === 'sent'
      ? 'Ya fue enviado; la siguiente accion preparara un reenvio explicito.'
      : 'Listo para preparar saludo, constancia y cobro.';
  }

  public canPreparePostPaymentWhatsApp(order: ServiceOrder): boolean {
    if (!this.isPostPaymentWhatsAppCandidate(order)) {
      return false;
    }
    if (order.whatsapp_followup_action_state === 'resolved') {
      return false;
    }
    const detail = this.orders.selectedOrderDetail();
    if (!detail || detail.order_id !== order.order_id) {
      return false;
    }
    return this.hasWhatsAppRecipient(detail);
  }

  public postPaymentWhatsAppHint(order: ServiceOrder): string {
    if (!this.isPostPaymentWhatsAppCandidate(order)) {
      return 'Requiere reserva confirmada y pago ya registrado.';
    }
    if (order.whatsapp_followup_action_state === 'resolved') {
      return 'El resultado fue conciliado y cerrado por el operador.';
    }
    const detail = this.orders.selectedOrderDetail();
    if (!detail || detail.order_id !== order.order_id) {
      return 'Cargando contacto protegido...';
    }
    if (!this.hasWhatsAppRecipient(detail)) {
      return 'Registra un numero internacional o un @usuario de WhatsApp valido.';
    }
    return order.whatsapp_followup_status === 'sent'
      ? 'Ya fue enviado; la siguiente accion preparara un reenvio explicito.'
      : 'Listo para preparar indicaciones post-pago y PDFs.';
  }

  public isPostPaymentWhatsAppCandidate(order: ServiceOrder): boolean {
    return (
      order.status === 'paid' &&
      order.reservation_status === 'confirmed' &&
      order.payment_status === 'paid'
    );
  }

  private hasWhatsAppRecipient(detail: ServiceOrderDetail): boolean {
    return /^\+\d{8,15}$/.test(detail.contact_whatsapp ?? '')
      || /^@\S{1,99}$/.test(detail.contact_whatsapp_username ?? '');
  }

  public async copyWhatsAppText(text: string, label: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(text);
      this.ui.markCopied(label);
      this.ui.showToast('Texto copiado');
    } catch {
      this.ui.errorMessage.set('El navegador no permitio copiar. Selecciona el texto manualmente.');
    }
  }

  public async copyWhatsAppAttachment(): Promise<void> {
    const message = this.whatsappPackage();
    if (!message) {
      return;
    }
    try {
      const blob = await this.messagesApi.getWhatsAppAttachment(message.attachment_url);
      const png = blob.type === 'image/png' ? blob : new Blob([blob], { type: 'image/png' });
      await navigator.clipboard.write([new ClipboardItem({ 'image/png': png })]);
      this.ui.markCopied('constancia');
      this.ui.showToast('Constancia copiada. Pegala con Ctrl+V en WhatsApp.');
    } catch {
      this.ui.errorMessage.set(
        'No se pudo copiar la imagen. Usa Descargar constancia como alternativa.',
      );
    }
  }

  public async prepareWhatsAppWebDraft(
    preparedMessage?: WhatsAppMessagePackage,
    autoSend = false,
  ): Promise<void> {
    const message = preparedMessage ?? this.whatsappPackage();
    if (!message || this.whatsappWebBusy()) {
      return;
    }
    this.whatsappWebBusy.set(true);
    this.ui.errorMessage.set(null);
    try {
      let response = await this.messagesApi.prepareWhatsAppWebDraft(
        message.message_id,
        'album',
        autoSend,
      );
      if (response.status === 'login_required') {
        const sessionReady = await this.validateWhatsAppSession();
        if (sessionReady) {
          response = await this.messagesApi.prepareWhatsAppWebDraft(
            message.message_id,
            'album',
            autoSend,
          );
        }
      }
      this.whatsappWebResult.set(response);
      this.whatsappManualFallbackOpen.set(response.status === 'web_unavailable');
      if (response.status === 'login_required') {
        this.whatsappSessionState.set('login_required');
      } else if (response.status === 'draft_ready') {
        this.ui.showToast('WhatsApp preparado: revisa el álbum y pulsa Enviar');
      } else if (response.status === 'sent') {
        this.whatsappPackage.set({
          ...message,
          status: 'sent',
          sent_at: response.sent_at ?? new Date().toISOString(),
        });
        this.ui.showToast('Constancia y cobro enviados por WhatsApp');
      }
    } catch (error) {
      this.ui.errorMessage.set(this.presentation.readError(error));
      this.whatsappManualFallbackOpen.set(true);
    } finally {
      this.whatsappWebBusy.set(false);
    }
  }

  public async confirmAndSendWhatsAppEvidence(): Promise<void> {
    const message = this.whatsappPackage();
    if (!message || message.status === 'sent' || this.whatsappWebBusy()) {
      return;
    }
    const result = await (await this.ui.getSweetAlert()).fire({
      icon: 'question',
      title: message.test_mode ? 'Enviar prueba de evidencias' : 'Enviar evidencia y cobro',
      text:
        `Se enviarán la constancia, el QR de Yape y el texto combinado a ` +
        `${message.recipient_label}. WhatsApp realizará un único intento.`,
      showCancelButton: true,
      confirmButtonText: message.test_mode ? 'Enviar prueba ahora' : 'Enviar ahora',
      cancelButtonText: 'Seguir revisando',
      reverseButtons: true,
      focusCancel: true,
    });
    if (!result.isConfirmed) {
      return;
    }
    await this.prepareWhatsAppWebDraft(message, true);
  }

  public async prepareWhatsAppFollowUpWebDraft(
    preparedMessage?: WhatsAppFollowUpPackage,
  ): Promise<WhatsAppWebDraftResponse | null> {
    const message = preparedMessage ?? this.whatsappFollowUpPackage();
    if (!message || this.whatsappWebBusy()) {
      return null;
    }
    this.whatsappWebBusy.set(true);
    this.ui.errorMessage.set(null);
    try {
      let response = await this.messagesApi.prepareWhatsAppFollowUpWebDraft(message.message_id);
      if (response.status === 'login_required') {
        const sessionReady = await this.validateWhatsAppSession();
        if (sessionReady) {
          response = await this.messagesApi.prepareWhatsAppFollowUpWebDraft(message.message_id);
        }
      }
      this.whatsappWebResult.set(response);
      this.whatsappManualFallbackOpen.set(response.status === 'web_unavailable');
      if (response.status === 'login_required') {
        this.whatsappSessionState.set('login_required');
      } else if (response.status === 'draft_ready') {
        this.ui.showToast('Post-pago preparado: revisa WhatsApp y pulsa Enviar');
      } else if (response.status === 'sent') {
        this.whatsappFollowUpPackage.set({
          ...message,
          status: 'sent',
          sent_at: response.sent_at ?? new Date().toISOString(),
        });
        this.ui.showToast('Post-pago enviado por WhatsApp');
      }
      return response;
    } catch (error) {
      this.ui.errorMessage.set(this.presentation.readError(error));
      this.whatsappManualFallbackOpen.set(true);
      return null;
    } finally {
      this.whatsappWebBusy.set(false);
    }
  }

  public async confirmAndSendWhatsAppFollowUp(): Promise<void> {
    const message = this.whatsappFollowUpPackage();
    if (!message || message.status === 'sent' || this.whatsappWebBusy()) {
      return;
    }
    const documentCount = message.steps.reduce(
      (total, step) => total + step.attachment_urls.length,
      0,
    );
    const result = await (await this.ui.getSweetAlert()).fire({
      icon: 'question',
      title: message.test_mode ? 'Enviar prueba post-pago' : 'Enviar post-pago',
      text:
        `Se enviarán ${documentCount} PDF y el texto post-pago a ` +
        `${message.recipient_label}. WhatsApp realizará un único intento.`,
      showCancelButton: true,
      confirmButtonText: message.test_mode ? 'Enviar prueba ahora' : 'Enviar ahora',
      cancelButtonText: 'Seguir revisando',
      reverseButtons: true,
      focusCancel: true,
    });
    if (!result.isConfirmed) {
      return;
    }
    await this.prepareWhatsAppFollowUpWebDraft(message);
  }

  public async confirmWhatsAppSent(): Promise<void> {
    const message = this.whatsappPackage();
    if (!message || message.status === 'sent') {
      return;
    }
    const result = await (await this.ui.getSweetAlert()).fire({
      icon: 'question',
      title: 'Confirmar envio',
      text: 'Confirma solo despues de enviar saludo, constancia y cobro en WhatsApp.',
      showCancelButton: true,
      confirmButtonText: 'Si, ya lo envie',
      cancelButtonText: 'Todavia no',
    });
    if (!result.isConfirmed) {
      return;
    }
    this.ui.actionBusy.set(true);
    try {
      const response = await this.messagesApi.markWhatsAppSent(message.message_id);
      this.whatsappPackage.set({
        ...message,
        status: 'sent',
        sent_at: response.sent_at ?? new Date().toISOString(),
      });
      await this.navigation.refreshAll();
      this.ui.showToast('Envio de WhatsApp registrado');
    } catch (error) {
      this.ui.errorMessage.set(this.presentation.readError(error));
    } finally {
      this.ui.actionBusy.set(false);
    }
  }

  public async confirmWhatsAppFollowUpSent(): Promise<void> {
    const message = this.whatsappFollowUpPackage();
    if (!message || message.status === 'sent') {
      return;
    }
    const result = await (await this.ui.getSweetAlert()).fire({
      icon: 'question',
      title: 'Confirmar seguimiento',
      text: 'Confirma solo despues de enviar el paquete post-pago en WhatsApp.',
      showCancelButton: true,
      confirmButtonText: 'Si, ya lo envie',
      cancelButtonText: 'Todavia no',
    });
    if (!result.isConfirmed) {
      return;
    }
    this.ui.actionBusy.set(true);
    try {
      const response = await this.messagesApi.markWhatsAppFollowUpSent(message.message_id);
      this.whatsappFollowUpPackage.set({
        ...message,
        status: 'sent',
        sent_at: response.sent_at ?? new Date().toISOString(),
      });
      await this.navigation.refreshAll();
      this.ui.showToast('Seguimiento post-pago registrado');
    } catch (error) {
      this.ui.errorMessage.set(this.presentation.readError(error));
    } finally {
      this.ui.actionBusy.set(false);
    }
  }

  private async loadWhatsAppPackage(
    load: () => Promise<WhatsAppMessagePackage>,
  ): Promise<WhatsAppMessagePackage> {
    this.whatsappPackageLoading.set(true);
    this.ui.errorMessage.set(null);
    try {
      const message = await load();
      this.whatsappPackage.set(message);
      return message;
    } catch (error) {
      this.ui.errorMessage.set(this.presentation.readError(error));
      throw error;
    } finally {
      this.whatsappPackageLoading.set(false);
    }
  }

  private async loadWhatsAppFollowUpPackage(
    load: () => Promise<WhatsAppFollowUpPackage>,
  ): Promise<WhatsAppFollowUpPackage> {
    this.whatsappFollowUpLoading.set(true);
    this.ui.errorMessage.set(null);
    try {
      const message = await load();
      this.whatsappFollowUpPackage.set(message);
      return message;
    } catch (error) {
      this.ui.errorMessage.set(this.presentation.readError(error));
      throw error;
    } finally {
      this.whatsappFollowUpLoading.set(false);
    }
  }

  public async loadMessagesView(scope: RequestScope): Promise<void> {
    this.whatsappMessageTemplates.set(await this.messagesApi.getWhatsAppMessageTemplates(scope));
    return;
  }

  public clearWhatsAppForm(): void {
    this.whatsappPackage.set(null);
    this.whatsappFollowUpPackage.set(null);
    this.whatsappTestRecipient.set('');
    this.whatsappTestMode.set(false);
    this.whatsappFollowUpMode.set(false);
    this.whatsappReviewMode.set(false);
    this.whatsappReview.set(null);
    this.whatsappReviewNote.set('');
    this.whatsappWebResult.set(null);
    this.whatsappManualFallbackOpen.set(false);
  }

  private get ui() { return this.injector.get(DASHBOARD_MESSAGES_UI); }

  private get presentation() { return this.injector.get(DASHBOARD_MESSAGES_PRESENTATION); }

  private get navigation() { return this.injector.get(DASHBOARD_MESSAGES_NAVIGATION); }

  private get orders() { return this.injector.get(DASHBOARD_MESSAGES_ORDERS); }
}
