import { Injectable, Injector, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import {
  AppointmentApiService,
  CloseServiceOrderPayload,
  ContactUpdatePayload,
  ExcludedDateRange,
  ManualSession,
  ManualSessionMode,
  PriorityUpdatePayload,
  ReservationRestrictionsUpdatePayload,
  ServiceOrder,
  ServiceOrderDetail,
  ServicePackageCatalog,
  ServicePackageDefinition,
  ServicePackageKey,
} from '../../appointment-api.service';
import {
  ClosureReason,
  OrderNextAction,
  SPANISH_LIST_FORMAT,
  WEEKDAY_NAMES,
} from '../../dashboard-domain.contracts';
import {
  DASHBOARD_ORDERS_FINANCE,
  DASHBOARD_ORDERS_MESSAGES,
  DASHBOARD_ORDERS_NAVIGATION,
  DASHBOARD_ORDERS_PRESENTATION,
  DASHBOARD_ORDERS_UI,
} from '../../dashboard-domain.ports';
import { OrdersListFacade } from '../../domains/orders/orders-list.facade';
import {
  ProgramResolutionPayload,
  ProgramResolutionResponse,
} from '../../program-resolution/program-resolution';
import { RequestScope } from '../../request-cancellation';
import { formatReservationDateRules } from '../../reservation-rule-labels';
import { buildCreateOrderPayload } from '../../sensitive-form-payloads';

@Injectable()
export class OrdersFacade {
  private readonly injector = inject(Injector);
  private readonly api = inject(AppointmentApiService);
  private readonly router = inject(Router);
  public readonly orderList = inject(OrdersListFacade);
  private readonly activeManualSessionIds = new Set<string>();

  public readonly manualSessions = signal<ManualSession[]>([]);

  public readonly closingManualSessionIds = signal<ReadonlySet<string>>(new Set());

  public readonly selectedOrderId = signal('');

  public readonly orderPanelOpen = signal(false);

  public readonly selectedOrderDetail = signal<ServiceOrderDetail | null>(null);

  public readonly orderDetailLoading = signal(false);

  public readonly contactName = signal('');

  public readonly contactWhatsapp = signal('');

  public readonly contactWhatsappUsername = signal('');

  public readonly contactSource = signal('whatsapp');

  public readonly orderDocumentNumber = signal('');

  public readonly orderDocumentType = signal<'dni' | 'foreign_resident_card'>('dni');

  public readonly orderPassword = signal('');

  public readonly orderPasswordVisible = signal(false);

  public readonly orderPriority = signal(0);

  public readonly orderMinimumReservationDate = signal('');

  public readonly orderMaximumReservationDate = signal('');

  public readonly orderAllowedWeekdays = signal<number[]>([]);

  public readonly orderExcludedDateRanges = signal<ExcludedDateRange[]>([]);

  public readonly orderExcludedDateStart = signal('');

  public readonly orderExcludedDateEnd = signal('');

  public readonly editOrderSection = signal<
    'all' | 'contact' | 'credentials' | 'restrictions' | 'program-resolution'
  >('all');

  public readonly newDocumentNumber = signal('');

  public readonly newDocumentType = signal<'dni' | 'foreign_resident_card'>('dni');

  public readonly newPassword = signal('');

  public readonly newContactName = signal('');

  public readonly newContactWhatsapp = signal('');

  public readonly newContactWhatsappUsername = signal('');

  public readonly newContactSource = signal('');

  public readonly servicePackageCatalog = signal<ServicePackageCatalog | null>(null);

  public readonly newServicePackage = signal<ServicePackageKey>('standard');

  public readonly newCustomReservationPrice = signal('');

  public readonly newMinimumReservationDate = signal('');

  public readonly newMaximumReservationDate = signal('');

  public readonly newAllowedWeekdays = signal<number[]>([]);

  public readonly newExcludedDateRanges = signal<ExcludedDateRange[]>([]);

  public readonly newExcludedDateStart = signal('');

  public readonly newExcludedDateEnd = signal('');

  public readonly closureReason = signal<ClosureReason>('client_withdrew');

  public readonly closureNote = signal('');

  public readonly selectedOrder = computed(() => {
    const selected = this.selectedOrderId();
    return this.orderList.orders().find((order) => order.order_id === selected) ?? this.orderList.orders()[0] ?? null;
  });

  public readonly modalOrder = computed(() => this.selectedOrder());

  public readonly selectedOrderChildren = computed(() => {
    const orderId = this.selectedOrder()?.order_id;
    return orderId ? this.orderList.orders().filter((order) => order.parent_order_id === orderId) : [];
  });

  public readonly orderNextAction = computed<OrderNextAction>(() => {
    const order = this.selectedOrder();
    if (!order) {
      return {
        key: 'none',
        label: 'Selecciona una orden',
        description: 'Elige una fila para ver el siguiente paso operativo.',
        disabled: true,
      };
    }
    if (
      this.messages.isPostPaymentWhatsAppCandidate(order) &&
      order.whatsapp_followup_action_state !== 'not_applicable'
    ) {
      if (['queued', 'blocked', 'running'].includes(order.whatsapp_followup_action_state)) {
        return {
          key: 'none',
          label: 'Seguimiento automático en proceso',
          description: 'No requiere intervención mientras el envío automático siga activo.',
          disabled: true,
        };
      }
      if (['failed', 'uncertain'].includes(order.whatsapp_followup_action_state)) {
        return {
          key: 'review',
          label: 'Revisar seguimiento',
          description:
            order.whatsapp_followup_action_state === 'uncertain'
              ? 'El resultado es ambiguo; comprueba WhatsApp antes de decidir.'
              : 'El envío falló; revisa la evidencia antes de repetirlo.',
          disabled: false,
        };
      }
      if (order.whatsapp_followup_action_state === 'resolved') {
        return {
          key: 'none',
          label: 'Post-pago conciliado',
          description: 'El operador cerró este resultado y ya no requiere atención.',
          disabled: true,
        };
      }
      return {
        key: 'post-payment-whatsapp',
        label:
          order.whatsapp_followup_status === 'sent' ? 'Reenviar post-pago' : 'Enviar post-pago',
        description:
          order.whatsapp_followup_status === 'sent'
            ? 'El paquete post-pago ya figura enviado; usa esto solo para un reenvio.'
            : 'La reserva esta pagada; envia indicaciones y PDFs al cliente.',
        disabled: this.ui.actionBusy(),
      };
    }
    if (this.isClosedOrder(order)) {
      return {
        key: 'none',
        label: 'Sin acciones pendientes',
        description: `La orden esta cerrada como ${this.closureDisplay(order)}.`,
        disabled: true,
      };
    }
    if (this.needsProgramResolution(order)) {
      return {
        key: 'program-resolution',
        label: 'Resolver trámites pendientes',
        description:
          'El portal devolvió varios expedientes pendientes. Elige explícitamente el alcance acordado.',
        disabled: this.ui.actionBusy(),
      };
    }
    if (order.payment_status === 'pending') {
      return {
        key: 'payment',
        label: 'Registrar pago',
        description: 'La reserva esta lista y el cobro sigue pendiente.',
        disabled: false,
      };
    }
    if (order.status === 'paused') {
      const blocked = this.hasActiveChildOrders(order);
      return {
        key: 'activate',
        label: blocked ? 'Padre bloqueado por subordenes' : 'Activar orden',
        description: blocked
          ? 'Gestiona primero las subordenes activas.'
          : 'La orden esta pausada y puede volver a la cola.',
        disabled: blocked,
      };
    }
    if (order.status === 'ready') {
      return {
        key: 'manual-session',
        label: 'Abrir sesion manual',
        description: 'La orden esta lista para una revision manual independiente.',
        disabled: this.ui.actionBusy(),
      };
    }
    return {
      key: 'review',
      label: 'Revisar acciones',
      description: `Revisa las opciones compatibles con el estado ${order.status}.`,
      disabled: false,
    };
  });

  public readonly selectedOrderWhatsappPlaceholder = computed(
    () => this.selectedOrder()?.contact_whatsapp_masked ?? 'sin numero registrado',
  );

  public readonly selectedOrderWhatsapp = computed(() => {
    const order = this.selectedOrder();
    const detail = this.selectedOrderDetail();
    if (order && detail?.order_id === order.order_id) {
      return detail.contact_whatsapp ?? detail.contact_whatsapp_username ?? 'sin WhatsApp';
    }
    return order?.contact_whatsapp_masked ?? order?.contact_whatsapp_username_masked ?? 'sin WhatsApp';
  });

  public handleBeforeUnload(): void {
    this.closeTrackedManualSessionsWithBeacon();
  }

  public applyOrders(orders: ServiceOrder[]): void {
    this.orderList.replaceOrders(orders);
    this.keepValidSelection(orders);
    this.hydrateSelectedOrderForms();
    if (this.orderPanelOpen() && this.selectedOrderId() && !this.selectedOrderDetail()) {
      void this.loadSelectedOrderDetail(this.selectedOrderId());
    }
  }

  public serviceTypeLabel(order: ServiceOrder): string {
    return this.servicePackageDefinition(order.service_package)?.label
      ?? order.service_package;
  }

  public servicePriceLabel(order: ServiceOrder): string {
    const amount = Number(order.reservation_price);
    return Number.isFinite(amount) ? `S/${amount.toFixed(2)}` : `S/${order.reservation_price}`;
  }

  public restrictionDaysLabel(order: ServiceOrder): string {
    const days = Array.from(
      new Set((order.allowed_weekdays ?? []).filter((day) => day >= 1 && day <= 7)),
    ).sort((left, right) => left - right);
    if (!days.length) {
      return 'Cualquier día';
    }
    if (days.length === 7) {
      return 'Todos los días';
    }
    const isContinuous = days.every((day, index) => index === 0 || day === days[index - 1] + 1);
    if (isContinuous && days.length >= 3) {
      return this.presentation.capitalize(`${WEEKDAY_NAMES[days[0] - 1]} a ${WEEKDAY_NAMES[days.at(-1)! - 1]}`);
    }
    return this.presentation.capitalize(SPANISH_LIST_FORMAT.format(days.map((day) => WEEKDAY_NAMES[day - 1])));
  }

  public restrictionTimingLabel(order: ServiceOrder): string {
    return formatReservationDateRules(order);
  }

  public selectOrder(orderId: string, loadDetail = true, updateRoute = true): void {
    if (!this.orderPanelOpen()) {
      this.ui.captureFocus();
    }
    this.selectedOrderId.set(orderId);
    this.orderPanelOpen.set(true);
    this.selectedOrderDetail.set(null);
    this.ui.formDirty.set(false);
    this.hydrateSelectedOrderForms();
    if (updateRoute && this.navigation.activeView() === 'orders') {
      void this.router.navigate(['/ordenes', orderId]);
    }
    if (loadDetail) {
      void this.loadSelectedOrderDetail(orderId);
    }
    window.setTimeout(() => {
      document.querySelector<HTMLElement>('[data-order-panel]')?.focus();
    });
  }

  public closeOrderPanel(updateRoute = true): void {
    if (this.ui.activeModal() || this.ui.actionBusy()) {
      return;
    }
    this.orderPanelOpen.set(false);
    this.selectedOrderDetail.set(null);
    this.ui.formDirty.set(false);
    if (updateRoute && this.navigation.activeView() === 'orders') {
      void this.router.navigateByUrl('/ordenes');
    }
    this.ui.restoreFocus();
  }

  public async openEditOrder(
    order: ServiceOrder,
    section: 'all' | 'contact' | 'credentials' | 'restrictions' | 'program-resolution' = 'all',
  ): Promise<void> {
    this.selectOrder(order.order_id, false);
    this.editOrderSection.set(section);
    this.ui.openModal('edit-order');
    await this.loadSelectedOrderDetail(order.order_id);
  }

  public async openProgramResolution(order: ServiceOrder): Promise<void> {
    this.selectOrder(order.order_id, false);
    this.editOrderSection.set('program-resolution');
    this.ui.openModal('edit-order');
    await this.loadSelectedOrderDetail(order.order_id);
  }

  public openOrderActions(order: ServiceOrder): void {
    this.selectOrder(order.order_id);
    this.ui.openModal('order-actions');
  }

  public openCreateOrder(): void {
    this.ui.openModal('create-order');
  }

  public runNextOrderAction(): void {
    const order = this.selectedOrder();
    const action = this.orderNextAction();
    if (!order || action.disabled) {
      return;
    }
    if (action.key === 'manual-session') {
      void this.openManualSessionNow(order);
    } else if (action.key === 'activate') {
      this.requestOrderAction('activate', 'Activar orden');
    } else if (action.key === 'payment') {
      void this.finance.openPayment(order);
    } else if (action.key === 'post-payment-whatsapp') {
      void this.messages.openPostPaymentWhatsApp(order);
    } else if (action.key === 'program-resolution') {
      void this.openProgramResolution(order);
    } else if (action.key === 'review') {
      void this.messages.openWhatsAppReview(order);
    }
  }

  public rowPrimaryActionLabel(order: ServiceOrder): string {
    if (this.needsProgramResolution(order)) {
      return 'Resolver trámites';
    }
    if (order.payment_status === 'pending') {
      return 'Registrar pago';
    }
    if (
      this.messages.isPostPaymentWhatsAppCandidate(order) &&
      order.whatsapp_followup_action_state !== 'not_applicable'
    ) {
      if (['failed', 'uncertain'].includes(order.whatsapp_followup_action_state)) {
        return 'Revisar post-pago';
      }
      if (['queued', 'blocked', 'running'].includes(order.whatsapp_followup_action_state)) {
        return 'Ver seguimiento';
      }
      if (order.whatsapp_followup_action_state === 'resolved') {
        return 'Post-pago conciliado';
      }
      return order.whatsapp_followup_status === 'sent' ? 'Reenviar post-pago' : 'Enviar post-pago';
    }
    if (order.status === 'paused') {
      return 'Activar';
    }
    if (order.status === 'ready') {
      return 'Abrir sesión';
    }
    return 'Ver detalle';
  }

  public runRowPrimaryAction(order: ServiceOrder): void {
    if (this.needsProgramResolution(order)) {
      void this.openProgramResolution(order);
      return;
    }
    if (order.payment_status === 'pending') {
      void this.finance.openPayment(order);
      return;
    }
    if (
      this.messages.isPostPaymentWhatsAppCandidate(order) &&
      order.whatsapp_followup_action_state !== 'not_applicable'
    ) {
      this.selectOrder(order.order_id);
      if (['failed', 'uncertain'].includes(order.whatsapp_followup_action_state)) {
        void this.messages.openWhatsAppReview(order);
      } else if (order.whatsapp_followup_action_state === 'sent') {
        void this.messages.openPostPaymentWhatsApp(order);
      }
      return;
    }
    if (order.status === 'paused') {
      this.selectOrder(order.order_id);
      this.requestOrderAction('activate', 'Activar orden');
    } else if (order.status === 'ready') {
      void this.openManualSessionNow(order);
    } else {
      this.selectOrder(order.order_id);
    }
  }

  public setQuickPriority(priority: number): void {
    this.orderPriority.set(priority);
    this.requestPriorityUpdate();
  }

  public priorityExplanation(order: ServiceOrder): string {
    if (order.priority >= 200) {
      return 'Enfoque exclusivo: el worker revisa unicamente esta orden.';
    }
    if (order.priority >= 100) {
      return 'Enfoque prioritario: se atiende antes que la cola normal.';
    }
    return 'Cola normal: mayor numero primero; empate por orden de creacion.';
  }

  public isClosedOrder(order: ServiceOrder): boolean {
    return ['archived', 'paid'].includes(order.status) || !!order.closed_at;
  }

  public requestContactUpdate(): void {
    if (this.orderDetailLoading()) {
      this.ui.errorMessage.set('Espera a que cargue el detalle protegido de la orden.');
      return;
    }
    const order = this.requireSelectedOrder();
    if (!order) {
      return;
    }
    const payload: ContactUpdatePayload = {
      contact_name: this.presentation.optionalText(this.contactName()),
      contact_whatsapp: this.presentation.optionalText(this.contactWhatsapp()),
      contact_whatsapp_username: this.presentation.optionalText(this.contactWhatsappUsername()),
      contact_source: this.presentation.optionalText(this.contactSource()),
    };
    if (!payload.contact_name && !payload.contact_whatsapp && !payload.contact_whatsapp_username) {
      this.ui.errorMessage.set('Ingresa nombre o WhatsApp para actualizar contacto.');
      return;
    }
    this.ui.setPendingAction({
      title: 'Actualizar contacto',
      message: `Actualizar contacto de ${order.order_id}.`,
      execute: () => this.api.updateServiceOrderContact(order.order_id, payload),
      onSuccess: () => {
        this.ui.activeModal.set(null);
        this.selectedOrderDetail.set(null);
      },
    });
  }

  public needsCredentialCorrection(order: ServiceOrder): boolean {
    return order.preflight_error_type === 'invalid_credentials';
  }

  public needsProgramResolution(order: ServiceOrder): boolean {
    return order.preflight_error_type === 'multiple_pending_resolution_required';
  }

  public requestProgramResolution(
    payload: ProgramResolutionPayload,
    confirmationLabel: string,
    onSuccess: (response: ProgramResolutionResponse) => void,
  ): void {
    const order = this.requireSelectedOrder();
    if (!order) {
      return;
    }
    this.ui.setPendingAction({
      title: 'Confirmar alcance de trámites',
      message: `${confirmationLabel}. No se enviará ningún mensaje. La decisión de comunicación quedará registrada.`,
      execute: async () => {
        const response = await this.api.resolveServiceOrderPrograms(order.order_id, payload);
        onSuccess(response);
        return response;
      },
      successMessage: (response) => response.message ?? 'Resolución registrada sin envío',
    });
  }

  public toggleOrderPasswordVisibility(): void {
    this.orderPasswordVisible.update((visible) => !visible);
  }

  public requestCredentialsUpdate(): void {
    if (this.orderDetailLoading()) {
      this.ui.errorMessage.set('Espera a que cargue el detalle protegido de la orden.');
      return;
    }
    const order = this.requireSelectedOrder();
    const detail = this.selectedOrderDetail();
    if (!order || !detail) {
      this.ui.errorMessage.set('No se pudo cargar el acceso actual de la orden.');
      return;
    }
    const documentNumber = this.orderDocumentNumber().trim();
    const password = this.orderPassword();
    if (!documentNumber || !password) {
      this.ui.errorMessage.set('Usuario o documento y nueva contraseña son obligatorios.');
      return;
    }
    const documentChanged = documentNumber !== detail.document_number;
    const message = documentChanged
      ? 'Cambiarás el usuario o documento de acceso. La cuenta y sus subórdenes se pausarán hasta validar la nueva identidad en el portal.'
      : 'Reemplazarás la contraseña. La cuenta y sus subórdenes se pausarán hasta validar nuevamente el acceso al portal.';
    this.ui.setPendingAction({
      title: documentChanged ? 'Cambiar usuario y contraseña' : 'Cambiar contraseña',
      message,
      execute: () =>
        this.api.updateServiceOrderCredentials(order.order_id, {
          document_number: documentNumber,
          document_type: this.orderDocumentType(),
          password,
        }),
      onSuccess: () => {
        this.orderPassword.set('');
        this.orderPasswordVisible.set(false);
        this.ui.activeModal.set(null);
        this.selectedOrderDetail.set(null);
      },
      onSettled: () => {
        this.orderPassword.set('');
        this.orderPasswordVisible.set(false);
      },
    });
  }

  public requestPriorityUpdate(): void {
    const order = this.requireSelectedOrder();
    if (!order) {
      return;
    }
    const priority = Number(this.orderPriority());
    if (!Number.isInteger(priority) || priority < 0) {
      this.ui.errorMessage.set('La prioridad debe ser un numero entero igual o mayor que 0.');
      return;
    }
    const payload: PriorityUpdatePayload = { priority };
    const entersExclusiveMode = order.priority < 200 && priority >= 200;
    const leavesExclusiveMode = order.priority >= 200 && priority < 200;
    const entersFocusedMode = order.priority < 100 && priority >= 100;
    const leavesFocusedMode = order.priority >= 100 && priority < 100;
    const effect = entersExclusiveMode
      ? ' Activara el enfoque exclusivo, limpiara su pausa y cualquier exclusivo anterior volvera a prioridad 100.'
      : leavesExclusiveMode
        ? priority >= 100
          ? ' Saldra del modo exclusivo y conservara el enfoque prioritario.'
          : ' Saldra del modo exclusivo y volvera a la cola normal.'
        : entersFocusedMode
          ? ' Activara enfoque y desplazara una orden de la cola normal.'
          : leavesFocusedMode
            ? ' La orden volvera a la cola normal.'
            : ' Se aplicara en la siguiente seleccion de la cola.';
    this.ui.setPendingAction({
      title: 'Actualizar prioridad',
      message: `Cambiar prioridad de ${order.order_id} de ${order.priority} a ${priority}.${effect}`,
      execute: () => this.api.updateServiceOrderPriority(order.order_id, payload),
      onSettled: () => this.orderPriority.set(this.selectedOrder()?.priority ?? priority),
    });
  }

  public requestReservationRestrictionsUpdate(): void {
    const order = this.requireSelectedOrder();
    if (!order) {
      return;
    }
    const excludedDateRanges = this.prepareExcludedDateRanges(
      this.orderExcludedDateRanges(),
      this.orderExcludedDateStart(),
      this.orderExcludedDateEnd(),
    );
    if (excludedDateRanges === null) {
      return;
    }
    const payload: ReservationRestrictionsUpdatePayload = {
      minimum_reservation_date: this.presentation.optionalText(this.orderMinimumReservationDate()),
      maximum_reservation_date: this.presentation.optionalText(this.orderMaximumReservationDate()),
      allowed_weekdays: this.orderAllowedWeekdays().length > 0 ? this.orderAllowedWeekdays() : null,
      excluded_date_ranges: excludedDateRanges,
    };
    if (
      payload.minimum_reservation_date &&
      payload.maximum_reservation_date &&
      payload.maximum_reservation_date < payload.minimum_reservation_date
    ) {
      this.ui.errorMessage.set('La fecha final no puede ser anterior a la fecha inicial.');
      return;
    }
    this.ui.setPendingAction({
      title: 'Actualizar reglas de reserva',
      message: `Guardar las reglas de reserva de ${order.order_id}. Los campos vacíos quitarán esa regla.`,
      execute: () => this.api.updateServiceOrderRestrictions(order.order_id, payload),
    });
  }

  public addOrderExcludedDateRange(): void {
    const ranges = this.prepareExcludedDateRanges(
      this.orderExcludedDateRanges(),
      this.orderExcludedDateStart(),
      this.orderExcludedDateEnd(),
    );
    if (ranges === null) {
      return;
    }
    this.orderExcludedDateRanges.set(ranges);
    this.orderExcludedDateStart.set('');
    this.orderExcludedDateEnd.set('');
    this.ui.formDirty.set(true);
  }

  public removeOrderExcludedDateRange(index: number): void {
    this.orderExcludedDateRanges.update((ranges) =>
      ranges.filter((_, rangeIndex) => rangeIndex !== index),
    );
    this.ui.formDirty.set(true);
  }

  public clearOrderExcludedDateRanges(): void {
    this.orderExcludedDateRanges.set([]);
    this.ui.formDirty.set(true);
  }

  public addNewExcludedDateRange(): void {
    const ranges = this.prepareExcludedDateRanges(
      this.newExcludedDateRanges(),
      this.newExcludedDateStart(),
      this.newExcludedDateEnd(),
    );
    if (ranges === null) {
      return;
    }
    this.newExcludedDateRanges.set(ranges);
    this.newExcludedDateStart.set('');
    this.newExcludedDateEnd.set('');
    this.ui.formDirty.set(true);
  }

  public removeNewExcludedDateRange(index: number): void {
    this.newExcludedDateRanges.update((ranges) =>
      ranges.filter((_, rangeIndex) => rangeIndex !== index),
    );
    this.ui.formDirty.set(true);
  }

  public clearNewExcludedDateRanges(): void {
    this.newExcludedDateRanges.set([]);
    this.ui.formDirty.set(true);
  }

  public requestOrderAction(
    action: 'pause' | 'activate' | 'no-charge' | 'done',
    title: string,
  ): void {
    const order = this.requireSelectedOrder();
    if (!order) {
      return;
    }
    if (action === 'activate' && this.hasActiveChildOrders(order)) {
      this.ui.errorMessage.set('No se puede activar una orden padre con subordenes activas.');
      return;
    }
    this.ui.setPendingAction({
      title,
      message: `${title} para ${order.order_id}.`,
      execute: () => this.api.runServiceOrderAction(order.order_id, action),
      onSuccess: () => this.ui.activeModal.set(null),
    });
  }

  public requestOrderValidation(order: ServiceOrder): void {
    this.ui.setPendingAction({
      title: 'Validar acceso',
      message: `Ingresar al portal y validar identidad y programas de ${order.order_id}.`,
      execute: () => this.api.revalidateServiceOrder(order.order_id),
      onSuccess: () => this.ui.activeModal.set(null),
    });
  }

  public preflightLabel(order: ServiceOrder): string {
    const labels: Record<ServiceOrder['preflight_status'], string> = {
      not_required: 'Sin validación previa',
      pending: 'Validación pendiente',
      running: 'Validando acceso',
      validated: 'Acceso validado',
      failed: 'Validación fallida',
    };
    return labels[order.preflight_status] ?? order.preflight_status;
  }

  public requestCloseOrder(): void {
    const order = this.requireSelectedOrder();
    if (!order) {
      return;
    }
    const payload: CloseServiceOrderPayload = {
      closure_reason: this.closureReason(),
      closure_note: this.presentation.optionalText(this.closureNote()),
    };
    this.ui.setPendingAction({
      title: this.closureReasonLabel(payload.closure_reason),
      message: `${this.closureReasonLabel(payload.closure_reason)} para ${order.order_id}.`,
      execute: () => this.api.closeServiceOrder(order.order_id, payload),
      onSuccess: () => this.ui.activeModal.set(null),
    });
  }

  public setClosureReason(value: string): void {
    const allowed: ClosureReason[] = [
      'completed_by_us',
      'family_no_charge',
      'client_withdrew',
      'external_slot',
      'duplicate',
      'not_serviceable',
      'uncollectible',
    ];
    const reason = allowed.includes(value as ClosureReason)
      ? (value as ClosureReason)
      : 'client_withdrew';
    this.ui.editField(this.closureReason, reason);
  }

  public async copySelectedOrderWhatsapp(): Promise<void> {
    const recipient = this.selectedOrderDetail()?.contact_whatsapp
      ?? this.selectedOrderDetail()?.contact_whatsapp_username;
    if (!recipient) {
      return;
    }
    await navigator.clipboard.writeText(recipient);
    this.ui.markCopied('whatsapp-number');
  }

  public openSelectedOrderWhatsapp(): void {
    const digits = this.selectedOrderDetail()?.contact_whatsapp?.replace(/\D/g, '');
    if (digits) {
      window.open(`https://wa.me/${digits}`, '_blank', 'noopener,noreferrer');
    }
  }

  public servicePackages(): ServicePackageDefinition[] {
    return this.servicePackageCatalog()?.service_packages ?? [];
  }

  public servicePackageDefinition(
    key: string | null | undefined,
  ): ServicePackageDefinition | null {
    return this.servicePackages().find((item) => item.key === key) ?? null;
  }

  public newServicePackageDefinition(): ServicePackageDefinition | null {
    return this.servicePackageDefinition(this.newServicePackage());
  }

  public servicePackageOptionLabel(definition: ServicePackageDefinition): string {
    if (!definition.total_amount) {
      return definition.label;
    }
    if (definition.key === 'integral') {
      return `${definition.label} — S/${definition.total_amount} `
        + `(S/${definition.initial_payment_amount} + S/${definition.balance_amount})`;
    }
    return `${definition.label} — S/${definition.total_amount}`;
  }

  public standardPackageAmount(): string | null {
    return this.servicePackageDefinition('standard')?.total_amount ?? null;
  }

  public requestCreateOrder(): void {
    const excludedDateRanges = this.prepareExcludedDateRanges(
      this.newExcludedDateRanges(),
      this.newExcludedDateStart(),
      this.newExcludedDateEnd(),
    );
    if (excludedDateRanges === null) {
      return;
    }
    const servicePackage = this.newServicePackage();
    const packageDefinition = this.servicePackageDefinition(servicePackage);
    const result = buildCreateOrderPayload({
      documentNumber: this.newDocumentNumber(),
      documentType: this.newDocumentType(),
      password: this.newPassword(),
      contactWhatsapp: this.newContactWhatsapp(),
      contactWhatsappUsername: this.newContactWhatsappUsername(),
      contactName: this.newContactName(),
      contactSource: this.newContactSource(),
      servicePackage,
      customReservationPrice: this.newCustomReservationPrice(),
      minimumReservationDate: this.newMinimumReservationDate(),
      maximumReservationDate: this.newMaximumReservationDate(),
      allowedWeekdays: this.newAllowedWeekdays(),
      excludedDateRanges,
    }, packageDefinition);
    if (!result.payload || !packageDefinition) {
      this.ui.errorMessage.set(result.error);
      return;
    }
    const payload = result.payload;
    const reservationPrice = payload.reservation_price;
    this.ui.setPendingAction({
      title: 'Crear orden nueva',
      message: `Crear orden para documento ${this.maskDocumentNumber(payload.document_number)} como ${packageDefinition.label.toLocaleLowerCase('es-PE')
        } por S/${reservationPrice}.`,
      execute: () => this.api.createServiceOrder(payload),
      onSuccess: () => {
        this.clearCreateOrderForm();
        this.ui.activeModal.set(null);
      },
      onSettled: () => this.clearCreateOrderSensitiveFields(),
    });
  }

  public requestManualSession(): void {
    const order = this.requireSelectedOrder();
    if (!order) {
      return;
    }
    const mode = this.manualSessionMode(order);
    this.ui.setPendingAction({
      title: this.manualSessionActionLabel(order),
      message:
        mode === 'appointment'
          ? `Abrir el panel de citas en un navegador independiente para ${order.order_id}.`
          : `Abrir el portal para consultar ${order.order_id}. El bot no cambiará el estado de la orden.`,
      execute: () => this.api.openManualSession(order.order_id, mode),
      onSuccess: (response) => {
        if (response.session_id) {
          this.activeManualSessionIds.add(response.session_id);
        }
        this.ui.activeModal.set(null);
      },
    });
  }

  public requestDiagnosticSession(): void {
    const order = this.requireSelectedOrder();
    if (!order) {
      return;
    }
    this.ui.setPendingAction({
      title: 'Medir flujo manual',
      message:
        `Abrir el portal desde el inicio para ${order.order_id}. ` +
        'Se registraran campos y solicitudes de forma sanitizada; tu controlas el envio final.',
      execute: () => this.api.openManualSession(order.order_id, 'diagnostic'),
      onSuccess: (response) => {
        if (response.session_id) {
          this.activeManualSessionIds.add(response.session_id);
        }
        this.ui.activeModal.set(null);
      },
    });
  }

  public async openManualSessionNow(
    order: ServiceOrder,
    mode: ManualSessionMode = this.manualSessionMode(order),
  ): Promise<void> {
    if (this.ui.actionBusy()) {
      return;
    }
    this.ui.actionBusy.set(true);
    this.ui.errorMessage.set(null);
    try {
      const response = await this.api.openManualSession(order.order_id, mode);
      if (response.session_id) {
        this.activeManualSessionIds.add(response.session_id);
      }
      await this.navigation.refreshAll();
      this.ui.showToast(
        mode === 'diagnostic'
          ? 'Medición activa'
          : mode === 'appointment'
            ? 'Sesión manual abierta'
            : 'Portal abierto para consulta',
      );
    } catch (error) {
      this.ui.errorMessage.set(this.presentation.readError(error));
    } finally {
      this.ui.actionBusy.set(false);
    }
  }

  public async closeManualSession(session: ManualSession): Promise<void> {
    if (this.isManualSessionClosing(session.session_id) || session.close_requested) {
      return;
    }
    this.closingManualSessionIds.update((sessionIds) => {
      const next = new Set(sessionIds);
      next.add(session.session_id);
      return next;
    });
    this.ui.errorMessage.set(null);
    try {
      await this.api.closeManualSession(session.session_id);
      this.activeManualSessionIds.delete(session.session_id);
      this.manualSessions.update((sessions) =>
        sessions.map((item) =>
          item.session_id === session.session_id
            ? {
              ...item,
              status: 'closing',
              close_requested: true,
              status_message: 'Cierre solicitado; esperando que Chromium termine.',
            }
            : item,
        ),
      );
      this.ui.showToast('Cierre solicitado');
    } catch (error) {
      this.ui.errorMessage.set(this.presentation.readError(error));
    } finally {
      this.closingManualSessionIds.update((sessionIds) => {
        const next = new Set(sessionIds);
        next.delete(session.session_id);
        return next;
      });
    }
  }

  public isManualSessionClosing(sessionId: string): boolean {
    return this.closingManualSessionIds().has(sessionId);
  }

  public orderLabel(order: ServiceOrder | null): string {
    if (!order) {
      return 'Sin orden seleccionada';
    }
    return `${order.order_id} | ${order.applicant_name ?? order.document_number_masked}`;
  }

  public closureReasonLabel(reason: string | null | undefined): string {
    const labels: Record<ClosureReason, string> = {
      completed_by_us: 'Realizado por nosotros',
      family_no_charge: 'Familiar sin cobro',
      client_withdrew: 'Cliente retirado',
      external_slot: 'Cupo por tercero',
      duplicate: 'Duplicado',
      not_serviceable: 'No gestionable',
      uncollectible: 'Incobrable',
    };
    if (!reason) {
      return 'sin cierre';
    }
    return labels[reason as ClosureReason] ?? reason.replaceAll('_', ' ');
  }

  public closureDisplay(order: ServiceOrder): string {
    if (order.closure_reason) {
      return this.closureReasonLabel(order.closure_reason);
    }
    if (order.status === 'archived') {
      return 'Archivado sin razon';
    }
    if (order.status === 'paid') {
      return 'Realizado por nosotros';
    }
    return 'abierto';
  }

  public manualSessionOrderLabel(session: ManualSession): string {
    const order = this.orderList.orders().find((item) => item.order_id === session.order_id);
    if (!order) {
      return session.order_id;
    }
    return `${session.order_id} | ${order.applicant_name ?? order.document_number_masked}`;
  }

  public manualSessionMode(order: ServiceOrder): ManualSessionMode {
    return order.status === 'ready' ? 'appointment' : 'portal';
  }

  public manualSessionActionLabel(order: ServiceOrder): string {
    return this.manualSessionMode(order) === 'appointment' ? 'Sesión manual' : 'Abrir portal';
  }

  public manualSessionTypeLabel(session: ManualSession): string {
    if (session.mode === 'diagnostic') {
      return 'Diagnóstico protegido';
    }
    return session.mode === 'appointment' ? 'Operativa' : 'Consulta';
  }

  public hasActiveChildOrders(order: ServiceOrder): boolean {
    return this.orderList.orders().some(
      (item) =>
        item.parent_order_id === order.order_id &&
        ['ready', 'paused', 'reserved_payment_pending'].includes(item.status),
    );
  }

  public programChildCount(order: ServiceOrder): number {
    return this.orderList.orders().filter((item) => item.parent_order_id === order.order_id).length;
  }

  public orderStatusDisplay(order: ServiceOrder): string {
    const childCount = this.programChildCount(order);
    if (childCount) {
      return `Contenedor · ${childCount} trámite${childCount === 1 ? '' : 's'}`;
    }
    return this.presentation.statusLabel(order.status);
  }

  public requireSelectedOrder(): ServiceOrder | null {
    const order = this.selectedOrder();
    if (!order) {
      this.ui.errorMessage.set('Carga y selecciona una orden primero.');
      return null;
    }
    return order;
  }

  public async loadSelectedOrderDetail(orderId: string): Promise<void> {
    this.orderDetailLoading.set(true);
    this.ui.errorMessage.set(null);
    try {
      const detail = await this.api.getServiceOrder(orderId);
      if (this.selectedOrderId() !== detail.order_id) {
        return;
      }
      this.selectedOrderDetail.set(detail);
      this.hydrateSelectedOrderForms(detail);
    } catch (error) {
      this.ui.errorMessage.set(this.presentation.readError(error));
    } finally {
      if (this.selectedOrderId() === orderId) {
        this.orderDetailLoading.set(false);
      }
    }
  }

  private keepValidSelection(orders: ServiceOrder[]): void {
    const selected = this.selectedOrderId();
    if (selected && orders.some((order) => order.order_id === selected)) {
      return;
    }
    this.selectedOrderId.set(orders[0]?.order_id ?? '');
  }

  public hydrateSelectedOrderForms(detail: ServiceOrderDetail | null = null): void {
    if (this.ui.formDirty()) {
      return;
    }
    const order = this.selectedOrder();
    if (!order) {
      return;
    }
    this.contactName.set(order.contact_name ?? '');
    this.contactWhatsapp.set(detail?.contact_whatsapp ?? '');
    this.contactWhatsappUsername.set(detail?.contact_whatsapp_username ?? '');
    this.contactSource.set(order.contact_source ?? 'whatsapp');
    this.orderDocumentNumber.set(detail?.document_number ?? '');
    this.orderDocumentType.set(order.document_type);
    this.orderPassword.set('');
    this.orderPasswordVisible.set(false);
    this.orderPriority.set(order.priority);
    this.orderMinimumReservationDate.set(order.minimum_reservation_date ?? '');
    this.orderMaximumReservationDate.set(order.maximum_reservation_date ?? '');
    this.orderAllowedWeekdays.set([...(order.allowed_weekdays ?? [])]);
    this.orderExcludedDateRanges.set([...(order.excluded_date_ranges ?? [])]);
    this.orderExcludedDateStart.set('');
    this.orderExcludedDateEnd.set('');
    this.finance.paymentAmountPaid.set(order.amount_paid ?? '');
    this.finance.paymentAmountAgreed.set(order.amount_agreed ?? '');
    this.closureReason.set((order.closure_reason as ClosureReason | null) ?? 'client_withdrew');
    this.closureNote.set(order.closure_note ?? '');
  }

  public clearCreateOrderForm(): void {
    this.newDocumentNumber.set('');
    this.newDocumentType.set('dni');
    this.newPassword.set('');
    this.newContactName.set('');
    this.newContactWhatsapp.set('');
    this.newContactWhatsappUsername.set('');
    this.newContactSource.set('');
    this.newServicePackage.set(this.servicePackageCatalog()?.default_package ?? 'standard');
    this.newCustomReservationPrice.set('');
    this.newMinimumReservationDate.set('');
    this.newMaximumReservationDate.set('');
    this.newAllowedWeekdays.set([]);
    this.newExcludedDateRanges.set([]);
    this.newExcludedDateStart.set('');
    this.newExcludedDateEnd.set('');
  }

  private clearCreateOrderSensitiveFields(): void {
    this.newDocumentNumber.set('');
    this.newPassword.set('');
    this.newContactName.set('');
    this.newContactWhatsapp.set('');
    this.newContactWhatsappUsername.set('');
  }

  private maskDocumentNumber(value: string): string {
    const normalized = value.trim();
    if (normalized.length <= 3) {
      return '***';
    }
    return `${normalized.slice(0, 2)}${'*'.repeat(Math.max(normalized.length - 3, 1))}${normalized.slice(-1)}`;
  }

  private prepareExcludedDateRanges(
    ranges: ExcludedDateRange[],
    startDate: string,
    endDate: string,
  ): ExcludedDateRange[] | null {
    const start = startDate.trim();
    const end = endDate.trim();
    if (!start && !end) {
      return this.normalizeExcludedDateRanges(ranges);
    }
    if (!start || !end) {
      this.ui.errorMessage.set('Completa ambas fechas del rango excluido.');
      return null;
    }
    if (end < start) {
      this.ui.errorMessage.set('El final del rango excluido no puede ser anterior al inicio.');
      return null;
    }
    return this.normalizeExcludedDateRanges([...ranges, { start_date: start, end_date: end }]);
  }

  private normalizeExcludedDateRanges(ranges: ExcludedDateRange[]): ExcludedDateRange[] {
    const sorted = [...ranges].sort((left, right) =>
      left.start_date.localeCompare(right.start_date),
    );
    const merged: ExcludedDateRange[] = [];
    for (const range of sorted) {
      const previous = merged.at(-1);
      if (previous && range.start_date <= previous.end_date) {
        previous.end_date =
          previous.end_date >= range.end_date ? previous.end_date : range.end_date;
        continue;
      }
      merged.push({ ...range });
    }
    return merged;
  }

  public closeTrackedManualSessionsWithBeacon(): void {
    if (!this.activeManualSessionIds.size) {
      return;
    }
    for (const sessionId of this.activeManualSessionIds) {
      const body = JSON.stringify({ session_id: sessionId });
      const sent = navigator.sendBeacon?.(
        '/api/v1/manual-session/close',
        new Blob([body], { type: 'application/json' }),
      );
      if (!sent) {
        void this.api.closeManualSession(sessionId).catch(() => undefined);
      }
    }
    this.activeManualSessionIds.clear();
  }

  public async loadOrdersView(scope: RequestScope): Promise<void> {
    this.applyOrders(await this.orderList.fetchOrders(scope));
    return;
  }

  public fetchOrderCommonData(scope: RequestScope) {
    const currentCatalog = this.servicePackageCatalog();
    const catalogRequest = currentCatalog ? Promise.resolve(currentCatalog) : this.api.getServicePackages(scope);
    return Promise.all([this.api.getManualSessions(scope), catalogRequest]);
  }

  public applyOrderCommonData(manualSessions: ManualSession[], catalog: ServicePackageCatalog): void {
    this.manualSessions.set(manualSessions);
    this.servicePackageCatalog.set(catalog);
  }

  private get messages() { return this.injector.get(DASHBOARD_ORDERS_MESSAGES); }

  private get ui() { return this.injector.get(DASHBOARD_ORDERS_UI); }

  private get presentation() { return this.injector.get(DASHBOARD_ORDERS_PRESENTATION); }

  private get navigation() { return this.injector.get(DASHBOARD_ORDERS_NAVIGATION); }

  private get finance() { return this.injector.get(DASHBOARD_ORDERS_FINANCE); }
}
