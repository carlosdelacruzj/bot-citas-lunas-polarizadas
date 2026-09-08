import { Component, HostListener, Injector, ViewEncapsulation, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink, RouterOutlet } from '@angular/router';
import {
  DASHBOARD_CAPTCHAS_NAVIGATION,
  DASHBOARD_CAPTCHAS_OPERATIONS,
  DASHBOARD_CAPTCHAS_PRESENTATION,
  DASHBOARD_CAPTCHAS_UI,
  DASHBOARD_CAPTCHAS_VIEW_CAPTCHAS,
  DASHBOARD_CAPTCHAS_VIEW_PRESENTATION,
  DASHBOARD_CREATE_ORDER_MODAL_ORDERS,
  DASHBOARD_CREATE_ORDER_MODAL_PRESENTATION,
  DASHBOARD_CREATE_ORDER_MODAL_UI,
  DASHBOARD_EDIT_ORDER_MODAL_FINANCE,
  DASHBOARD_EDIT_ORDER_MODAL_ORDERS,
  DASHBOARD_EDIT_ORDER_MODAL_PRESENTATION,
  DASHBOARD_EDIT_ORDER_MODAL_UI,
  DASHBOARD_FINANCE_ENTRY_MODAL_FINANCE,
  DASHBOARD_FINANCE_ENTRY_MODAL_ORDERLIST,
  DASHBOARD_FINANCE_ENTRY_MODAL_UI,
  DASHBOARD_FINANCE_NAVIGATION,
  DASHBOARD_FINANCE_ORDERS,
  DASHBOARD_FINANCE_PRESENTATION,
  DASHBOARD_FINANCE_UI,
  DASHBOARD_FINANCE_VIEW_FINANCE,
  DASHBOARD_FINANCE_VIEW_PRESENTATION,
  DASHBOARD_FINANCE_VIEW_UI,
  DASHBOARD_FOLLOWUPS_NAVIGATION,
  DASHBOARD_FOLLOWUPS_PRESENTATION,
  DASHBOARD_FOLLOWUPS_UI,
  DASHBOARD_FOLLOWUPS_VIEW_FOLLOWUPS,
  DASHBOARD_FOLLOWUPS_VIEW_PRESENTATION,
  DASHBOARD_INBOX_VIEW_CAPTCHAS,
  DASHBOARD_INBOX_VIEW_OPERATIONS,
  DASHBOARD_INBOX_VIEW_UI,
  DASHBOARD_MESSAGES_NAVIGATION,
  DASHBOARD_MESSAGES_ORDERS,
  DASHBOARD_MESSAGES_PRESENTATION,
  DASHBOARD_MESSAGES_UI,
  DASHBOARD_MESSAGE_TEMPLATES_VIEW_MESSAGES,
  DASHBOARD_MESSAGE_TEMPLATES_VIEW_PRESENTATION,
  DASHBOARD_MESSAGE_TEMPLATES_VIEW_UI,
  DASHBOARD_NAVIGATION_CAPTCHAS,
  DASHBOARD_NAVIGATION_FINANCE,
  DASHBOARD_NAVIGATION_FOLLOWUPS,
  DASHBOARD_NAVIGATION_MESSAGES,
  DASHBOARD_NAVIGATION_OPERATIONS,
  DASHBOARD_NAVIGATION_ORDERS,
  DASHBOARD_NAVIGATION_PRESENTATION,
  DASHBOARD_NAVIGATION_UI,
  DASHBOARD_OPERATIONS_CAPTCHAS,
  DASHBOARD_OPERATIONS_FINANCE,
  DASHBOARD_OPERATIONS_FOLLOWUPS,
  DASHBOARD_OPERATIONS_MESSAGES,
  DASHBOARD_OPERATIONS_NAVIGATION,
  DASHBOARD_OPERATIONS_ORDERS,
  DASHBOARD_OPERATIONS_PRESENTATION,
  DASHBOARD_OPERATIONS_UI,
  DASHBOARD_ORDERS_FINANCE,
  DASHBOARD_ORDERS_MESSAGES,
  DASHBOARD_ORDERS_NAVIGATION,
  DASHBOARD_ORDERS_PRESENTATION,
  DASHBOARD_ORDERS_UI,
  DASHBOARD_ORDERS_VIEW_FINANCE,
  DASHBOARD_ORDERS_VIEW_MESSAGES,
  DASHBOARD_ORDERS_VIEW_ORDERLIST,
  DASHBOARD_ORDERS_VIEW_ORDERS,
  DASHBOARD_ORDERS_VIEW_PRESENTATION,
  DASHBOARD_ORDERS_VIEW_UI,
  DASHBOARD_ORDER_ACTIONS_MODAL_ORDERS,
  DASHBOARD_ORDER_ACTIONS_MODAL_PRESENTATION,
  DASHBOARD_ORDER_ACTIONS_MODAL_UI,
  DASHBOARD_PAYMENT_MODAL_FINANCE,
  DASHBOARD_PAYMENT_MODAL_ORDERS,
  DASHBOARD_PAYMENT_MODAL_PRESENTATION,
  DASHBOARD_PAYMENT_MODAL_UI,
  DASHBOARD_PROGRAM_RESOLUTION_PANEL_ORDERS,
  DASHBOARD_PROGRAM_RESOLUTION_PANEL_UI,
  DASHBOARD_RUNS_VIEW_OPERATIONS,
  DASHBOARD_RUNS_VIEW_PRESENTATION,
  DASHBOARD_SHELL_CAPTCHAS,
  DASHBOARD_SHELL_FINANCE,
  DASHBOARD_SHELL_NAVIGATION,
  DASHBOARD_SHELL_OPERATIONS,
  DASHBOARD_SHELL_ORDERS,
  DASHBOARD_SHELL_PRESENTATION,
  DASHBOARD_SHELL_UI,
  DASHBOARD_SUMMARY_VIEW_CAPTCHAS,
  DASHBOARD_SUMMARY_VIEW_FINANCE,
  DASHBOARD_SUMMARY_VIEW_FOLLOWUPS,
  DASHBOARD_SUMMARY_VIEW_NAVIGATION,
  DASHBOARD_SUMMARY_VIEW_OPERATIONS,
  DASHBOARD_SUMMARY_VIEW_ORDERLIST,
  DASHBOARD_SUMMARY_VIEW_PRESENTATION,
  DASHBOARD_SUMMARY_VIEW_UI,
  DASHBOARD_UI_FINANCE,
  DASHBOARD_UI_MESSAGES,
  DASHBOARD_UI_NAVIGATION,
  DASHBOARD_UI_ORDERS,
  DASHBOARD_UI_PRESENTATION,
  DASHBOARD_WHATSAPP_MODAL_MESSAGES,
  DASHBOARD_WHATSAPP_MODAL_PRESENTATION,
  DASHBOARD_WHATSAPP_MODAL_UI,
  DASHBOARD_WORKER_RESTART_MODAL_OPERATIONS,
  DASHBOARD_WORKER_RESTART_MODAL_UI,
} from './dashboard-domain.ports';
import { CaptchasFacade } from './domains/captchas/captchas.facade';
import { FinanceFacade } from './domains/finance/finance.facade';
import { FollowupsFacade } from './domains/followups/followups.facade';
import { MessagesFacade } from './domains/messages/messages.facade';
import { DashboardNavigation } from './domains/navigation/navigation.facade';
import { OperationsFacade } from './domains/operations/operations.facade';
import { OrdersListFacade } from './domains/orders/orders-list.facade';
import { OrdersFacade } from './domains/orders/orders.facade';
import { DashboardPresentation } from './domains/presentation/presentation.facade';
import { DashboardUi } from './domains/ui/ui.facade';
import { CreateOrderModalComponent } from './modals/create-order-modal.component';
import { EditOrderModalComponent } from './modals/edit-order-modal.component';
import { FinanceEntryModalComponent } from './modals/finance-entry-modal.component';
import { OrderActionsModalComponent } from './modals/order-actions-modal.component';
import { PaymentModalComponent } from './modals/payment-modal.component';
import { WhatsappModalComponent } from './modals/whatsapp-modal.component';
import { WorkerRestartModalComponent } from './modals/worker-restart-modal.component';
import { ViewStateComponent } from './view-state/view-state.component';

@Component({
  selector: 'app-root',
  imports: [
    FormsModule,
    ViewStateComponent,
    RouterOutlet,
    RouterLink,
    WhatsappModalComponent,
    PaymentModalComponent,
    EditOrderModalComponent,
    OrderActionsModalComponent,
    CreateOrderModalComponent,
    FinanceEntryModalComponent,
    WorkerRestartModalComponent,
  ],
  providers: [OrdersListFacade, OrdersFacade, FinanceFacade, MessagesFacade, FollowupsFacade, CaptchasFacade, OperationsFacade, DashboardUi, DashboardNavigation, DashboardPresentation,
    { provide: DASHBOARD_ORDERS_MESSAGES, useExisting: MessagesFacade },
    { provide: DASHBOARD_ORDERS_UI, useExisting: DashboardUi },
    { provide: DASHBOARD_ORDERS_PRESENTATION, useExisting: DashboardPresentation },
    { provide: DASHBOARD_ORDERS_NAVIGATION, useExisting: DashboardNavigation },
    { provide: DASHBOARD_ORDERS_FINANCE, useExisting: FinanceFacade },
    { provide: DASHBOARD_FINANCE_NAVIGATION, useExisting: DashboardNavigation },
    { provide: DASHBOARD_FINANCE_UI, useExisting: DashboardUi },
    { provide: DASHBOARD_FINANCE_PRESENTATION, useExisting: DashboardPresentation },
    { provide: DASHBOARD_FINANCE_ORDERS, useExisting: OrdersFacade },
    { provide: DASHBOARD_MESSAGES_UI, useExisting: DashboardUi },
    { provide: DASHBOARD_MESSAGES_PRESENTATION, useExisting: DashboardPresentation },
    { provide: DASHBOARD_MESSAGES_NAVIGATION, useExisting: DashboardNavigation },
    { provide: DASHBOARD_MESSAGES_ORDERS, useExisting: OrdersFacade },
    { provide: DASHBOARD_FOLLOWUPS_UI, useExisting: DashboardUi },
    { provide: DASHBOARD_FOLLOWUPS_NAVIGATION, useExisting: DashboardNavigation },
    { provide: DASHBOARD_FOLLOWUPS_PRESENTATION, useExisting: DashboardPresentation },
    { provide: DASHBOARD_CAPTCHAS_OPERATIONS, useExisting: OperationsFacade },
    { provide: DASHBOARD_CAPTCHAS_NAVIGATION, useExisting: DashboardNavigation },
    { provide: DASHBOARD_CAPTCHAS_PRESENTATION, useExisting: DashboardPresentation },
    { provide: DASHBOARD_CAPTCHAS_UI, useExisting: DashboardUi },
    { provide: DASHBOARD_OPERATIONS_PRESENTATION, useExisting: DashboardPresentation },
    { provide: DASHBOARD_OPERATIONS_CAPTCHAS, useExisting: CaptchasFacade },
    { provide: DASHBOARD_OPERATIONS_ORDERS, useExisting: OrdersFacade },
    { provide: DASHBOARD_OPERATIONS_MESSAGES, useExisting: MessagesFacade },
    { provide: DASHBOARD_OPERATIONS_FINANCE, useExisting: FinanceFacade },
    { provide: DASHBOARD_OPERATIONS_UI, useExisting: DashboardUi },
    { provide: DASHBOARD_OPERATIONS_NAVIGATION, useExisting: DashboardNavigation },
    { provide: DASHBOARD_OPERATIONS_FOLLOWUPS, useExisting: FollowupsFacade },
    { provide: DASHBOARD_UI_NAVIGATION, useExisting: DashboardNavigation },
    { provide: DASHBOARD_UI_ORDERS, useExisting: OrdersFacade },
    { provide: DASHBOARD_UI_FINANCE, useExisting: FinanceFacade },
    { provide: DASHBOARD_UI_MESSAGES, useExisting: MessagesFacade },
    { provide: DASHBOARD_UI_PRESENTATION, useExisting: DashboardPresentation },
    { provide: DASHBOARD_NAVIGATION_UI, useExisting: DashboardUi },
    { provide: DASHBOARD_NAVIGATION_FINANCE, useExisting: FinanceFacade },
    { provide: DASHBOARD_NAVIGATION_MESSAGES, useExisting: MessagesFacade },
    { provide: DASHBOARD_NAVIGATION_OPERATIONS, useExisting: OperationsFacade },
    { provide: DASHBOARD_NAVIGATION_FOLLOWUPS, useExisting: FollowupsFacade },
    { provide: DASHBOARD_NAVIGATION_CAPTCHAS, useExisting: CaptchasFacade },
    { provide: DASHBOARD_NAVIGATION_ORDERS, useExisting: OrdersFacade },
    { provide: DASHBOARD_NAVIGATION_PRESENTATION, useExisting: DashboardPresentation },
    { provide: DASHBOARD_CREATE_ORDER_MODAL_UI, useExisting: DashboardUi },
    { provide: DASHBOARD_CREATE_ORDER_MODAL_ORDERS, useExisting: OrdersFacade },
    { provide: DASHBOARD_CREATE_ORDER_MODAL_PRESENTATION, useExisting: DashboardPresentation },
    { provide: DASHBOARD_EDIT_ORDER_MODAL_UI, useExisting: DashboardUi },
    { provide: DASHBOARD_EDIT_ORDER_MODAL_ORDERS, useExisting: OrdersFacade },
    { provide: DASHBOARD_EDIT_ORDER_MODAL_PRESENTATION, useExisting: DashboardPresentation },
    { provide: DASHBOARD_EDIT_ORDER_MODAL_FINANCE, useExisting: FinanceFacade },
    { provide: DASHBOARD_FINANCE_ENTRY_MODAL_UI, useExisting: DashboardUi },
    { provide: DASHBOARD_FINANCE_ENTRY_MODAL_FINANCE, useExisting: FinanceFacade },
    { provide: DASHBOARD_FINANCE_ENTRY_MODAL_ORDERLIST, useExisting: OrdersListFacade },
    { provide: DASHBOARD_ORDER_ACTIONS_MODAL_UI, useExisting: DashboardUi },
    { provide: DASHBOARD_ORDER_ACTIONS_MODAL_ORDERS, useExisting: OrdersFacade },
    { provide: DASHBOARD_ORDER_ACTIONS_MODAL_PRESENTATION, useExisting: DashboardPresentation },
    { provide: DASHBOARD_PAYMENT_MODAL_UI, useExisting: DashboardUi },
    { provide: DASHBOARD_PAYMENT_MODAL_ORDERS, useExisting: OrdersFacade },
    { provide: DASHBOARD_PAYMENT_MODAL_PRESENTATION, useExisting: DashboardPresentation },
    { provide: DASHBOARD_PAYMENT_MODAL_FINANCE, useExisting: FinanceFacade },
    { provide: DASHBOARD_WHATSAPP_MODAL_UI, useExisting: DashboardUi },
    { provide: DASHBOARD_WHATSAPP_MODAL_MESSAGES, useExisting: MessagesFacade },
    { provide: DASHBOARD_WHATSAPP_MODAL_PRESENTATION, useExisting: DashboardPresentation },
    { provide: DASHBOARD_WORKER_RESTART_MODAL_UI, useExisting: DashboardUi },
    { provide: DASHBOARD_WORKER_RESTART_MODAL_OPERATIONS, useExisting: OperationsFacade },
    { provide: DASHBOARD_PROGRAM_RESOLUTION_PANEL_ORDERS, useExisting: OrdersFacade },
    { provide: DASHBOARD_PROGRAM_RESOLUTION_PANEL_UI, useExisting: DashboardUi },
    { provide: DASHBOARD_CAPTCHAS_VIEW_CAPTCHAS, useExisting: CaptchasFacade },
    { provide: DASHBOARD_CAPTCHAS_VIEW_PRESENTATION, useExisting: DashboardPresentation },
    { provide: DASHBOARD_FINANCE_VIEW_FINANCE, useExisting: FinanceFacade },
    { provide: DASHBOARD_FINANCE_VIEW_PRESENTATION, useExisting: DashboardPresentation },
    { provide: DASHBOARD_FINANCE_VIEW_UI, useExisting: DashboardUi },
    { provide: DASHBOARD_FOLLOWUPS_VIEW_FOLLOWUPS, useExisting: FollowupsFacade },
    { provide: DASHBOARD_FOLLOWUPS_VIEW_PRESENTATION, useExisting: DashboardPresentation },
    { provide: DASHBOARD_INBOX_VIEW_OPERATIONS, useExisting: OperationsFacade },
    { provide: DASHBOARD_INBOX_VIEW_UI, useExisting: DashboardUi },
    { provide: DASHBOARD_INBOX_VIEW_CAPTCHAS, useExisting: CaptchasFacade },
    { provide: DASHBOARD_MESSAGE_TEMPLATES_VIEW_MESSAGES, useExisting: MessagesFacade },
    { provide: DASHBOARD_MESSAGE_TEMPLATES_VIEW_UI, useExisting: DashboardUi },
    { provide: DASHBOARD_MESSAGE_TEMPLATES_VIEW_PRESENTATION, useExisting: DashboardPresentation },
    { provide: DASHBOARD_ORDERS_VIEW_MESSAGES, useExisting: MessagesFacade },
    { provide: DASHBOARD_ORDERS_VIEW_ORDERS, useExisting: OrdersFacade },
    { provide: DASHBOARD_ORDERS_VIEW_PRESENTATION, useExisting: DashboardPresentation },
    { provide: DASHBOARD_ORDERS_VIEW_UI, useExisting: DashboardUi },
    { provide: DASHBOARD_ORDERS_VIEW_FINANCE, useExisting: FinanceFacade },
    { provide: DASHBOARD_ORDERS_VIEW_ORDERLIST, useExisting: OrdersListFacade },
    { provide: DASHBOARD_RUNS_VIEW_OPERATIONS, useExisting: OperationsFacade },
    { provide: DASHBOARD_RUNS_VIEW_PRESENTATION, useExisting: DashboardPresentation },
    { provide: DASHBOARD_SUMMARY_VIEW_FINANCE, useExisting: FinanceFacade },
    { provide: DASHBOARD_SUMMARY_VIEW_FOLLOWUPS, useExisting: FollowupsFacade },
    { provide: DASHBOARD_SUMMARY_VIEW_PRESENTATION, useExisting: DashboardPresentation },
    { provide: DASHBOARD_SUMMARY_VIEW_OPERATIONS, useExisting: OperationsFacade },
    { provide: DASHBOARD_SUMMARY_VIEW_ORDERLIST, useExisting: OrdersListFacade },
    { provide: DASHBOARD_SUMMARY_VIEW_CAPTCHAS, useExisting: CaptchasFacade },
    { provide: DASHBOARD_SUMMARY_VIEW_UI, useExisting: DashboardUi },
    { provide: DASHBOARD_SUMMARY_VIEW_NAVIGATION, useExisting: DashboardNavigation },
    { provide: DASHBOARD_SHELL_NAVIGATION, useExisting: DashboardNavigation },
    { provide: DASHBOARD_SHELL_OPERATIONS, useExisting: OperationsFacade },
    { provide: DASHBOARD_SHELL_FINANCE, useExisting: FinanceFacade },
    { provide: DASHBOARD_SHELL_CAPTCHAS, useExisting: CaptchasFacade },
    { provide: DASHBOARD_SHELL_UI, useExisting: DashboardUi },
    { provide: DASHBOARD_SHELL_ORDERS, useExisting: OrdersFacade },
    { provide: DASHBOARD_SHELL_PRESENTATION, useExisting: DashboardPresentation }
  ],
  templateUrl: './app.html',
  styleUrl: './app.css',
  encapsulation: ViewEncapsulation.None,
})
export class App {
  private readonly injector = inject(Injector);

  constructor() {
    inject(DashboardUi);
    inject(DashboardNavigation);
  }

  @HostListener('document:visibilitychange')
  public onVisibilityChange(): void {
    this.navigation.handleVisibilityChange();
  }

  @HostListener('document:keydown.escape')
  public onEscape(): void {
    this.ui.handleEscape();
  }

  @HostListener('window:beforeunload')
  public onBeforeUnload(): void {
    this.orders.handleBeforeUnload();
  }

  @HostListener('document:keydown', ['$event'])
  public onCaptchaKey(event: KeyboardEvent): void {
    this.captchas.handleCaptchaReviewKeyboard(event);
  }

  public get navigation() { return this.injector.get(DASHBOARD_SHELL_NAVIGATION); }

  public get operations() { return this.injector.get(DASHBOARD_SHELL_OPERATIONS); }

  public get finance() { return this.injector.get(DASHBOARD_SHELL_FINANCE); }

  public get captchas() { return this.injector.get(DASHBOARD_SHELL_CAPTCHAS); }

  public get ui() { return this.injector.get(DASHBOARD_SHELL_UI); }

  public get orders() { return this.injector.get(DASHBOARD_SHELL_ORDERS); }

  public get presentation() { return this.injector.get(DASHBOARD_SHELL_PRESENTATION); }
}
