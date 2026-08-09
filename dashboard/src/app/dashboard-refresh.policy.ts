export type RefreshableDashboardView =
  | 'inbox'
  | 'summary'
  | 'finance'
  | 'orders'
  | 'followups'
  | 'runs'
  | 'captchas';

export type CaptchaRefreshMode = 'review' | 'history' | 'quality';

const VIEW_INTERVALS_MS: Record<Exclude<RefreshableDashboardView, 'captchas'>, number> = {
  inbox: 10_000,
  runs: 10_000,
  orders: 20_000,
  followups: 60_000,
  summary: 60_000,
  finance: 120_000,
};

const CAPTCHA_INTERVALS_MS: Record<CaptchaRefreshMode, number> = {
  review: 20_000,
  history: 60_000,
  quality: 60_000,
};

export function dashboardRefreshInterval(
  view: RefreshableDashboardView,
  captchaMode: CaptchaRefreshMode = 'review',
): number {
  return view === 'captchas' ? CAPTCHA_INTERVALS_MS[captchaMode] : VIEW_INTERVALS_MS[view];
}

export function dashboardDataExpired(
  lastSuccessfulAt: number | null,
  intervalMs: number,
  now = Date.now(),
): boolean {
  return lastSuccessfulAt === null || now - lastSuccessfulAt >= intervalMs;
}
