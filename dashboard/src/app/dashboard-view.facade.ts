import { InjectionToken } from '@angular/core';

// Transitional facade while view-specific inputs and outputs are narrowed.
// The parent remains the single owner of operational state and side effects.
export type DashboardViewFacade = any;

export const DASHBOARD_VIEW_FACADE = new InjectionToken<DashboardViewFacade>(
  'DASHBOARD_VIEW_FACADE',
);
