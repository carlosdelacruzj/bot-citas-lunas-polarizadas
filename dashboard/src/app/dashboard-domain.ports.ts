import { InjectionToken } from '@angular/core';
import type { CaptchasFacade } from './domains/captchas/captchas.facade';
import type { FinanceFacade } from './domains/finance/finance.facade';
import type { FollowupsFacade } from './domains/followups/followups.facade';
import type { MessagesFacade } from './domains/messages/messages.facade';
import type { DashboardNavigation } from './domains/navigation/navigation.facade';
import type { OperationsFacade } from './domains/operations/operations.facade';
import type { OrdersListFacade } from './domains/orders/orders-list.facade';
import type { OrdersFacade } from './domains/orders/orders.facade';
import type { DashboardPresentation } from './domains/presentation/presentation.facade';
import type { DashboardUi } from './domains/ui/ui.facade';

export const DASHBOARD_SUMMARY_VIEW_ORDERS = new InjectionToken<Pick<OrdersFacade, 'loads'>>('DASHBOARD_SUMMARY_VIEW_ORDERS');

export const DASHBOARD_ORDERS_MESSAGES = new InjectionToken<Pick<MessagesFacade,
  "loads" |
  "isPostPaymentWhatsAppCandidate"
  | "openPostPaymentWhatsApp"
  | "openWhatsAppReview"
>>('DASHBOARD_ORDERS_MESSAGES');

export const DASHBOARD_ORDERS_UI = new InjectionToken<Pick<DashboardUi,
  "actionBusy"
  | "captureFocus"
  | "formDirty"
  | "activeModal"
  | "restoreFocus"
  | "openModal"
  | "errorMessage"
  | "setPendingAction"
  | "editField"
  | "markCopied"
  | "showToast"
>>('DASHBOARD_ORDERS_UI');

export const DASHBOARD_ORDERS_PRESENTATION = new InjectionToken<Pick<DashboardPresentation,
  "capitalize"
  | "optionalText"
  | "readError"
  | "statusLabel"
>>('DASHBOARD_ORDERS_PRESENTATION');

export const DASHBOARD_ORDERS_NAVIGATION = new InjectionToken<Pick<DashboardNavigation,
  "activeView"
  | "refreshAll"
>>('DASHBOARD_ORDERS_NAVIGATION');

export const DASHBOARD_ORDERS_FINANCE = new InjectionToken<Pick<FinanceFacade,
  "loads" |
  "openPayment"
  | "paymentAmountPaid"
  | "paymentAmountAgreed"
>>('DASHBOARD_ORDERS_FINANCE');

export const DASHBOARD_FINANCE_NAVIGATION = new InjectionToken<Pick<DashboardNavigation,
  "activeView"
  | "refreshAll"
>>('DASHBOARD_FINANCE_NAVIGATION');

export const DASHBOARD_FINANCE_UI = new InjectionToken<Pick<DashboardUi,
  "errorMessage"
  | "openModal"
  | "setPendingAction"
  | "activeModal"
  | "getSweetAlert"
  | "actionBusy"
  | "showToast"
  | "editField"
  | "formDirty"
>>('DASHBOARD_FINANCE_UI');

export const DASHBOARD_FINANCE_PRESENTATION = new InjectionToken<Pick<DashboardPresentation,
  "readError"
  | "formatDate"
  | "formatMoney"
  | "formatPercent"
  | "statusLabel"
  | "optionalText"
>>('DASHBOARD_FINANCE_PRESENTATION');

export const DASHBOARD_FINANCE_ORDERS = new InjectionToken<Pick<OrdersFacade,
  "loads" |
  "selectOrder"
  | "standardPackageAmount"
  | "loadSelectedOrderDetail"
  | "selectedOrderDetail"
  | "requireSelectedOrder"
>>('DASHBOARD_FINANCE_ORDERS');

export const DASHBOARD_MESSAGES_UI = new InjectionToken<Pick<DashboardUi,
  "openModal"
  | "errorMessage"
  | "showToast"
  | "getSweetAlert"
  | "actionBusy"
  | "closeModal"
  | "markCopied"
>>('DASHBOARD_MESSAGES_UI');

export const DASHBOARD_MESSAGES_PRESENTATION = new InjectionToken<Pick<DashboardPresentation,
  "readError"
>>('DASHBOARD_MESSAGES_PRESENTATION');

export const DASHBOARD_MESSAGES_NAVIGATION = new InjectionToken<Pick<DashboardNavigation,
  "refreshAll"
>>('DASHBOARD_MESSAGES_NAVIGATION');

export const DASHBOARD_MESSAGES_ORDERS = new InjectionToken<Pick<OrdersFacade,
  "loads" |
  "selectedOrderDetail"
>>('DASHBOARD_MESSAGES_ORDERS');

export const DASHBOARD_FOLLOWUPS_UI = new InjectionToken<Pick<DashboardUi,
  "errorMessage"
  | "showToast"
>>('DASHBOARD_FOLLOWUPS_UI');

export const DASHBOARD_FOLLOWUPS_NAVIGATION = new InjectionToken<Pick<DashboardNavigation,
  "lastUpdatedAt"
  | "activeView"
>>('DASHBOARD_FOLLOWUPS_NAVIGATION');

export const DASHBOARD_FOLLOWUPS_PRESENTATION = new InjectionToken<Pick<DashboardPresentation,
  "formatClock"
  | "readError"
>>('DASHBOARD_FOLLOWUPS_PRESENTATION');

export const DASHBOARD_CAPTCHAS_OPERATIONS = new InjectionToken<Pick<OperationsFacade,
  "loads" |
  "health"
>>('DASHBOARD_CAPTCHAS_OPERATIONS');

export const DASHBOARD_CAPTCHAS_NAVIGATION = new InjectionToken<Pick<DashboardNavigation,
  "activeView"
  | "scheduleNextRefresh"
>>('DASHBOARD_CAPTCHAS_NAVIGATION');

export const DASHBOARD_CAPTCHAS_PRESENTATION = new InjectionToken<Pick<DashboardPresentation,
  "readError"
>>('DASHBOARD_CAPTCHAS_PRESENTATION');

export const DASHBOARD_CAPTCHAS_UI = new InjectionToken<Pick<DashboardUi,
  "errorMessage"
  | "showToast"
  | "setPendingAction"
>>('DASHBOARD_CAPTCHAS_UI');

export const DASHBOARD_OPERATIONS_PRESENTATION = new InjectionToken<Pick<DashboardPresentation,
  "statusTone"
  | "readError"
>>('DASHBOARD_OPERATIONS_PRESENTATION');

export const DASHBOARD_OPERATIONS_CAPTCHAS = new InjectionToken<Pick<CaptchasFacade,
  "loads" |
  "showCaptchaWorkspace"
  | "loadPendingReview"
  | "captchaShadowEnabled"
  | "captchaReviewTotal"
  | "loadSamplingControl"
  | "loadAuthorityControl"
  | "applyCaptchaSamplingControl"
  | "captchaAuthorityControl"
>>('DASHBOARD_OPERATIONS_CAPTCHAS');

export const DASHBOARD_OPERATIONS_ORDERS = new InjectionToken<Pick<OrdersFacade,
  "loadOrderList" |
  "loads" |
  "openEditOrder"
  | "selectOrder"
  | "requestOrderValidation"
  | "applyOrders"
>>('DASHBOARD_OPERATIONS_ORDERS');

export const DASHBOARD_OPERATIONS_MESSAGES = new InjectionToken<Pick<MessagesFacade,
  "loads" |
  "openOrderWhatsApp"
  | "openWhatsAppReview"
>>('DASHBOARD_OPERATIONS_MESSAGES');

export const DASHBOARD_OPERATIONS_FINANCE = new InjectionToken<Pick<FinanceFacade,
  "loads" |
  "openPayment"
  | "loadMonthlySummary"
  | "monthlySummary"
>>('DASHBOARD_OPERATIONS_FINANCE');

export const DASHBOARD_OPERATIONS_UI = new InjectionToken<Pick<DashboardUi,
  "actionBusy"
  | "errorMessage"
  | "openModal"
  | "setPendingAction"
  | "activeModal"
  | "markCopied"
>>('DASHBOARD_OPERATIONS_UI');

export const DASHBOARD_OPERATIONS_NAVIGATION = new InjectionToken<Pick<DashboardNavigation,
  "activeView"
>>('DASHBOARD_OPERATIONS_NAVIGATION');

export const DASHBOARD_OPERATIONS_FOLLOWUPS = new InjectionToken<Pick<FollowupsFacade,
  "loads" |
  "loadReminders"
  | "appointmentReminderStatus"
>>('DASHBOARD_OPERATIONS_FOLLOWUPS');

export const DASHBOARD_UI_NAVIGATION = new InjectionToken<Pick<DashboardNavigation,
  "mobileMenuOpen"
  | "refreshAll"
>>('DASHBOARD_UI_NAVIGATION');

export const DASHBOARD_UI_ORDERS = new InjectionToken<Pick<OrdersFacade,
  "loads" |
  "orderPanelOpen"
  | "closeOrderPanel"
  | "hydrateSelectedOrderForms"
  | "clearCreateOrderForm"
  | "selectedOrderId"
>>('DASHBOARD_UI_ORDERS');

export const DASHBOARD_UI_FINANCE = new InjectionToken<Pick<FinanceFacade,
  "loads" |
  "clearFinanceForm"
>>('DASHBOARD_UI_FINANCE');

export const DASHBOARD_UI_MESSAGES = new InjectionToken<Pick<MessagesFacade,
  "loads" |
  "clearWhatsAppForm"
>>('DASHBOARD_UI_MESSAGES');

export const DASHBOARD_UI_PRESENTATION = new InjectionToken<Pick<DashboardPresentation,
  "readError"
>>('DASHBOARD_UI_PRESENTATION');

export const DASHBOARD_NAVIGATION_UI = new InjectionToken<Pick<DashboardUi,
  "formDirty"
  | "actionBusy"
  | "pendingAction"
  | "disposeNotifications"
  | "errorMessage"
>>('DASHBOARD_NAVIGATION_UI');

export const DASHBOARD_NAVIGATION_FINANCE = new InjectionToken<Pick<FinanceFacade,
  "selectMonth" |
  "loads" |
  "monthlySummary"
  | "financeSummary"
  | "selectedMonth"
  | "loadFinanceView"
>>('DASHBOARD_NAVIGATION_FINANCE');

export const DASHBOARD_NAVIGATION_MESSAGES = new InjectionToken<Pick<MessagesFacade,
  "loads" |
  "whatsappMessageTemplates"
  | "loadMessagesView"
>>('DASHBOARD_NAVIGATION_MESSAGES');

export const DASHBOARD_NAVIGATION_OPERATIONS = new InjectionToken<Pick<OperationsFacade,
  "disposeReadRequests" |
  "loads" |
  "runs"
  | "workerCommands"
  | "selectedRunId"
  | "selectRun"
  | "closeRunDetail"
  | "loadHealth"

  | "loadInboxView"
  | "loadSummaryView"
  | "loadRunsView"
>>('DASHBOARD_NAVIGATION_OPERATIONS');

export const DASHBOARD_NAVIGATION_FOLLOWUPS = new InjectionToken<Pick<FollowupsFacade,
  "loads" |
  "postAppointmentPayload"
  | "disposeFollowupRequests"
  | "loadFollowupsView"
>>('DASHBOARD_NAVIGATION_FOLLOWUPS');

export const DASHBOARD_NAVIGATION_CAPTCHAS = new InjectionToken<Pick<CaptchasFacade,
  "loads" |
  "captchaSummary"
  | "disposeCaptchaRequests"
  | "captchaWorkspaceMode"
  | "captchaShadowEnabled"
  | "loadCaptchaData"
  | "captchaState"
>>('DASHBOARD_NAVIGATION_CAPTCHAS');

export const DASHBOARD_NAVIGATION_ORDERS = new InjectionToken<Pick<OrdersFacade,
  "loads" |
  "closeTrackedManualSessionsWithBeacon"
  | "selectedOrderId"
  | "orderPanelOpen"
  | "selectOrder"
  | "closeOrderPanel"
  | "cancelOrderDetail" | "loadCommonData"

  | "loadOrdersView"
>>('DASHBOARD_NAVIGATION_ORDERS');

export const DASHBOARD_NAVIGATION_PRESENTATION = new InjectionToken<Pick<DashboardPresentation,
  "formatClock"
  | "readError"
>>('DASHBOARD_NAVIGATION_PRESENTATION');

export const DASHBOARD_CREATE_ORDER_MODAL_UI = new InjectionToken<Pick<DashboardUi,
  "activeModal"
  | "closeModal"
  | "editField"
  | "formDirty"
>>('DASHBOARD_CREATE_ORDER_MODAL_UI');

export const DASHBOARD_CREATE_ORDER_MODAL_ORDERS = new InjectionToken<Pick<OrdersFacade,
  "loads" |
  "newDocumentType"
  | "newDocumentNumber"
  | "newPassword"
  | "newContactName"
  | "newContactWhatsapp"
  | "newContactWhatsappUsername"
  | "newContactSource"
  | "newServicePackage"
  | "servicePackages"
  | "servicePackageOptionLabel"
  | "newServicePackageDefinition"
  | "newCustomReservationPrice"
  | "newMinimumReservationDate"
  | "newMaximumReservationDate"
  | "newAllowedWeekdays"
  | "newExcludedDateRanges"
  | "newExcludedDateStart"
  | "newExcludedDateEnd"
  | "addNewExcludedDateRange"
  | "removeNewExcludedDateRange"
  | "clearNewExcludedDateRanges"
  | "requestCreateOrder"
>>('DASHBOARD_CREATE_ORDER_MODAL_ORDERS');

export const DASHBOARD_CREATE_ORDER_MODAL_PRESENTATION = new InjectionToken<Pick<DashboardPresentation,
  "formatMoney"
>>('DASHBOARD_CREATE_ORDER_MODAL_PRESENTATION');

export const DASHBOARD_EDIT_ORDER_MODAL_UI = new InjectionToken<Pick<DashboardUi,
  "activeModal"
  | "closeModal"
  | "editField"
>>('DASHBOARD_EDIT_ORDER_MODAL_UI');

export const DASHBOARD_EDIT_ORDER_MODAL_ORDERS = new InjectionToken<Pick<OrdersFacade,
  "loads" |
  "modalOrder"
  | "orderLabel"
  | "editOrderSection"
  | "orderDetailLoading"
  | "contactName"
  | "selectedOrderWhatsappPlaceholder"
  | "contactWhatsapp"
  | "contactWhatsappUsername"
  | "contactSource"
  | "requestContactUpdate"
  | "isClosedOrder"
  | "orderDocumentType"
  | "orderDocumentNumber"
  | "orderPasswordVisible"
  | "orderPassword"
  | "toggleOrderPasswordVisibility"
  | "requestCredentialsUpdate"
  | "orderMinimumReservationDate"
  | "orderMaximumReservationDate"
  | "orderAllowedWeekdays"
  | "orderExcludedDateRanges"
  | "orderExcludedDateStart"
  | "orderExcludedDateEnd"
  | "addOrderExcludedDateRange"
  | "removeOrderExcludedDateRange"
  | "clearOrderExcludedDateRanges"
  | "requestReservationRestrictionsUpdate"
  | "orderPriority"
  | "requestPriorityUpdate"
>>('DASHBOARD_EDIT_ORDER_MODAL_ORDERS');

export const DASHBOARD_EDIT_ORDER_MODAL_PRESENTATION = new InjectionToken<Pick<DashboardPresentation,
  "statusLabel"
  | "statusTone"
>>('DASHBOARD_EDIT_ORDER_MODAL_PRESENTATION');

export const DASHBOARD_EDIT_ORDER_MODAL_FINANCE = new InjectionToken<Pick<FinanceFacade,
  "loads" |
  "paymentLabel"
>>('DASHBOARD_EDIT_ORDER_MODAL_FINANCE');

export const DASHBOARD_FINANCE_ENTRY_MODAL_UI = new InjectionToken<Pick<DashboardUi,
  "activeModal"
  | "closeModal"
  | "editField"
>>('DASHBOARD_FINANCE_ENTRY_MODAL_UI');

export const DASHBOARD_FINANCE_ENTRY_MODAL_FINANCE = new InjectionToken<Pick<FinanceFacade,
  "loads" |
  "editingFinanceEntryId"
  | "financeOccurredOn"
  | "financeEntryKind"
  | "financeCategoryCode"
  | "financeCategories"
  | "financeDataQuality"
  | "financeDescription"
  | "financeVendor"
  | "financeAmountOriginal"
  | "financeCurrency"
  | "financeExchangeRatePen"
  | "financeQuantity"
  | "financeUnit"
  | "financeChannel"
  | "financeCampaign"
  | "financeOrderId"
  | "financeEvidenceReference"
  | "financeNotes"
  | "requestSaveFinanceEntry"
>>('DASHBOARD_FINANCE_ENTRY_MODAL_FINANCE');

export const DASHBOARD_FINANCE_ENTRY_MODAL_ORDERLIST = new InjectionToken<Pick<OrdersListFacade,
  "orders"
>>('DASHBOARD_FINANCE_ENTRY_MODAL_ORDERLIST');

export const DASHBOARD_ORDER_ACTIONS_MODAL_UI = new InjectionToken<Pick<DashboardUi,
  "activeModal"
  | "closeModal"
  | "actionBusy"
  | "editField"
>>('DASHBOARD_ORDER_ACTIONS_MODAL_UI');

export const DASHBOARD_ORDER_ACTIONS_MODAL_ORDERS = new InjectionToken<Pick<OrdersFacade,
  "loads" |
  "modalOrder"
  | "orderLabel"
  | "closureDisplay"
  | "requestOrderAction"
  | "hasActiveChildOrders"
  | "isClosedOrder"
  | "requestManualSession"
  | "manualSessionActionLabel"
  | "requestDiagnosticSession"
  | "closureReason"
  | "setClosureReason"
  | "closureNote"
  | "requestCloseOrder"
>>('DASHBOARD_ORDER_ACTIONS_MODAL_ORDERS');

export const DASHBOARD_ORDER_ACTIONS_MODAL_PRESENTATION = new InjectionToken<Pick<DashboardPresentation,
  "statusLabel"
>>('DASHBOARD_ORDER_ACTIONS_MODAL_PRESENTATION');

export const DASHBOARD_PAYMENT_MODAL_UI = new InjectionToken<Pick<DashboardUi,
  "activeModal"
  | "closeModal"
  | "editField"
  | "actionBusy"
>>('DASHBOARD_PAYMENT_MODAL_UI');

export const DASHBOARD_PAYMENT_MODAL_ORDERS = new InjectionToken<Pick<OrdersFacade,
  "loads" |
  "modalOrder"
  | "orderLabel"
  | "servicePackageDefinition"
  | "standardPackageAmount"
>>('DASHBOARD_PAYMENT_MODAL_ORDERS');

export const DASHBOARD_PAYMENT_MODAL_PRESENTATION = new InjectionToken<Pick<DashboardPresentation,
  "formatMoney"
  | "formatDate"
  | "formatTime"
>>('DASHBOARD_PAYMENT_MODAL_PRESENTATION');

export const DASHBOARD_PAYMENT_MODAL_FINANCE = new InjectionToken<Pick<FinanceFacade,
  "loads" |
  "paymentAmountAgreed"
  | "paymentAmountPaid"
  | "setQuickPaymentAmount"
  | "requestMarkPaid"
>>('DASHBOARD_PAYMENT_MODAL_FINANCE');

export const DASHBOARD_WHATSAPP_MODAL_UI = new InjectionToken<Pick<DashboardUi,
  "activeModal"
  | "actionBusy"
  | "closeModal"
>>('DASHBOARD_WHATSAPP_MODAL_UI');

export const DASHBOARD_WHATSAPP_MODAL_MESSAGES = new InjectionToken<Pick<MessagesFacade,
  "loads" |
  "whatsappTestMode"
  | "whatsappReviewMode"
  | "whatsappFollowUpMode"
  | "whatsappPackage"
  | "whatsappFollowUpPackage"
  | "whatsappTestRecipient"
  | "whatsappFollowUpLoading"
  | "whatsappPackageLoading"
  | "prepareWhatsAppTest"
  | "whatsappReview"
  | "copyWhatsAppText"
  | "whatsappWebBusy"
  | "confirmAndSendWhatsAppFollowUp"
  | "whatsappWebResult"
  | "confirmWhatsAppFollowUpSent"
  | "whatsappReviewNote"
  | "resolveWhatsAppReview"
  | "confirmAndSendWhatsAppEvidence"
  | "whatsappManualFallbackOpen"
  | "copyWhatsAppAttachment"
  | "confirmWhatsAppSent"
>>('DASHBOARD_WHATSAPP_MODAL_MESSAGES');

export const DASHBOARD_WHATSAPP_MODAL_PRESENTATION = new InjectionToken<Pick<DashboardPresentation,
  "statusLabel"
  | "formatDateTime"
  | "statusTone"
>>('DASHBOARD_WHATSAPP_MODAL_PRESENTATION');

export const DASHBOARD_WORKER_RESTART_MODAL_UI = new InjectionToken<Pick<DashboardUi,
  "activeModal"
  | "closeModal"
>>('DASHBOARD_WORKER_RESTART_MODAL_UI');

export const DASHBOARD_WORKER_RESTART_MODAL_OPERATIONS = new InjectionToken<Pick<OperationsFacade,
  "loads" |
  "phaseLabel"
  | "worker"
  | "health"
  | "currentWorkLabel"
  | "releaseSafeBackoffsOnRestart"
  | "requestRestartWorker"
>>('DASHBOARD_WORKER_RESTART_MODAL_OPERATIONS');

export const DASHBOARD_PROGRAM_RESOLUTION_PANEL_ORDERS = new InjectionToken<Pick<OrdersFacade,
  "loads" |
  "selectedOrderDetail"
  | "requestProgramResolution"
  | "orderDetailLoading"
  | "servicePriceLabel"
  | "restrictionDaysLabel"
  | "restrictionTimingLabel"
  | "openProgramResolution"
>>('DASHBOARD_PROGRAM_RESOLUTION_PANEL_ORDERS');

export const DASHBOARD_PROGRAM_RESOLUTION_PANEL_UI = new InjectionToken<Pick<DashboardUi,
  "formDirty"
  | "errorMessage"
  | "actionBusy"
  | "closeModal"
>>('DASHBOARD_PROGRAM_RESOLUTION_PANEL_UI');

export const DASHBOARD_CAPTCHAS_VIEW_CAPTCHAS = new InjectionToken<Pick<CaptchasFacade,
  "loads" |
  "showAllPendingCaptchas"
  | "captchaState"
  | "loadCaptchaData"
  | "captchaSummary"
  | "captchaReviewTotal"
  | "captchaPendingTotal"
  | "captchaWorkspaceMode"
  | "showCaptchaWorkspace"
  | "captchaTotal"
  | "captchaQuality"
  | "captchaError"
  | "activeCaptchaReview"
  | "captchaReviewPosition"
  | "captchaReviewReasonLabel"
  | "captchaChoiceLabel"
  | "captchaSourceLabel"
  | "captchaReviewMessage"
  | "captchaOrderLabel"
  | "captchaChoiceMode"
  | "captchaPredictionOptions"
  | "captchaSuggestionTone"
  | "captchaSavingEventId"
  | "chooseCaptchaPrediction"
  | "saveCaptchaHumanLabel"
  | "captchaDraft"
  | "updateCaptchaDraft"
  | "isObserverCaptcha"
  | "formatMilliseconds"
  | "captchaPredictionTone"
  | "captchaModelLabel"
  | "moveCaptchaReview"
  | "captchaReviewQueue"
  | "applyCaptchaFilters"
  | "captchaSearch"
  | "captchaReviewStatus"
  | "changeCaptchaReviewStatus"
  | "toggleCaptchaHistoryFilters"
  | "captchaActiveFilterCount"
  | "captchaHistoryFiltersOpen"
  | "captchaAgreement"
  | "setCaptchaAgreement"
  | "captchaSource"
  | "changeCaptchaSource"
  | "captchaPortalStatus"
  | "changeCaptchaPortalStatus"
  | "captchaPage"
  | "captchaTotalPages"
  | "captchaEvents"
  | "captchaAgreementTone"
  | "captchaAgreementLabel"
  | "captchaPortalTone"
  | "captchaPortalLabel"
  | "captchaLocalTotalMs"
  | "pendingCaptchaCorrection"
  | "confirmCaptchaCorrection"
  | "cancelCaptchaCorrection"
  | "formatConfidence"
  | "captchaPageSize"
  | "changeCaptchaPageSize"
  | "goToCaptchaPage"
  | "captchaPageNumbers"
  | "captchaQualityState"
  | "captchaQualityError"
  | "loadCaptchaQuality"
  | "captchaDatasetExporting"
  | "exportCaptchaDataset"
  | "captchaQualityBestModel"
  | "captchaQualityAccuracy"
  | "captchaQualityModelTone"
  | "captchaQualityWeeklyModel"
  | "captchaQualityCases"
  | "captchaQualityCaseFilters"
  | "captchaQualityCaseType"
  | "changeCaptchaQualityCaseType"
  | "captchaQualityCaseSummary"
  | "goToCaptchaQualityCasePage"
  | "captchaQualityCasePageNumbers"
>>('DASHBOARD_CAPTCHAS_VIEW_CAPTCHAS');

export const DASHBOARD_CAPTCHAS_VIEW_PRESENTATION = new InjectionToken<Pick<DashboardPresentation,
  "statusLabel"
  | "formatDateTime"
>>('DASHBOARD_CAPTCHAS_VIEW_PRESENTATION');

export const DASHBOARD_FINANCE_VIEW_FINANCE = new InjectionToken<Pick<FinanceFacade,
  "loads" |
  "selectedMonth"
  | "financeLoading"
  | "changeMonth"
  | "openNewFinanceEntry"
  | "financeSummary"
  | "financeConversionComplete"
  | "financeQuality"
  | "financeReviewIssueCount"
  | "monthlySummary"
  | "missingAcquisitionSourceOrders"
  | "selectedMonthLabel"
  | "openEditFinanceEntryById"
  | "financeResolutionLabel"
  | "financeMismatchPaymentId"
  | "startFinanceMismatchResolution"
  | "financeMismatchResolution"
  | "financeMismatchReason"
  | "cancelFinanceMismatchResolution"
  | "requestReconcileFinancePayment"
  | "financeMonthClosure"
  | "financeClosureOpeningBalance"
  | "financeClosureClosingBalance"
  | "financeClosureNotes"
  | "financeClosureCanReconcile"
  | "financeSelectedMonthIsClosed"
  | "requestSaveFinanceMonthClosure"
  | "financeEntries"
  | "financeKindLabel"
  | "formatOriginalMoney"
  | "openEditFinanceEntry"
  | "requestVoidFinanceEntry"
>>('DASHBOARD_FINANCE_VIEW_FINANCE');

export const DASHBOARD_FINANCE_VIEW_PRESENTATION = new InjectionToken<Pick<DashboardPresentation,
  "formatMoney"
  | "formatDateTime"
  | "formatDate"
  | "statusTone"
>>('DASHBOARD_FINANCE_VIEW_PRESENTATION');

export const DASHBOARD_FINANCE_VIEW_UI = new InjectionToken<Pick<DashboardUi,
  "actionBusy"
>>('DASHBOARD_FINANCE_VIEW_UI');

export const DASHBOARD_FOLLOWUPS_VIEW_FOLLOWUPS = new InjectionToken<Pick<FollowupsFacade,
  "loads" |
  "appointmentReminderStatus"
  | "postAppointmentPayload"
  | "setPostAppointmentFilter"
  | "choosePostAppointmentSort"
  | "postAppointmentSortDirection"
  | "togglePostAppointmentSortDirection"
  | "postAppointmentOutcomeDetail"
  | "postAppointmentSearch"
  | "setPostAppointmentSearch"
  | "postAppointmentQuickFilters"
  | "postAppointmentFilter"
  | "postAppointmentItems"
  | "paginatedPostAppointmentItems"
  | "postAppointmentItemNumber"
  | "postAppointmentItemLabel"
  | "postAppointmentStageTone"
  | "postAppointmentMessageTone"
  | "isPostAppointmentReviewing"
  | "reviewPostAppointment"
  | "postAppointmentPageStart"
  | "postAppointmentPageEnd"
  | "currentPostAppointmentPage"
  | "postAppointmentTotalPages"
  | "postAppointmentPageSize"
  | "changePostAppointmentPageSize"
  | "goToPostAppointmentPage"
  | "postAppointmentPageNumbers"
>>('DASHBOARD_FOLLOWUPS_VIEW_FOLLOWUPS');

export const DASHBOARD_FOLLOWUPS_VIEW_PRESENTATION = new InjectionToken<Pick<DashboardPresentation,
  "statusLabel"
  | "formatDateTime"
  | "formatDate"
  | "statusTone"
>>('DASHBOARD_FOLLOWUPS_VIEW_PRESENTATION');

export const DASHBOARD_INBOX_VIEW_OPERATIONS = new InjectionToken<Pick<OperationsFacade,
  "loads" |
  "inboxPendingTotal"
  | "inboxAccessCount"
  | "inboxPausedCount"
  | "inboxPaymentCount"
  | "inboxMessageCount"
  | "inboxOrderTasks"
  | "openInboxOrder"
  | "runInboxOrderTask"
  | "openInboxCaptchaReview"
>>('DASHBOARD_INBOX_VIEW_OPERATIONS');

export const DASHBOARD_INBOX_VIEW_UI = new InjectionToken<Pick<DashboardUi,
  "actionBusy"
>>('DASHBOARD_INBOX_VIEW_UI');

export const DASHBOARD_INBOX_VIEW_CAPTCHAS = new InjectionToken<Pick<CaptchasFacade,
  "loads" |
  "captchaShadowEnabled"
  | "captchaReviewTotal"
>>('DASHBOARD_INBOX_VIEW_CAPTCHAS');

export const DASHBOARD_MESSAGE_TEMPLATES_VIEW_MESSAGES = new InjectionToken<Pick<MessagesFacade,
  "loads" |
  "whatsappMessageTemplates"
>>('DASHBOARD_MESSAGE_TEMPLATES_VIEW_MESSAGES');

export const DASHBOARD_MESSAGE_TEMPLATES_VIEW_UI = new InjectionToken<Pick<DashboardUi,
  "formDirty"
>>('DASHBOARD_MESSAGE_TEMPLATES_VIEW_UI');

export const DASHBOARD_MESSAGE_TEMPLATES_VIEW_PRESENTATION = new InjectionToken<Pick<DashboardPresentation,
  "formatDateTime"
>>('DASHBOARD_MESSAGE_TEMPLATES_VIEW_PRESENTATION');

export const DASHBOARD_ORDERS_VIEW_MESSAGES = new InjectionToken<Pick<MessagesFacade,
  "loads" |
  "whatsappSessionBusy"
  | "validateWhatsAppSession"
  | "whatsappSessionState"
  | "openWhatsAppEvidenceTest"
  | "openWhatsAppTest"
  | "canPrepareOrderWhatsApp"
  | "whatsappPreparationHint"
  | "openOrderWhatsApp"
  | "canPreparePostPaymentWhatsApp"
  | "postPaymentWhatsAppHint"
  | "openPostPaymentWhatsApp"
>>('DASHBOARD_ORDERS_VIEW_MESSAGES');

export const DASHBOARD_ORDERS_VIEW_ORDERS = new InjectionToken<Pick<OrdersFacade,
  "loads" |
  "openCreateOrder"
  | "orderPanelOpen"
  | "selectedOrder"
  | "closeOrderPanel"
  | "preflightLabel"
  | "orderNextAction"
  | "runNextOrderAction"
  | "needsProgramResolution"
  | "openProgramResolution"
  | "needsCredentialCorrection"
  | "openEditOrder"
  | "requestOrderValidation"
  | "requestOrderAction"
  | "hasActiveChildOrders"
  | "requestManualSession"
  | "openOrderActions"
  | "orderDetailLoading"
  | "selectedOrderWhatsapp"
  | "selectedOrderDetail"
  | "openSelectedOrderWhatsapp"
  | "copySelectedOrderWhatsapp"
  | "isClosedOrder"
  | "serviceTypeLabel"
  | "servicePriceLabel"
  | "priorityExplanation"
  | "restrictionDaysLabel"
  | "restrictionTimingLabel"
  | "setQuickPriority"
  | "closureDisplay"
  | "selectedOrderChildren"
  | "selectOrder"
  | "selectedOrderId"
  | "orderStatusDisplay"
  | "runRowPrimaryAction"
  | "rowPrimaryActionLabel"
  | "openManualSessionNow"
>>('DASHBOARD_ORDERS_VIEW_ORDERS');

export const DASHBOARD_ORDERS_VIEW_PRESENTATION = new InjectionToken<Pick<DashboardPresentation,
  "statusTone"
  | "statusLabel"
  | "formatDate"
  | "formatTime"
  | "formatDateTime"
>>('DASHBOARD_ORDERS_VIEW_PRESENTATION');

export const DASHBOARD_ORDERS_VIEW_UI = new InjectionToken<Pick<DashboardUi,
  "actionBusy"
  | "copiedLabel"
>>('DASHBOARD_ORDERS_VIEW_UI');

export const DASHBOARD_ORDERS_VIEW_FINANCE = new InjectionToken<Pick<FinanceFacade,
  "loads" |
  "openPayment"
  | "paymentLabel"
  | "paymentAmountLabel"
>>('DASHBOARD_ORDERS_VIEW_FINANCE');

export const DASHBOARD_ORDERS_VIEW_ORDERLIST = new InjectionToken<Pick<OrdersListFacade,
  "orderPageStart"
  | "orderPageEnd"
  | "filteredOrders"
  | "orders"
  | "orderQuickFilters"
  | "orderQuickFilter"
  | "setOrderQuickFilter"
  | "orderFilter"
  | "setOrderFilter"
  | "orderSortKey"
  | "chooseOrderSort"
  | "toggleOrderSortDirection"
  | "orderSortDirection"
  | "orderAriaSort"
  | "setOrderSort"
  | "sortIndicator"
  | "paginatedOrders"
  | "hasReservationRestrictions"
  | "currentOrderPage"
  | "orderTotalPages"
  | "orderPageSize"
  | "changeOrderPageSize"
  | "goToOrderPage"
  | "orderPageNumbers"
>>('DASHBOARD_ORDERS_VIEW_ORDERLIST');

export const DASHBOARD_RUNS_VIEW_OPERATIONS = new InjectionToken<Pick<OperationsFacade,
  "loads" |
  "workerCommands"
  | "runStatusFilter"
  | "runStatuses"
  | "selectedRunId"
  | "closeRunDetail"
  | "runDetailState"
  | "runDetailError"
  | "selectRun"
  | "selectedRun"
  | "runResultLabel"
  | "runEvidencePaths"
  | "filteredRuns"
>>('DASHBOARD_RUNS_VIEW_OPERATIONS');

export const DASHBOARD_RUNS_VIEW_PRESENTATION = new InjectionToken<Pick<DashboardPresentation,
  "statusTone"
  | "statusLabel"
  | "formatDateTime"
>>('DASHBOARD_RUNS_VIEW_PRESENTATION');

export const DASHBOARD_SUMMARY_VIEW_FINANCE = new InjectionToken<Pick<FinanceFacade,
  "loads" |
  "selectedMonth"
  | "monthlyLoading"
  | "changeMonth"
  | "monthlySummary"
  | "metricPeriodLabel"
  | "monthlyRevenueComparison"
  | "dailyRevenueWidth"
  | "selectedMonthLabel"
  | "closedMonthRevenueComparison"
  | "paymentLabel"
>>('DASHBOARD_SUMMARY_VIEW_FINANCE');

export const DASHBOARD_SUMMARY_VIEW_FOLLOWUPS = new InjectionToken<Pick<FollowupsFacade,
  "loads" |
  "appointmentReminderStatus"
>>('DASHBOARD_SUMMARY_VIEW_FOLLOWUPS');

export const DASHBOARD_SUMMARY_VIEW_PRESENTATION = new InjectionToken<Pick<DashboardPresentation,
  "formatDate"
  | "statusLabel"
  | "formatMoney"
  | "formatDateTime"
  | "formatTime"
  | "statusTone"
>>('DASHBOARD_SUMMARY_VIEW_PRESENTATION');

export const DASHBOARD_SUMMARY_VIEW_OPERATIONS = new InjectionToken<Pick<OperationsFacade,
  "loads" |
  "openOrderFromSummary"
  | "openPaymentFromSummary"
  | "health"
  | "worker"
  | "phaseLabel"
  | "showPendingPayments"
  | "currentWorkLabel"
  | "currentOrder"
  | "generalObserverActive"
  | "pendingWorkerControl"
  | "requestWorkerPauseToggle"
  | "openWorkerRestart"
  | "opportunityControlTone"
  | "opportunityControlLabel"
  | "opportunityMaxSessions"
  | "opportunityControl"
  | "opportunityBreakerOpen"
  | "opportunityReasonLabel"
  | "requestResetOpportunityBreaker"
  | "opportunityModeTone"
  | "opportunityModeLabel"
  | "opportunityActionDisabled"
  | "requestOpportunityContextAction"
  | "opportunityActionLabel"
  | "latestOpportunityBurst"
  | "copyDashboardSnapshot"
  | "filteredRuns"
  | "failedRuns"
>>('DASHBOARD_SUMMARY_VIEW_OPERATIONS');

export const DASHBOARD_SUMMARY_VIEW_ORDERLIST = new InjectionToken<Pick<OrdersListFacade,
  "readyOrders"
  | "filteredOrders"
  | "pendingPaymentOrders"
  | "confirmedOrders"
>>('DASHBOARD_SUMMARY_VIEW_ORDERLIST');

export const DASHBOARD_SUMMARY_VIEW_CAPTCHAS = new InjectionToken<Pick<CaptchasFacade,
  "loads" |
  "captchaShadowEnabled"
  | "captchaSamplingEnabled"
  | "captchaAuthorityUsesV6"
  | "captchaSamplingEffectiveLimit"
  | "setCaptchaSamplingEnabled"
  | "captchaSamplingSaving"
  | "captchaSamplingLimit"
  | "setCaptchaSamplingLimit"
  | "captchaSamplingEstimatedSeconds"
  | "captchaAuthorityControl"
  | "requestCaptchaAuthorityFallback"
  | "requestCaptchaAuthorityCanary"
  | "captchaSamplingControl"
  | "captchaSamplingDirty"
  | "saveCaptchaSamplingControl"
>>('DASHBOARD_SUMMARY_VIEW_CAPTCHAS');

export const DASHBOARD_SUMMARY_VIEW_UI = new InjectionToken<Pick<DashboardUi,
  "actionBusy"
  | "copiedLabel"
>>('DASHBOARD_SUMMARY_VIEW_UI');

export const DASHBOARD_SUMMARY_VIEW_NAVIGATION = new InjectionToken<Pick<DashboardNavigation,
  "loadState"
>>('DASHBOARD_SUMMARY_VIEW_NAVIGATION');

export const DASHBOARD_SHELL_NAVIGATION = new InjectionToken<Pick<DashboardNavigation,
  "sidebarCollapsed"
  | "mobileMenuOpen"
  | "activeView"
  | "toggleSidebar"
  | "activeViewGroup"
  | "activeViewLabel"
  | "refreshingViewState"
  | "pageHidden"
  | "autoRefreshPaused"
  | "lastUpdatedAt"
  | "refreshNow"
  | "activeViewState"
  | "viewLoadError"
  | "handleVisibilityChange"
>>('DASHBOARD_SHELL_NAVIGATION');

export const DASHBOARD_SHELL_OPERATIONS = new InjectionToken<Pick<OperationsFacade,
  "loads" |
  "inboxPendingTotal"
  | "health"
  | "worker"
>>('DASHBOARD_SHELL_OPERATIONS');

export const DASHBOARD_SHELL_FINANCE = new InjectionToken<Pick<FinanceFacade,
  "loads" |
  "selectedMonth"
>>('DASHBOARD_SHELL_FINANCE');

export const DASHBOARD_SHELL_CAPTCHAS = new InjectionToken<Pick<CaptchasFacade,
  "loads" |
  "captchaShadowEnabled"
  | "captchaWorkspaceMode"
  | "handleCaptchaReviewKeyboard"
>>('DASHBOARD_SHELL_CAPTCHAS');

export const DASHBOARD_SHELL_UI = new InjectionToken<Pick<DashboardUi,
  "errorMessage"
  | "formDirty"
  | "activeModal"
  | "handleEscape"
>>('DASHBOARD_SHELL_UI');

export const DASHBOARD_SHELL_ORDERS = new InjectionToken<Pick<OrdersFacade,
  "loads" |
  "manualSessions"
  | "manualSessionOrderLabel"
  | "manualSessionTypeLabel"
  | "isManualSessionClosing"
  | "closeManualSession"
  | "handleBeforeUnload"
>>('DASHBOARD_SHELL_ORDERS');

export const DASHBOARD_SHELL_PRESENTATION = new InjectionToken<Pick<DashboardPresentation,
  "statusLabel"
  | "statusTone"
  | "formatDateTime"
>>('DASHBOARD_SHELL_PRESENTATION');

export const DASHBOARD_DOMAIN_VIEW_TOKENS = [DASHBOARD_SUMMARY_VIEW_ORDERS, DASHBOARD_CREATE_ORDER_MODAL_UI, DASHBOARD_CREATE_ORDER_MODAL_ORDERS, DASHBOARD_CREATE_ORDER_MODAL_PRESENTATION, DASHBOARD_EDIT_ORDER_MODAL_UI, DASHBOARD_EDIT_ORDER_MODAL_ORDERS, DASHBOARD_EDIT_ORDER_MODAL_PRESENTATION, DASHBOARD_EDIT_ORDER_MODAL_FINANCE, DASHBOARD_FINANCE_ENTRY_MODAL_UI, DASHBOARD_FINANCE_ENTRY_MODAL_FINANCE, DASHBOARD_FINANCE_ENTRY_MODAL_ORDERLIST, DASHBOARD_ORDER_ACTIONS_MODAL_UI, DASHBOARD_ORDER_ACTIONS_MODAL_ORDERS, DASHBOARD_ORDER_ACTIONS_MODAL_PRESENTATION, DASHBOARD_PAYMENT_MODAL_UI, DASHBOARD_PAYMENT_MODAL_ORDERS, DASHBOARD_PAYMENT_MODAL_PRESENTATION, DASHBOARD_PAYMENT_MODAL_FINANCE, DASHBOARD_WHATSAPP_MODAL_UI, DASHBOARD_WHATSAPP_MODAL_MESSAGES, DASHBOARD_WHATSAPP_MODAL_PRESENTATION, DASHBOARD_WORKER_RESTART_MODAL_UI, DASHBOARD_WORKER_RESTART_MODAL_OPERATIONS, DASHBOARD_PROGRAM_RESOLUTION_PANEL_ORDERS, DASHBOARD_PROGRAM_RESOLUTION_PANEL_UI, DASHBOARD_CAPTCHAS_VIEW_CAPTCHAS, DASHBOARD_CAPTCHAS_VIEW_PRESENTATION, DASHBOARD_FINANCE_VIEW_FINANCE, DASHBOARD_FINANCE_VIEW_PRESENTATION, DASHBOARD_FINANCE_VIEW_UI, DASHBOARD_FOLLOWUPS_VIEW_FOLLOWUPS, DASHBOARD_FOLLOWUPS_VIEW_PRESENTATION, DASHBOARD_INBOX_VIEW_OPERATIONS, DASHBOARD_INBOX_VIEW_UI, DASHBOARD_INBOX_VIEW_CAPTCHAS, DASHBOARD_MESSAGE_TEMPLATES_VIEW_MESSAGES, DASHBOARD_MESSAGE_TEMPLATES_VIEW_UI, DASHBOARD_MESSAGE_TEMPLATES_VIEW_PRESENTATION, DASHBOARD_ORDERS_VIEW_MESSAGES, DASHBOARD_ORDERS_VIEW_ORDERS, DASHBOARD_ORDERS_VIEW_PRESENTATION, DASHBOARD_ORDERS_VIEW_UI, DASHBOARD_ORDERS_VIEW_FINANCE, DASHBOARD_ORDERS_VIEW_ORDERLIST, DASHBOARD_RUNS_VIEW_OPERATIONS, DASHBOARD_RUNS_VIEW_PRESENTATION, DASHBOARD_SUMMARY_VIEW_FINANCE, DASHBOARD_SUMMARY_VIEW_FOLLOWUPS, DASHBOARD_SUMMARY_VIEW_PRESENTATION, DASHBOARD_SUMMARY_VIEW_OPERATIONS, DASHBOARD_SUMMARY_VIEW_ORDERLIST, DASHBOARD_SUMMARY_VIEW_CAPTCHAS, DASHBOARD_SUMMARY_VIEW_UI, DASHBOARD_SUMMARY_VIEW_NAVIGATION] as const;
