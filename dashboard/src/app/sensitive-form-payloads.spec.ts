import { describe, expect, it } from 'vitest';

import type { ServicePackageDefinition } from './service-package.model';
import { buildCreateOrderPayload, buildPaymentPayload } from './sensitive-form-payloads';

const packageDefinition = (
  overrides: Partial<ServicePackageDefinition> = {},
): ServicePackageDefinition => ({
  key: 'standard',
  label: 'Servicio regular',
  total_amount: '50.00',
  initial_payment_amount: '0.00',
  official_fee_amount: '0.00',
  balance_amount: '50.00',
  management_fee_amount: '50.00',
  fixed_price: true,
  default_service_type: 'standard',
  compatible_service_types: ['standard'],
  requires_restrictions: false,
  ...overrides,
});

const validForm = () => ({
  documentNumber: ' 12345678 ',
  documentType: 'dni' as const,
  password: 'secret',
  contactWhatsapp: ' +51999999999 ',
  contactWhatsappUsername: ' ',
  contactName: ' Cliente ',
  contactSource: 'whatsapp',
  servicePackage: 'standard' as const,
  customReservationPrice: '',
  minimumReservationDate: '',
  maximumReservationDate: '',
  allowedWeekdays: [] as number[],
  excludedDateRanges: [],
});

describe('sensitive form payloads', () => {
  it('builds a normalized standard order payload without inventing optional values', () => {
    const result = buildCreateOrderPayload(validForm(), packageDefinition());

    expect(result.error).toBeNull();
    expect(result.payload).toMatchObject({
      document_number: '12345678',
      contact_name: 'Cliente',
      contact_whatsapp: '+51999999999',
      contact_whatsapp_username: null,
      service_type: 'standard',
      service_package: 'standard',
      reservation_price: '50.00',
      allowed_weekdays: null,
    });
  });

  it('preserves the integral package amounts from the catalog', () => {
    const form = { ...validForm(), servicePackage: 'integral' as const };
    const result = buildCreateOrderPayload(form, packageDefinition({
      key: 'integral',
      label: 'Trámite integral',
      total_amount: '160.00',
      initial_payment_amount: '80.00',
      official_fee_amount: '71.40',
      balance_amount: '80.00',
      management_fee_amount: '88.60',
    }));

    expect(result.payload?.reservation_price).toBe('160.00');
    expect(result.payload?.service_package).toBe('integral');
  });

  it('requires a bounded and explicit rule for restricted availability', () => {
    const definition = packageDefinition({
      key: 'restricted',
      total_amount: '70.00',
      default_service_type: 'selected_weekday',
      compatible_service_types: ['selected_weekday'],
      requires_restrictions: true,
    });
    const missingWindow = buildCreateOrderPayload(
      { ...validForm(), servicePackage: 'restricted' },
      definition,
    );
    const valid = buildCreateOrderPayload({
      ...validForm(),
      servicePackage: 'restricted',
      minimumReservationDate: '2026-09-01',
      maximumReservationDate: '2026-09-30',
      allowedWeekdays: [6],
    }, definition);

    expect(missingWindow.error).toContain('fecha inicial');
    expect(valid.payload).toMatchObject({
      service_type: 'selected_weekday',
      reservation_price: '70.00',
      allowed_weekdays: [6],
    });
  });

  it('formats custom prices and rejects reversed date ranges', () => {
    const definition = packageDefinition({
      key: 'custom',
      total_amount: null,
      fixed_price: false,
      default_service_type: 'custom',
      compatible_service_types: ['custom'],
    });
    const custom = buildCreateOrderPayload(
      { ...validForm(), servicePackage: 'custom', customReservationPrice: '82.5' },
      definition,
    );
    const reversed = buildCreateOrderPayload({
      ...validForm(),
      minimumReservationDate: '2026-10-01',
      maximumReservationDate: '2026-09-01',
    }, packageDefinition());

    expect(custom.payload?.reservation_price).toBe('82.50');
    expect(reversed.error).toContain('fecha final');
  });

  it('builds an optimistic payment payload and rejects non-positive totals', () => {
    const result = buildPaymentPayload('25.00', '50.00', {
      expected_payment_status: 'pending',
      expected_amount_agreed: '50.00',
      expected_amount_paid: '10.00',
    });

    expect(result.payload).toEqual({
      amount_paid: '25.00',
      amount_agreed: '50.00',
      expected_payment_status: 'pending',
      expected_amount_agreed: '50.00',
      expected_amount_paid: '10.00',
    });
    expect(buildPaymentPayload('0', '50', {}).error).toContain('mayor que cero');
  });
});
