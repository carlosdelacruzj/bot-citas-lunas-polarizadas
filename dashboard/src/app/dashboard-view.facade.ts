import { InjectionToken } from '@angular/core';
import type { App } from './app';

export type DashboardViewFacade = App;

export const DASHBOARD_VIEW_FACADE = new InjectionToken<DashboardViewFacade>(
  'DASHBOARD_VIEW_FACADE',
);
