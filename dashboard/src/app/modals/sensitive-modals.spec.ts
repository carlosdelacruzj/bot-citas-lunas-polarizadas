import { signal, type WritableSignal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { DASHBOARD_VIEW_FACADE, type DashboardViewFacade } from '../dashboard-view.facade';
import { CreateOrderModalComponent } from './create-order-modal.component';
import { EditOrderModalComponent } from './edit-order-modal.component';
import { PaymentModalComponent } from './payment-modal.component';
import { WhatsappModalComponent } from './whatsapp-modal.component';

const servicePackage = {
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
};

function fakeView(activeModal: string): Record<string, unknown> {
  const values: Record<string, unknown> = {
    activeModal: signal(activeModal),
    actionBusy: signal(false),
    formDirty: signal(false),
    newDocumentType: signal('dni'),
    newDocumentNumber: signal('12345678'),
    newPassword: signal('secret'),
    newContactName: signal('Cliente'),
    newContactWhatsapp: signal(''),
    newContactWhatsappUsername: signal(''),
    newContactSource: signal('whatsapp'),
    newServicePackage: signal('standard'),
    newCustomReservationPrice: signal(''),
    newMinimumReservationDate: signal(''),
    newMaximumReservationDate: signal(''),
    newAllowedWeekdays: signal([]),
    newExcludedDateRanges: signal([]),
    newExcludedDateStart: signal(''),
    newExcludedDateEnd: signal(''),
    servicePackages: vi.fn(() => [servicePackage]),
    newServicePackageDefinition: vi.fn(() => servicePackage),
    servicePackageOptionLabel: vi.fn(() => 'Servicio regular — S/50.00'),
    formatMoney: vi.fn((amount: number) => `S/${amount.toFixed(2)}`),
    closeModal: vi.fn(),
    requestCreateOrder: vi.fn(),
    editField: vi.fn(),
    addNewExcludedDateRange: vi.fn(),
    removeNewExcludedDateRange: vi.fn(),
    clearNewExcludedDateRanges: vi.fn(),
  };
  return new Proxy(values, {
    get(target, property: string) {
      if (!(property in target)) {
        target[property] = vi.fn(() => null);
      }
      return target[property];
    },
  });
}

async function render<T>(component: { new(): T }, view: Record<string, unknown>) {
  await TestBed.configureTestingModule({
    imports: [component],
    providers: [{ provide: DASHBOARD_VIEW_FACADE, useValue: view as unknown as DashboardViewFacade }],
  }).compileComponents();
  const fixture = TestBed.createComponent(component);
  fixture.detectChanges();
  return fixture;
}

describe('sensitive dashboard modals', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('renders create-order and delegates create and cancel explicitly', async () => {
    const view = fakeView('create-order');
    const fixture = await render(CreateOrderModalComponent, view);
    const buttons = [...fixture.nativeElement.querySelectorAll('button')] as HTMLButtonElement[];

    buttons.find((button) => button.textContent?.includes('Crear orden'))?.click();
    buttons.find((button) => button.textContent?.includes('Cancelar'))?.click();

    expect(view['requestCreateOrder']).toHaveBeenCalledOnce();
    expect(view['closeModal']).toHaveBeenCalledOnce();
  });

  it('disables payment submission until an accumulated total exists', async () => {
    const view = fakeView('payment');
    view['modalOrder'] = vi.fn(() => ({
      order_id: 'order-1', amount_paid: '10.00', amount_agreed: '50.00',
      reservation_date: null, reservation_hour: null, service_package: 'standard',
    }));
    view['paymentAmountAgreed'] = signal('50.00');
    view['paymentAmountPaid'] = signal('');
    view['standardPackageAmount'] = vi.fn(() => '50.00');
    view['requestMarkPaid'] = vi.fn();
    const fixture = await render(PaymentModalComponent, view);
    const submit = [...fixture.nativeElement.querySelectorAll('button')]
      .find((button: HTMLButtonElement) => button.textContent?.includes('Registrar total')) as HTMLButtonElement;

    expect(submit.disabled).toBe(true);
    (view['paymentAmountPaid'] as WritableSignal<string>).set('50.00');
    fixture.detectChanges();
    submit.click();
    expect(view['requestMarkPaid']).toHaveBeenCalledOnce();
  });

  it('keeps credential submission disabled without the replacement password', async () => {
    const view = fakeView('edit-order');
    view['modalOrder'] = vi.fn(() => ({
      order_id: 'order-1', status: 'paused', reservation_status: null,
      payment_status: 'pending', amount_paid: '0.00', amount_agreed: '50.00',
      preflight_status: 'validated', priority: 0, charge_required: true,
    }));
    view['editOrderSection'] = signal('credentials');
    view['orderDetailLoading'] = signal(false);
    view['orderDocumentType'] = signal('dni');
    view['orderDocumentNumber'] = signal('12345678');
    view['orderPassword'] = signal('');
    view['orderPasswordVisible'] = signal(false);
    view['isClosedOrder'] = vi.fn(() => false);
    view['requestCredentialsUpdate'] = vi.fn();
    const fixture = await render(EditOrderModalComponent, view);
    const submit = [...fixture.nativeElement.querySelectorAll('button')]
      .find((button: HTMLButtonElement) => button.textContent?.includes('Guardar y validar')) as HTMLButtonElement;

    expect(submit.disabled).toBe(true);
    (view['orderPassword'] as WritableSignal<string>).set('replacement');
    fixture.detectChanges();
    submit.click();
    expect(view['requestCredentialsUpdate']).toHaveBeenCalledOnce();
  });

  it('prepares WhatsApp only after the operator presses the explicit button', async () => {
    const view = fakeView('whatsapp');
    view['whatsappTestMode'] = signal(true);
    view['whatsappReviewMode'] = signal(false);
    view['whatsappFollowUpMode'] = signal(false);
    view['whatsappPackage'] = signal(null);
    view['whatsappFollowUpPackage'] = signal(null);
    view['whatsappReview'] = signal(null);
    view['whatsappTestRecipient'] = signal('+51999999999');
    view['whatsappFollowUpLoading'] = signal(false);
    view['whatsappPackageLoading'] = signal(false);
    view['prepareWhatsAppTest'] = vi.fn();
    const fixture = await render(WhatsappModalComponent, view);
    const button = [...fixture.nativeElement.querySelectorAll('button')]
      .find((item: HTMLButtonElement) => item.textContent?.includes('Crear prueba')) as HTMLButtonElement;

    expect(view['prepareWhatsAppTest']).not.toHaveBeenCalled();
    button.click();
    expect(view['prepareWhatsAppTest']).toHaveBeenCalledOnce();
  });
});
