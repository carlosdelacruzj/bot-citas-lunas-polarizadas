import type {
  CreateServiceOrderPayload,
  ExcludedDateRange,
  PaymentPaidPayload,
} from './appointment-api.service';
import type { ServicePackageDefinition, ServicePackageKey } from './service-package.model';

export interface CreateOrderFormValues {
  documentNumber: string;
  documentType: CreateServiceOrderPayload['document_type'];
  password: string;
  contactWhatsapp: string;
  contactWhatsappUsername: string;
  contactName: string;
  contactSource: string;
  servicePackage: ServicePackageKey;
  customReservationPrice: string | number;
  minimumReservationDate: string;
  maximumReservationDate: string;
  allowedWeekdays: number[];
  excludedDateRanges: ExcludedDateRange[];
}

export type PayloadResult<T> = { payload: T; error: null } | { payload: null; error: string };

const optionalText = (value: string): string | null => value.trim() || null;

export function buildCreateOrderPayload(
  values: CreateOrderFormValues,
  packageDefinition: ServicePackageDefinition | null,
): PayloadResult<CreateServiceOrderPayload> {
  if (!packageDefinition || packageDefinition.key !== values.servicePackage) {
    return { payload: null, error: 'El catálogo comercial no está disponible. Actualiza la vista.' };
  }
  const customPrice = Number(values.customReservationPrice);
  if (!packageDefinition.fixed_price && (!Number.isFinite(customPrice) || customPrice <= 0 || customPrice > 99999.99)) {
    return { payload: null, error: 'Ingresa un precio personalizado válido mayor que cero.' };
  }
  const reservationPrice = packageDefinition.fixed_price
    ? packageDefinition.total_amount
    : customPrice.toFixed(2);
  if (!reservationPrice) {
    return { payload: null, error: 'El paquete seleccionado no tiene un precio válido.' };
  }
  const payload: CreateServiceOrderPayload = {
    document_number: values.documentNumber.trim(),
    document_type: values.documentType,
    password: values.password,
    contact_whatsapp: optionalText(values.contactWhatsapp),
    contact_whatsapp_username: optionalText(values.contactWhatsappUsername),
    contact_name: values.contactName.trim(),
    contact_source: values.contactSource,
    service_type: packageDefinition.default_service_type,
    service_package: values.servicePackage,
    reservation_price: reservationPrice,
    minimum_reservation_date: optionalText(values.minimumReservationDate),
    maximum_reservation_date: optionalText(values.maximumReservationDate),
    allowed_weekdays: values.allowedWeekdays.length > 0 ? [...values.allowedWeekdays] : null,
    excluded_date_ranges: [...values.excludedDateRanges],
  };
  if (payload.minimum_reservation_date && payload.maximum_reservation_date && payload.maximum_reservation_date < payload.minimum_reservation_date) {
    return { payload: null, error: 'La fecha final no puede ser anterior a la fecha inicial.' };
  }
  if (packageDefinition.requires_restrictions && (!payload.minimum_reservation_date || !payload.maximum_reservation_date)) {
    return { payload: null, error: 'La disponibilidad restringida exige una fecha inicial y una fecha final.' };
  }
  if (packageDefinition.requires_restrictions && !payload.allowed_weekdays?.length && !payload.excluded_date_ranges?.length) {
    return { payload: null, error: 'Indica días permitidos o fechas excluidas para delimitar la disponibilidad restringida.' };
  }
  if (!payload.document_number || !payload.document_type || !payload.password || !payload.contact_name || !payload.contact_source) {
    return { payload: null, error: 'Usuario, contraseña, contacto y fuente son obligatorios.' };
  }
  return { payload, error: null };
}

export function buildPaymentPayload(
  amountPaid: string | number | null,
  amountAgreed: string | number | null,
  current: Pick<PaymentPaidPayload, 'expected_payment_status' | 'expected_amount_agreed' | 'expected_amount_paid'>,
): PayloadResult<PaymentPaidPayload> {
  const paidText = String(amountPaid ?? '').trim();
  const agreedText = String(amountAgreed ?? '').trim();
  if (!paidText) {
    return { payload: null, error: 'Ingresa el monto pagado.' };
  }
  const paid = Number(paidText);
  if (!Number.isFinite(paid) || paid <= 0) {
    return { payload: null, error: 'El total pagado debe ser mayor que cero.' };
  }
  return {
    payload: {
      amount_paid: paidText,
      amount_agreed: optionalText(agreedText),
      ...current,
    },
    error: null,
  };
}
