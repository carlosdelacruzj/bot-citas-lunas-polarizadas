import { expect, test } from '@playwright/test';
import domainResponses from '../src/app/api/testing/navigation.fixture';
import { orderDetailFixture, orderListItemFixture } from '../src/app/api/testing/sensitive-contract.fixtures';

test('navigates locally and surfaces one controlled 409 without side effects', async ({ page }) => {
  let restartRequests = 0;
  const unexpectedMutations: string[] = [];
  const runtimeErrors: string[] = [];
  const cancelledRequests: string[] = [];
  let detailRequests = 0;
  let releaseOldDetail!: () => void;
  const oldDetailGate = new Promise<void>((resolve) => { releaseOldDetail = resolve; });
  let delayedSummary = false;
  let summaryHeld = false;
  let releaseSummary!: () => void;
  const summaryGate = new Promise<void>((resolve) => { releaseSummary = resolve; });
  page.on('pageerror', (error) => runtimeErrors.push(error.message));
  page.on('requestfailed', (request) => cancelledRequests.push(new URL(request.url()).pathname));

  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === '/health') {
      await route.fulfill({ json: {
        status: 'ok', message: 'API simulada para smoke test', worker_running: true,
        reason: 'running', captcha_shadow_enabled: true,
      } });
      return;
    }
    if (!url.pathname.startsWith('/api/')) {
      await route.continue();
      return;
    }
    if (request.method() !== 'GET') {
      if (url.pathname === '/api/v1/worker/restart' && request.method() === 'POST') {
        restartRequests += 1;
        await route.fulfill({
          status: 409,
          contentType: 'application/json',
          body: JSON.stringify({ code: 'manual_session_active', message: 'Hay una sesión manual activa.' }),
        });
        return;
      }
      unexpectedMutations.push(`${request.method()} ${url.pathname}`);
      await route.fulfill({ status: 500, json: { message: 'Mutación no permitida en smoke test.' } });
      return;
    }
    if (url.pathname === '/api/v1/service-orders/synthetic-a') {
      detailRequests++;
      if (detailRequests === 1) {
        await oldDetailGate;
        await route.fulfill({ status: 503, json: { message: 'Detalle anterior fuera de orden' } }).catch(() => undefined);
      } else {
        await route.fulfill({ json: { ...orderDetailFixture, order_id: 'synthetic-a', contact_whatsapp: 'A-actual' } });
      }
      return;
    }
    if (url.pathname === '/api/v1/service-orders/synthetic-b') {
      await route.fulfill({ json: { ...orderDetailFixture, order_id: 'synthetic-b', contact_whatsapp: 'B-actual' } });
      return;
    }
    if (url.pathname === '/api/v1/finance/data-quality') {
      await route.fulfill({ status: 503, json: { message: 'Calidad temporalmente no disponible' } });
      return;
    }
    if (url.pathname === '/api/v2/monthly-summary' && delayedSummary) {
      delayedSummary = false;
      summaryHeld = true;
      await summaryGate;
      await route.fulfill({ json: domainResponses['/api/v2/monthly-summary'] }).catch(() => undefined);
      return;
    }
    const responses: Record<string, unknown> = {
      ...domainResponses,
      '/api/v1/worker': { worker_running: true, phase: 'monitoring' },
      '/api/v1/manual-sessions': { manual_sessions: [] },
      '/api/v1/service-packages': {
        default_package: 'standard',
        service_packages: [{
          key: 'standard', label: 'Servicio regular', total_amount: '50.00',
          initial_payment_amount: '0.00', official_fee_amount: '0.00',
          balance_amount: '50.00', management_fee_amount: '50.00', fixed_price: true,
          default_service_type: 'standard', compatible_service_types: ['standard'],
          requires_restrictions: false,
        }],
      },
      '/api/v1/service-orders': { service_orders: [
        { ...orderListItemFixture, order_id: 'synthetic-a', applicant_name: 'Cliente A' },
        { ...orderListItemFixture, order_id: 'synthetic-b', applicant_name: 'Cliente B' },
      ] },
      '/api/v1/runs': { runs: [] },
      '/api/v1/worker/commands': { commands: [] },
    };
    const body = responses[url.pathname];
    await route.fulfill({
      status: body === undefined ? 404 : 200,
      json: body ?? { message: `Fixture no definido: ${url.pathname}` },
    });
  });

  await page.goto('/ordenes');
  await expect(page.getByRole('heading', { name: 'Ordenes', exact: true })).toBeVisible();
  await page.locator('[data-order-row="synthetic-a"]').click();
  await expect.poll(() => detailRequests).toBe(1);
  await page.locator('[data-order-panel]').getByRole('button', { name: 'Cerrar', exact: true }).click();
  await page.locator('[data-order-row="synthetic-b"]').click();
  await expect(page.locator('[data-order-panel]')).toContainText('B-actual');
  await page.locator('[data-order-panel]').getByRole('button', { name: 'Cerrar', exact: true }).click();
  await page.locator('[data-order-row="synthetic-a"]').click();
  await expect(page.locator('[data-order-panel]')).toContainText('A-actual');
  releaseOldDetail();
  await expect.poll(() => cancelledRequests.includes('/api/v1/service-orders/synthetic-a')).toBe(true);
  await expect(page.locator('[data-order-panel]')).toContainText('A-actual');
  await expect(page.getByText('Detalle anterior fuera de orden', { exact: false })).toHaveCount(0);
  await page.locator('[data-order-panel]').getByRole('button', { name: 'Cerrar', exact: true }).click();
  await expect(page).toHaveURL(/\/ordenes$/);
  await page.locator('input[name="orderFilter"]').fill('consulta local');
  await expect(page.locator('input[name="orderFilter"]')).toBeFocused();
  await expect(page.locator('[data-order-row]')).toHaveCount(0);
  for (const [route, component] of [
    ['pendientes', 'app-inbox-view'],
    ['resumen', 'app-summary-view'],
    ['finanzas', 'app-finance-view'],
    ['mensajes', 'app-message-templates-view'],
    ['seguimiento', 'app-followups-view'],
    ['captchas', 'app-captchas-view'],
    ['ordenes', 'app-orders-view'],
  ]) {
    await page.locator(`nav a[href^="/${route}"]`).click();
    await expect(page.locator(component)).toBeVisible();
    if (route === 'finanzas') {
      await expect(page.getByText('Ingresos cobrados', { exact: true })).toBeVisible();
      await expect(page.locator('app-load-status').filter({ hasText: 'Calidad financiera:' })).toContainText('Calidad temporalmente no disponible');
      await expect(page.locator('app-load-status').filter({ hasText: 'Calidad financiera:' })).toBeVisible();
      await expect(page.locator('app-load-status').filter({ hasText: 'Resumen financiero:' })).toContainText('Actualizado el');
    }
  }
  await expect(page.locator('input[name="orderFilter"]')).toHaveValue('consulta local');
  delayedSummary = true;
  await page.locator('nav a[href^="/resumen"]').click();
  await expect.poll(() => summaryHeld).toBe(true);
  await page.locator('nav a[href^="/mensajes"]').click();
  await expect(page.locator('app-message-templates-view')).toBeVisible();
  releaseSummary();
  await expect.poll(() => cancelledRequests.includes('/api/v2/monthly-summary')).toBe(true);
  await expect(page).toHaveURL(/\/mensajes$/);
  await page.getByRole('link', { name: 'Actividad' }).click();
  await expect(page).toHaveURL(/\/actividad$/);
  await expect(page.getByRole('heading', { name: 'Comandos worker' })).toBeVisible();

  const conflict = await page.evaluate(async () => {
    const response = await fetch('/api/v1/worker/restart', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ release_safe_backoffs: false }),
    });
    return { status: response.status, body: await response.json() };
  });

  expect(conflict).toEqual({
    status: 409,
    body: { code: 'manual_session_active', message: 'Hay una sesión manual activa.' },
  });
  expect(restartRequests).toBe(1);
  expect(unexpectedMutations).toEqual([]);
  expect(runtimeErrors).toEqual([]);
});
