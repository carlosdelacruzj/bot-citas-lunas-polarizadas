import { Routes } from '@angular/router';

const loadInboxView = () =>
  import('./views/inbox-view/inbox-view.component').then((module) => module.InboxViewComponent);
const loadSummaryView = () =>
  import('./views/summary-view/summary-view.component').then(
    (module) => module.SummaryViewComponent,
  );
const loadOrdersView = () =>
  import('./views/orders-view/orders-view.component').then((module) => module.OrdersViewComponent);
const loadRunsView = () =>
  import('./views/runs-view/runs-view.component').then((module) => module.RunsViewComponent);
const loadFinanceView = () =>
  import('./views/finance-view/finance-view.component').then(
    (module) => module.FinanceViewComponent,
  );
const loadCaptchasView = () =>
  import('./views/captchas-view/captchas-view.component').then(
    (module) => module.CaptchasViewComponent,
  );

export const routes: Routes = [
  { path: 'pendientes', title: 'Pendientes', loadComponent: loadInboxView },
  { path: 'resumen', title: 'Resumen', loadComponent: loadSummaryView },
  { path: 'ordenes', title: 'Órdenes', loadComponent: loadOrdersView },
  { path: 'ordenes/:orderId', title: 'Detalle de orden', loadComponent: loadOrdersView },
  { path: 'actividad', title: 'Actividad', loadComponent: loadRunsView },
  { path: 'actividad/:runId', title: 'Detalle de actividad', loadComponent: loadRunsView },
  { path: 'finanzas', title: 'Finanzas', loadComponent: loadFinanceView },
  { path: 'captchas', title: 'Control de CAPTCHA', loadComponent: loadCaptchasView },
  { path: '', pathMatch: 'full', redirectTo: 'pendientes' },
  { path: '**', redirectTo: 'pendientes' },
];
