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
const loadFollowupsView = () =>
  import('./views/followups-view/followups-view.component').then(
    (module) => module.FollowupsViewComponent,
  );
const loadMessageTemplatesView = () =>
  import('./views/message-templates-view/message-templates-view.component').then(
    (module) => module.MessageTemplatesViewComponent,
  );

export const routes: Routes = [
  { path: 'pendientes', title: 'Pendientes', loadComponent: loadInboxView },
  { path: 'resumen', title: 'Resumen', loadComponent: loadSummaryView },
  { path: 'ordenes', title: 'Órdenes', loadComponent: loadOrdersView },
  { path: 'ordenes/:orderId', title: 'Detalle de orden', loadComponent: loadOrdersView },
  { path: 'actividad', title: 'Actividad', loadComponent: loadRunsView },
  { path: 'actividad/:runId', title: 'Detalle de actividad', loadComponent: loadRunsView },
  { path: 'seguimiento', title: 'Seguimiento', loadComponent: loadFollowupsView },
  { path: 'post-cita', pathMatch: 'full', redirectTo: 'seguimiento' },
  { path: 'finanzas', title: 'Finanzas', loadComponent: loadFinanceView },
  {
    path: 'mensajes',
    title: 'Mensajes de WhatsApp',
    loadComponent: loadMessageTemplatesView,
  },
  { path: 'captchas', title: 'Control de CAPTCHA', loadComponent: loadCaptchasView },
  { path: '', pathMatch: 'full', redirectTo: 'resumen' },
  { path: '**', redirectTo: 'resumen' },
];
