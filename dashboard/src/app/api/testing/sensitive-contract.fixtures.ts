import type { PaymentPaidPayload } from '../finance/finance.contracts';
import type { WhatsAppMessagePackage } from '../messages/messages.contracts';
import type {
  CreateServiceOrderPayload,
  CredentialsUpdatePayload,
  ServiceOrder,
  ServiceOrderDetail,
} from '../orders/orders.contracts';
import type { ApiActionResponse } from '../shared/shared.contracts';

export const createOrderFixture = {
  document_number: '12345678', document_type: 'dni', password: 'synthetic-password',
  contact_name: 'Cliente de prueba', contact_source: 'whatsapp', reservation_price: '50.00',
} satisfies CreateServiceOrderPayload;

export const credentialsFixture = {
  document_number: '123', document_type: 'dni', password: 'synthetic-replacement',
} satisfies CredentialsUpdatePayload;

export const paymentFixture = {
  amount_paid: '25.00', amount_agreed: '50.00',
} satisfies PaymentPaidPayload;

export const createdFixture = { status: 'created', order_id: 'synthetic-order' } satisfies ApiActionResponse;
export const actionFixture = { status: 'ok' } satisfies ApiActionResponse;

export const orderListItemFixture = {
  order_id: 'synthetic-order', applicant_id: 'synthetic-applicant',
  applicant_name: 'Cliente de prueba', document_number_masked: '****5678', document_type: 'dni',
  contact_name: null, contact_whatsapp_masked: null, contact_whatsapp_username_masked: null,
  contact_source: 'whatsapp', priority: 0, charge_required: true, service_type: 'standard',
  reservation_price: '50.00', service_package: 'standard', official_fee_amount: '0.00',
  initial_payment_amount: '0.00', status: 'paused', reservation_status: null,
  reservation_site: null, reservation_date: null, reservation_hour: null, payment_status: null,
  amount_agreed: null, amount_paid: null, whatsapp_message_status: null,
  whatsapp_message_sent_at: null, whatsapp_message_action_state: 'not_applicable',
  whatsapp_followup_status: null, whatsapp_followup_action_state: 'not_applicable',
  parent_order_id: null, program_expediente: null, program_plate: null, closure_reason: null,
  closure_note: null, closed_at: null, minimum_reservation_date: null,
  maximum_reservation_date: null, allowed_weekdays: null, excluded_date_ranges: [],
  preflight_status: 'pending', preflight_message: null, preflight_error_type: null,
  registration_notice_type: null, registration_notice_status: null, registration_notice_error: null,
  created_at: '2026-09-08T10:00:00-05:00', updated_at: '2026-09-08T10:00:00-05:00',
} satisfies ServiceOrder;

export const orderDetailFixture = {
  ...orderListItemFixture, document_number: '12345678', contact_whatsapp: null,
  contact_whatsapp_username: null, preflight_details: null,
} satisfies ServiceOrderDetail;

export const whatsappPackageFixture = {
  message_id: 'm1', order_id: 'synthetic-order', test_mode: true, status: 'prepared',
  recipient_phone: null, recipient_phone_masked: null, recipient_username: null,
  recipient_label: 'Destinatario de prueba', greeting: 'Texto sintetico', evidence_caption: '',
  payment_message: '', whatsapp_url: null, attachment_url: '/synthetic/evidence.png',
  payment_attachment_url: '/synthetic/payment.png', confirmation_template_key: null,
  confirmation_template_revision: null, payment_template_key: null, payment_template_revision: null,
  prepared_at: '2026-09-08T10:00:00-05:00', sent_at: null,
} satisfies WhatsAppMessagePackage;
