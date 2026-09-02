import { HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { AppointmentApiService, apiErrorMessage } from './appointment-api.service';

describe('AppointmentApiService sensitive contracts', () => {
  let api: AppointmentApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    api = TestBed.inject(AppointmentApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('creates an order with the exact POST body', async () => {
    const payload = {
      document_number: '12345678', document_type: 'dni' as const, password: 'secret',
      contact_name: 'Cliente', contact_source: 'whatsapp', reservation_price: '50.00',
    };
    const response = api.createServiceOrder(payload);
    const request = http.expectOne('/api/v1/service-orders');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual(payload);
    request.flush({ status: 'created' });
    await expect(response).resolves.toMatchObject({ status: 'created' });
  });

  it.each([
    ['markPaymentPaid', '/payment/paid'],
    ['recordPartialPayment', '/payment/partial'],
  ] as const)('encodes order ids for %s', async (method, suffix) => {
    const payload = { amount_paid: '25.00', amount_agreed: '50.00' };
    const response = api[method]('order/with space', payload);
    const request = http.expectOne(`/api/v1/service-orders/order%2Fwith%20space${suffix}`);
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual(payload);
    request.flush({ status: 'ok' });
    await response;
  });

  it('posts credentials and WhatsApp preparation without changing their bodies', async () => {
    const credentials = { document_number: '123', document_type: 'dni' as const, password: 'new' };
    const credentialResponse = api.updateServiceOrderCredentials('a/b', credentials);
    const credentialRequest = http.expectOne('/api/v1/service-orders/a%2Fb/credentials');
    expect(credentialRequest.request.body).toEqual(credentials);
    credentialRequest.flush({ status: 'ok' });
    await credentialResponse;

    const whatsappResponse = api.prepareOrderWhatsApp('a/b', true);
    const whatsappRequest = http.expectOne('/api/v1/service-orders/a%2Fb/whatsapp/prepare');
    expect(whatsappRequest.request.method).toBe('POST');
    expect(whatsappRequest.request.body).toEqual({ allow_resend: true });
    whatsappRequest.flush({ message_id: 'm1' });
    await whatsappResponse;
  });

  it('posts one explicit restart command and exposes 409 details', async () => {
    const response = api.restartWorker(false);
    const request = http.expectOne('/api/v1/worker/restart');
    expect(request.request.body).toEqual({ release_safe_backoffs: false });
    request.flush({ message: 'Hay una sesión manual activa.' }, { status: 409, statusText: 'Conflict' });
    await expect(response).rejects.toBeInstanceOf(HttpErrorResponse);

    expect(apiErrorMessage(new HttpErrorResponse({
      status: 409,
      error: { message: 'Hay una sesión manual activa.' },
    }))).toBe('409 Hay una sesión manual activa.');
  });
});
