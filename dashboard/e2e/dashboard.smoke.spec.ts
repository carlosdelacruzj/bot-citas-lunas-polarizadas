import { expect, test } from '@playwright/test';

test('navigates locally and surfaces one controlled 409 without side effects', async ({ page }) => {
  let restartRequests = 0;
  const unexpectedMutations: string[] = [];

  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === '/health') {
      await route.fulfill({ json: {
        status: 'ok', message: 'API simulada para smoke test', worker_running: true,
        reason: 'running', captcha_shadow_enabled: false,
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
    const responses: Record<string, unknown> = {
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
      '/api/v1/service-orders': { service_orders: [] },
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
});
