import { HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { LoadSection } from '../load-section';
import { RequestCancelledError, RequestScope } from '../request-cancellation';

import { FinanceApiClient } from './finance/finance-api.client';
import { MessagesApiClient } from './messages/messages-api.client';
import { OperationsApiClient } from './operations/operations-api.client';
import { OrdersApiClient } from './orders/orders-api.client';
import { apiErrorMessage } from './shared/api-error';
import {
  actionFixture,
  createdFixture,
  createOrderFixture,
  credentialsFixture,
  orderDetailFixture,
  orderListItemFixture,
  paymentFixture,
  whatsappPackageFixture,
} from './testing/sensitive-contract.fixtures';

describe('Domain API sensitive contracts', () => {
  let orders: OrdersApiClient;
  let finance: FinanceApiClient;
  let messages: MessagesApiClient;
  let operations: OperationsApiClient;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    orders = TestBed.inject(OrdersApiClient);
    finance = TestBed.inject(FinanceApiClient);
    messages = TestBed.inject(MessagesApiClient);
    operations = TestBed.inject(OperationsApiClient);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('creates an order with the exact POST body', async () => {
    const payload = createOrderFixture;
    const response = orders.createServiceOrder(payload);
    const request = http.expectOne('/api/v1/service-orders');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual(payload);
    request.flush(createdFixture);
    await expect(response).resolves.toMatchObject({ status: 'created' });

    const list = orders.getServiceOrders();
    http.expectOne('/api/v1/service-orders?projection=dashboard')
      .flush({ service_orders: [orderListItemFixture] });
    const [item] = await list;
    expect(item).not.toHaveProperty('document_number');
    expect(item).not.toHaveProperty('contact_whatsapp');
    expect(item).not.toHaveProperty('password');

    const detail = orders.getServiceOrder('order/with space');
    http.expectOne('/api/v1/service-orders/order%2Fwith%20space').flush(orderDetailFixture);
    await expect(detail).resolves.toEqual(orderDetailFixture);

    const parent = new RequestScope();
    const child = parent.fork();
    const cancelled = orders.getServiceOrder('cancelled-order', child);
    const pending = http.expectOne('/api/v1/service-orders/cancelled-order');
    parent.cancel();
    expect(pending.cancelled).toBe(true);
    await expect(cancelled).rejects.toBeInstanceOf(RequestCancelledError);

    const section = new LoadSection('Detalle');
    const scope = new RequestScope();
    let rejectOld!: (reason: Error) => void;
    let finishCurrent!: (value: string) => void;
    let published = '';
    const old = section.load(scope, () => new Promise<string>((_resolve, reject) => { rejectOld = reject; }), value => { published = value; });
    const current = section.load(scope, () => new Promise<string>((resolve) => { finishCurrent = resolve; }), value => { published = value; });
    rejectOld(new Error('Error anterior'));
    await old;
    expect(section.error()).toBeNull();
    expect(section.loading()).toBe(true);
    finishCurrent('Actual');
    await current;
    expect(published).toBe('Actual');
    expect(section.loading()).toBe(false);
    const updatedAt = section.updatedAt();
    await section.load(scope, () => Promise.reject(new Error('Fallo actual')), value => { published = value; });
    expect(section.error()).toBe('Fallo actual');
    expect(section.updatedAt()).toBe(updatedAt);
    expect(published).toBe('Actual');
    scope.cancel();
    const cancelledScope = new RequestScope();
    let finishCancelled!: (value: string) => void;
    const late = section.load(cancelledScope,
      () => new Promise<string>((resolve) => { finishCancelled = resolve; }),
      value => { published = value; });
    cancelledScope.cancel();
    finishCancelled('Respuesta cancelada');
    await late;
    expect(published).toBe('Actual');
    expect(section.updatedAt()).toBe(updatedAt);
  });

  it.each([
    ['markPaymentPaid', '/payment/paid'],
    ['recordPartialPayment', '/payment/partial'],
  ] as const)('encodes order ids for %s', async (method, suffix) => {
    const payload = paymentFixture;
    const response = finance[method]('order/with space', payload);
    const request = http.expectOne(`/api/v1/service-orders/order%2Fwith%20space${suffix}`);
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual(payload);
    request.flush(actionFixture);
    await response;
  });

  it('posts credentials and WhatsApp preparation without changing their bodies', async () => {
    const credentials = credentialsFixture;
    const credentialResponse = orders.updateServiceOrderCredentials('a/b', credentials);
    const credentialRequest = http.expectOne('/api/v1/service-orders/a%2Fb/credentials');
    expect(credentialRequest.request.body).toEqual(credentials);
    credentialRequest.flush(actionFixture);
    await credentialResponse;

    const whatsappResponse = messages.prepareOrderWhatsApp('a/b', true);
    const whatsappRequest = http.expectOne('/api/v1/service-orders/a%2Fb/whatsapp/prepare');
    expect(whatsappRequest.request.method).toBe('POST');
    expect(whatsappRequest.request.body).toEqual({ allow_resend: true });
    whatsappRequest.flush(whatsappPackageFixture);
    await expect(whatsappResponse).resolves.toEqual(whatsappPackageFixture);
  });

  it('posts one explicit restart command and exposes 409 details', async () => {
    const response = operations.restartWorker(false);
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
