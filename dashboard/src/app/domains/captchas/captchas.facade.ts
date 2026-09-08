import { Injectable, Injector, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import {
  AppointmentApiService,
  CaptchaAuthorityControl,
  CaptchaEvent,
  CaptchaEventsPage,
  CaptchaPrediction,
  CaptchaQuality,
  CaptchaQualityCase,
  CaptchaQualityCaseType,
  CaptchaQualityCasesPage,
  CaptchaQualityModel,
  CaptchaQualityWeek,
  CaptchaSamplingControl,
  CaptchaSummary,
} from '../../appointment-api.service';
import {
  CAPTCHA_QUALITY_CASE_FILTERS,
  CaptchaAgreementFilter,
  CaptchaPendingCorrection,
  CaptchaPortalFilter,
  CaptchaPredictionOption,
  CaptchaReviewFilter,
  CaptchaSourceFilter,
  CaptchaWorkspaceMode,
  LoadState,
} from '../../dashboard-domain.contracts';
import { DASHBOARD_CAPTCHAS_SHELL } from '../../dashboard-domain.ports';
import { paginationWindow } from '../../pagination';
import { RequestScope, isRequestCancelled } from '../../request-cancellation';

@Injectable()
export class CaptchasFacade {
  private readonly injector = inject(Injector);
  private readonly api = inject(AppointmentApiService);
  private readonly router = inject(Router);

  public captchaLoadScope: RequestScope | null = null;

  public captchaQualityCaseScope: RequestScope | null = null;

  public captchaReviewMessageTimer: number | null = null;

  public readonly captchaAuthorityControl = signal<CaptchaAuthorityControl | null>(null);

  public readonly captchaSamplingControl = signal<CaptchaSamplingControl | null>(null);

  public readonly captchaSamplingEnabled = signal(false);

  public readonly captchaSamplingLimit = signal(10);

  public readonly captchaSamplingDirty = signal(false);

  public readonly captchaSamplingSaving = signal(false);

  public readonly captchaSummary = signal<CaptchaSummary | null>(null);

  public readonly captchaEvents = signal<CaptchaEvent[]>([]);

  public readonly captchaReviewQueue = signal<CaptchaEvent[]>([]);

  public readonly captchaReviewTotal = signal(0);

  public readonly captchaPendingTotal = signal(0);

  public readonly captchaReviewPosition = signal(0);

  public readonly captchaWorkspaceMode = signal<CaptchaWorkspaceMode>('review');

  public readonly captchaHistoryFiltersOpen = signal(false);

  public readonly captchaState = signal<LoadState>('idle');

  public readonly captchaError = signal<string | null>(null);

  public readonly captchaPage = signal(1);

  public readonly captchaPageSize = signal(12);

  public readonly captchaTotal = signal(0);

  public readonly captchaTotalPages = signal(1);

  public readonly captchaSearch = signal('');

  public readonly captchaAgreement = signal<CaptchaAgreementFilter>('all');

  public readonly captchaPortalStatus = signal<CaptchaPortalFilter>('all');

  public readonly captchaSource = signal<CaptchaSourceFilter>('all');

  public readonly captchaReviewStatus = signal<CaptchaReviewFilter>('all');

  public readonly captchaDrafts = signal<Record<string, string>>({});

  public readonly captchaSavingEventId = signal('');

  public readonly captchaReviewMessage = signal<string | null>(null);

  public readonly captchaPendingCorrection = signal<CaptchaPendingCorrection | null>(null);

  public readonly captchaShadowEnabled = computed(
    () => this.shell.health()?.captcha_shadow_enabled === true,
  );

  public readonly captchaQuality = signal<CaptchaQuality | null>(null);

  public readonly captchaQualityCases = signal<CaptchaQualityCasesPage | null>(null);

  public readonly captchaQualityState = signal<LoadState>('idle');

  public readonly captchaQualityError = signal<string | null>(null);

  public readonly captchaQualityCaseType = signal<CaptchaQualityCaseType>('wrong');

  public readonly captchaQualityCasePage = signal(1);

  public readonly captchaQualityCasePageSize = signal(12);

  public readonly captchaDatasetExporting = signal(false);

  public readonly captchaQualityCaseFilters = CAPTCHA_QUALITY_CASE_FILTERS;

  public readonly activeCaptchaReview = computed(
    () => this.captchaReviewQueue()[this.captchaReviewPosition()] ?? null,
  );

  public readonly captchaPageNumbers = computed(() => {
    return paginationWindow(this.captchaPage(), this.captchaTotalPages());
  });

  public readonly captchaQualityBestModel = computed<CaptchaQualityModel | null>(() => {
    return [...(this.captchaQuality()?.models ?? [])]
      .filter((model) => model.accuracy !== null)
      .sort(
        (left, right) =>
          (right.accuracy ?? 0) - (left.accuracy ?? 0) || right.evaluated - left.evaluated,
      )[0] ?? null;
  });

  public readonly captchaQualityCasePageNumbers = computed(() => {
    const pagination = this.captchaQualityCases()?.pagination;
    return pagination ? paginationWindow(pagination.page, pagination.total_pages) : [];
  });

  public readonly captchaSamplingEffectiveLimit = computed(() =>
    this.captchaSamplingEnabled() ? this.captchaSamplingLimit() : 1,
  );

  public readonly captchaSamplingEstimatedSeconds = computed(() =>
    Math.round(Math.max(this.captchaSamplingEffectiveLimit() - 1, 0) * 4) / 10,
  );

  public readonly captchaAuthorityUsesV6 = computed(() => {
    const control = this.captchaAuthorityControl();
    return Boolean(
      control?.mode === 'canary' &&
        control.circuit_state === 'closed' &&
        control.remaining_local_decisions > 0,
    );
  });

  public handleCaptchaReviewKeyboard(event: KeyboardEvent): void {
    if (
      this.shell.activeView() !== 'captchas' ||
      this.captchaWorkspaceMode() !== 'review' ||
      event.ctrlKey ||
      event.metaKey ||
      event.altKey
    ) {
      return;
    }
    const target = event.target as HTMLElement | null;
    if (target?.matches('input, textarea, select, button')) {
      return;
    }
    if (event.key === 'ArrowRight') {
      this.moveCaptchaReview(1);
      return;
    }
    if (event.key === 'ArrowLeft') {
      this.moveCaptchaReview(-1);
      return;
    }
    const captcha = this.activeCaptchaReview();
    if (!captcha || this.captchaSavingEventId()) {
      return;
    }
    const options = this.captchaPredictionOptions(captcha);
    const optionIndex = Number(event.key) - 1;
    if (Number.isInteger(optionIndex) && optionIndex >= 0 && options[optionIndex]) {
      event.preventDefault();
      void this.chooseCaptchaPrediction(captcha, options[optionIndex].answer);
      return;
    }
    if (event.key === 'Enter' && this.captchaChoiceMode(captcha) === 'consensus') {
      event.preventDefault();
      void this.chooseCaptchaPrediction(captcha, options[0].answer);
    }
  }

  public async loadCaptchaData(showLoading = true, scope?: RequestScope): Promise<void> {
    const ownsScope = !scope;
    if (ownsScope) {
      this.captchaLoadScope?.cancel();
      this.captchaLoadScope = new RequestScope();
    }
    const activeScope = scope ?? this.captchaLoadScope!;
    if (showLoading) {
      this.captchaState.set('loading');
    }
    this.captchaError.set(null);
    try {
      if (this.captchaWorkspaceMode() === 'quality') {
        const [summary] = await Promise.all([
          this.api.getCaptchaSummary(activeScope),
          this.loadCaptchaQuality(activeScope),
        ]);
        this.captchaSummary.set(summary);
        this.captchaPendingTotal.set(
          Math.max(0, summary.stats.events - summary.stats.human_labeled),
        );
        this.captchaState.set('ready');
        return;
      }
      const [summary, page, reviewPage] = await Promise.all([
        this.api.getCaptchaSummary(activeScope),
        this.api.getCaptchaEvents(
          this.captchaPage(),
          this.captchaPageSize(),
          this.captchaSearch().trim(),
          this.captchaAgreement(),
          this.captchaPortalStatus(),
          this.captchaSource(),
          this.captchaReviewStatus(),
          'newest',
          'all',
          activeScope,
        ),
        this.api.getCaptchaEvents(
          1, 48, '', 'all', 'all', 'all', 'pending', 'review_priority', 'targeted', activeScope,
        ),
      ]);
      this.captchaSummary.set(summary);
      this.captchaPendingTotal.set(
        Math.max(0, summary.stats.events - summary.stats.human_labeled),
      );
      this.applyCaptchaPage(page);
      this.captchaReviewQueue.set(reviewPage.events);
      this.captchaReviewTotal.set(reviewPage.pagination.total);
      if (this.captchaReviewPosition() >= reviewPage.events.length) {
        this.captchaReviewPosition.set(0);
      }
      this.captchaState.set('ready');
    } catch (error) {
      if (isRequestCancelled(error)) {
        return;
      }
      this.captchaState.set('error');
      this.captchaError.set(this.shell.readError(error));
    } finally {
      if (ownsScope && this.captchaLoadScope === activeScope) {
        this.captchaLoadScope = null;
      }
    }
  }

  public async loadCaptchaQuality(scope?: RequestScope): Promise<void> {
    if (!this.captchaQuality()) {
      this.captchaQualityState.set('loading');
    }
    this.captchaQualityError.set(null);
    try {
      const [quality, cases] = await Promise.all([
        this.api.getCaptchaQuality(scope),
        this.api.getCaptchaQualityCases(
          this.captchaQualityCaseType(),
          this.captchaQualityCasePage(),
          this.captchaQualityCasePageSize(),
          scope,
        ),
      ]);
      this.captchaQuality.set(quality);
      this.applyCaptchaQualityCases(cases);
      this.captchaQualityState.set('ready');
    } catch (error) {
      if (isRequestCancelled(error)) {
        return;
      }
      this.captchaQualityState.set('error');
      this.captchaQualityError.set(this.shell.readError(error));
    }
  }

  public async changeCaptchaQualityCaseType(value: CaptchaQualityCaseType): Promise<void> {
    if (value === this.captchaQualityCaseType()) {
      return;
    }
    this.captchaQualityCaseType.set(value);
    this.captchaQualityCasePage.set(1);
    await this.loadCaptchaQualityCases();
  }

  public async goToCaptchaQualityCasePage(page: number): Promise<void> {
    const pagination = this.captchaQualityCases()?.pagination;
    if (!pagination || page < 1 || page > pagination.total_pages || page === pagination.page) {
      return;
    }
    this.captchaQualityCasePage.set(page);
    await this.loadCaptchaQualityCases();
  }

  private async loadCaptchaQualityCases(): Promise<void> {
    this.captchaQualityCaseScope?.cancel();
    const scope = new RequestScope();
    this.captchaQualityCaseScope = scope;
    this.captchaQualityError.set(null);
    try {
      const cases = await this.api.getCaptchaQualityCases(
        this.captchaQualityCaseType(),
        this.captchaQualityCasePage(),
        this.captchaQualityCasePageSize(),
        scope,
      );
      this.applyCaptchaQualityCases(cases);
    } catch (error) {
      if (!isRequestCancelled(error)) {
        this.captchaQualityError.set(this.shell.readError(error));
      }
    } finally {
      if (this.captchaQualityCaseScope === scope) {
        this.captchaQualityCaseScope = null;
      }
    }
  }

  private applyCaptchaQualityCases(cases: CaptchaQualityCasesPage): void {
    this.captchaQualityCases.set(cases);
    this.captchaQualityCasePage.set(cases.pagination.page);
    this.captchaQualityCasePageSize.set(cases.pagination.page_size);
  }

  public async exportCaptchaDataset(): Promise<void> {
    if (this.captchaDatasetExporting()) {
      return;
    }
    this.captchaDatasetExporting.set(true);
    this.captchaQualityError.set(null);
    try {
      const archive = await this.api.downloadCaptchaDataset();
      const url = URL.createObjectURL(archive);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = 'captcha-human-validated-dataset.zip';
      anchor.hidden = true;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
    } catch (error) {
      this.captchaQualityError.set(this.shell.readError(error));
    } finally {
      this.captchaDatasetExporting.set(false);
    }
  }

  public async applyCaptchaFilters(): Promise<void> {
    this.captchaPage.set(1);
    await this.loadCaptchaData();
  }

  public async setCaptchaAgreement(filter: CaptchaAgreementFilter): Promise<void> {
    if (this.captchaAgreement() === filter) {
      return;
    }
    this.captchaAgreement.set(filter);
    await this.applyCaptchaFilters();
  }

  public async changeCaptchaPortalStatus(value: CaptchaPortalFilter): Promise<void> {
    this.captchaPortalStatus.set(value);
    await this.applyCaptchaFilters();
  }

  public async changeCaptchaSource(value: CaptchaSourceFilter): Promise<void> {
    this.captchaSource.set(value);
    await this.applyCaptchaFilters();
  }

  public async changeCaptchaReviewStatus(value: CaptchaReviewFilter): Promise<void> {
    this.captchaReviewStatus.set(value);
    await this.applyCaptchaFilters();
  }

  public showCaptchaWorkspace(mode: CaptchaWorkspaceMode): void {
    const changed = this.captchaWorkspaceMode() !== mode;
    this.captchaWorkspaceMode.set(mode);
    this.captchaPendingCorrection.set(null);
    this.clearCaptchaReviewMessage();
    this.shell.scheduleNextRefresh();
    if (this.shell.activeView() === 'captchas') {
      void this.router.navigate([], {
        queryParams: { mode },
        queryParamsHandling: 'merge',
        replaceUrl: true,
      });
      if (changed) {
        void this.loadCaptchaData(mode === 'quality');
      }
    }
  }

  public showAllPendingCaptchas(): void {
    this.captchaReviewStatus.set('pending');
    this.captchaPage.set(1);
    this.showCaptchaWorkspace('history');
  }

  public toggleCaptchaHistoryFilters(): void {
    this.captchaHistoryFiltersOpen.update((open) => !open);
  }

  public captchaActiveFilterCount(): number {
    return (
      Number(this.captchaAgreement() !== 'all') +
      Number(this.captchaPortalStatus() !== 'all') +
      Number(this.captchaSource() !== 'all')
    );
  }

  public moveCaptchaReview(offset: number): void {
    const next = this.captchaReviewPosition() + offset;
    if (next < 0 || next >= this.captchaReviewQueue().length) {
      return;
    }
    this.captchaReviewPosition.set(next);
    this.captchaPendingCorrection.set(null);
    this.clearCaptchaReviewMessage();
  }

  public async changeCaptchaPageSize(value: number | string): Promise<void> {
    this.captchaPageSize.set(Number(value));
    await this.applyCaptchaFilters();
  }

  public async goToCaptchaPage(page: number): Promise<void> {
    if (page < 1 || page > this.captchaTotalPages() || page === this.captchaPage()) {
      return;
    }
    this.captchaPage.set(page);
    await this.loadCaptchaData();
  }

  public captchaPrediction(event: CaptchaEvent, modelName: string): CaptchaPrediction | null {
    return event.predictions.find((prediction) => prediction.model_name === modelName) ?? null;
  }

  public captchaPredictionTone(event: CaptchaEvent, prediction: CaptchaPrediction): string {
    const reference = event.human_label?.answer ?? event.external_answer;
    if (!reference) {
      return 'neutral';
    }
    return prediction.prediction === reference ? 'good' : 'warn';
  }

  public captchaPortalLabel(event: CaptchaEvent): string {
    if (this.isObserverCaptcha(event)) {
      return 'Portal no aplica';
    }
    if (event.portal_accepted === true) {
      return 'Aceptado por el portal';
    }
    if (event.portal_accepted === false) {
      return 'CAPTCHA rechazado';
    }
    return 'Sin validar por el portal';
  }

  public captchaPortalTone(event: CaptchaEvent): string {
    if (event.portal_accepted === true) {
      return 'good';
    }
    if (event.portal_accepted === false) {
      return 'bad';
    }
    return 'neutral';
  }

  public captchaAgreementLabel(event: CaptchaEvent): string {
    if (this.isObserverCaptcha(event)) {
      return event.predictions.length ? 'Solo modelos locales' : 'Inferencia pendiente';
    }
    if (
      !event.external_answer ||
      !event.selected_model_name ||
      !this.captchaPrediction(event, event.selected_model_name)
    ) {
      return 'Comparación pendiente';
    }
    return event.selected_matches_external ? 'Coincide con 2Captcha' : 'Difiere de 2Captcha';
  }

  public captchaAgreementTone(event: CaptchaEvent): string {
    if (this.isObserverCaptcha(event)) {
      return event.predictions.length ? 'good' : 'neutral';
    }
    if (
      !event.external_answer ||
      !event.selected_model_name ||
      !this.captchaPrediction(event, event.selected_model_name)
    ) {
      return 'neutral';
    }
    return event.selected_matches_external ? 'good' : 'warn';
  }

  public formatMilliseconds(value: number | null | undefined): string {
    if (value === null || value === undefined || !Number.isFinite(value)) {
      return 'Sin dato';
    }
    return value >= 1000 ? `${(value / 1000).toFixed(3)} s` : `${value.toFixed(3)} ms`;
  }

  public formatConfidence(value: number | null | undefined): string {
    if (value === null || value === undefined || !Number.isFinite(value)) {
      return 'Sin dato';
    }
    return `${(value * 100).toFixed(1)}%`;
  }

  public captchaQualityAccuracy(value: number | null | undefined): string {
    return this.formatConfidence(value);
  }

  public captchaQualityModelTone(model: CaptchaQualityModel): string {
    if (model.accuracy === null || model.evaluated < 10) {
      return 'neutral';
    }
    if (model.accuracy >= 0.95) {
      return 'good';
    }
    return model.accuracy >= 0.85 ? 'warn' : 'bad';
  }

  public captchaQualityCaseSummary(item: CaptchaQualityCase): string {
    if (item.case_types.includes('unanimous_wrong')) {
      return 'Todos los modelos coincidieron en una respuesta incorrecta.';
    }
    if (item.case_types.includes('majority_wrong')) {
      return 'La respuesta apoyada por la mayoría fue incorrecta.';
    }
    if (item.case_types.includes('high_confidence_wrong')) {
      return 'Al menos un modelo falló con confianza alta.';
    }
    if (item.case_types.includes('disagreement')) {
      return 'Los modelos no produjeron la misma respuesta.';
    }
    return 'Al menos un modelo difiere de la validación humana.';
  }

  public captchaQualityWeeklyModel(week: CaptchaQualityWeek, modelName: string) {
    return week.models[modelName] ?? null;
  }

  public captchaOrderLabel(event: CaptchaEvent): string {
    if (this.isObserverCaptcha(event)) {
      return `Observador · muestra ${event.metadata.attempt ?? '?'} de 15`;
    }
    return event.metadata.order_id || (event.metadata.run_id ? 'Observador' : 'Sin orden');
  }

  public isObserverCaptcha(event: CaptchaEvent): boolean {
    return event.metadata.observer === 1 || event.metadata.observer === true;
  }

  public captchaLocalTotalMs(event: CaptchaEvent): number | null {
    if (!event.predictions.length) {
      return null;
    }
    return event.predictions.reduce((total, prediction) => total + prediction.inference_ms, 0);
  }

  public captchaDraft(event: CaptchaEvent): string {
    return this.captchaDrafts()[event.event_id] ?? event.human_label?.answer ?? '';
  }

  public updateCaptchaDraft(eventId: string, value: string): void {
    const normalized = value
      .toUpperCase()
      .replace(/[^A-Z0-9]/g, '')
      .slice(0, 5);
    this.captchaDrafts.update((drafts) => ({ ...drafts, [eventId]: normalized }));
    this.clearCaptchaReviewMessage();
  }

  public captchaPredictionOptions(event: CaptchaEvent): CaptchaPredictionOption[] {
    const groups = new Map<string, string[]>();
    for (const prediction of event.predictions) {
      const models = groups.get(prediction.prediction) ?? [];
      groups.set(prediction.prediction, [...models, prediction.model_name]);
    }
    return [...groups.entries()]
      .map(([answer, modelNames]) => ({ answer, modelNames }))
      .sort(
        (left, right) =>
          right.modelNames.length - left.modelNames.length ||
          left.answer.localeCompare(right.answer),
      );
  }

  public captchaChoiceMode(
    event: CaptchaEvent,
  ): 'consensus' | 'majority' | 'plurality' | 'manual' {
    const options = this.captchaPredictionOptions(event);
    if (event.predictions.length >= 2 && options.length === 1) {
      return 'consensus';
    }
    const leadingVotes = options[0]?.modelNames.length ?? 0;
    if (leadingVotes > event.predictions.length / 2) {
      return 'majority';
    }
    if (leadingVotes >= 2) {
      return 'plurality';
    }
    return 'manual';
  }

  public captchaChoiceLabel(event: CaptchaEvent): string {
    const mode = this.captchaChoiceMode(event);
    if (mode === 'consensus') {
      return 'Consenso';
    }
    if (mode === 'majority') {
      const leadingVotes = this.captchaPredictionOptions(event)[0]?.modelNames.length ?? 0;
      return `Mayoría ${leadingVotes}–${event.predictions.length - leadingVotes}`;
    }
    if (mode === 'plurality') {
      return 'Coincidencia parcial';
    }
    return event.predictions.length ? `${event.predictions.length} respuestas` : 'Sin consenso';
  }

  public captchaReviewReasonLabel(event: CaptchaEvent): string {
    const labels: Record<string, string> = {
      canary_v6: 'Canario V6',
      anomaly: 'Anomalía',
      model_disagreement: 'Desacuerdo V3/V6',
      control_sample: 'Muestra de control',
    };
    return labels[event.review_priority_reason ?? ''] ?? 'Revisión dirigida';
  }

  public captchaModelLabel(modelName: string): string {
    return (
      {
        v1_real: 'v1 original',
        v2_scratch: 'v2 desde cero',
        v2_selected: 'v2 seleccionado',
        v3_selected: 'v3 seleccionado',
        v4_candidate: 'v4 histórico',
        v5_candidate: 'v5 histórico',
        v6_sequence_candidate: 'v6 secuencial',
      }[modelName] ?? modelName
    );
  }

  public captchaSourceLabel(event: CaptchaEvent): string {
    return this.isObserverCaptcha(event) ? 'Observador' : 'Reserva';
  }

  public captchaSuggestionTone(event: CaptchaEvent, answer: string): string {
    if (!event.human_label) {
      return 'neutral';
    }
    return event.human_label.answer === answer ? 'good' : 'bad';
  }

  public async chooseCaptchaPrediction(event: CaptchaEvent, answer: string): Promise<void> {
    this.updateCaptchaDraft(event.event_id, answer);
    await this.requestCaptchaHumanLabel(event, answer);
  }

  public async saveCaptchaHumanLabel(event: CaptchaEvent): Promise<void> {
    await this.requestCaptchaHumanLabel(event, this.captchaDraft(event));
  }

  public pendingCaptchaCorrection(eventId: string): CaptchaPendingCorrection | null {
    const correction = this.captchaPendingCorrection();
    return correction?.eventId === eventId ? correction : null;
  }

  public async confirmCaptchaCorrection(event: CaptchaEvent): Promise<void> {
    const correction = this.pendingCaptchaCorrection(event.event_id);
    if (!correction) {
      return;
    }
    await this.persistCaptchaHumanLabel(event, correction.nextAnswer);
  }

  public cancelCaptchaCorrection(event: CaptchaEvent): void {
    this.captchaPendingCorrection.set(null);
    this.updateCaptchaDraft(event.event_id, event.human_label?.answer ?? '');
  }

  private async requestCaptchaHumanLabel(event: CaptchaEvent, answer: string): Promise<void> {
    if (!/^[A-Z0-9]{5}$/.test(answer)) {
      this.showCaptchaReviewMessage('Escribe exactamente cinco letras o números.', 5_000);
      return;
    }
    const currentAnswer = event.human_label?.answer;
    if (currentAnswer === answer) {
      this.captchaPendingCorrection.set(null);
      this.showCaptchaReviewMessage(`La respuesta ${answer} ya está validada.`);
      return;
    }
    if (currentAnswer) {
      this.captchaPendingCorrection.set({
        eventId: event.event_id,
        previousAnswer: currentAnswer,
        nextAnswer: answer,
      });
      return;
    }
    await this.persistCaptchaHumanLabel(event, answer);
  }

  private async persistCaptchaHumanLabel(event: CaptchaEvent, answer: string): Promise<void> {
    this.captchaSavingEventId.set(event.event_id);
    this.captchaPendingCorrection.set(null);
    this.clearCaptchaReviewMessage();
    try {
      const response = await this.api.saveCaptchaHumanLabel(
        event.event_id,
        event.image_sha256,
        answer,
      );
      this.showCaptchaReviewMessage(`Respuesta ${answer} guardada para entrenamiento.`);
      if (this.captchaWorkspaceMode() === 'review' || this.captchaReviewStatus() === 'pending') {
        this.captchaReviewPosition.set(0);
        await this.loadCaptchaData(false);
      } else {
        this.captchaEvents.update((events) =>
          events.map((item) => (item.event_id === event.event_id ? response.event : item)),
        );
        this.captchaSummary.update((summary) =>
          summary && !event.human_label
            ? {
                ...summary,
                stats: { ...summary.stats, human_labeled: summary.stats.human_labeled + 1 },
              }
            : summary,
        );
      }
    } catch (error) {
      this.showCaptchaReviewMessage(this.shell.readError(error), 6_000);
    } finally {
      this.captchaSavingEventId.set('');
    }
  }

  private showCaptchaReviewMessage(message: string, durationMs = 3_500): void {
    this.clearCaptchaReviewMessage();
    this.captchaReviewMessage.set(message);
    this.captchaReviewMessageTimer = window.setTimeout(() => {
      this.captchaReviewMessage.set(null);
      this.captchaReviewMessageTimer = null;
    }, durationMs);
  }

  private clearCaptchaReviewMessage(): void {
    if (this.captchaReviewMessageTimer !== null) {
      window.clearTimeout(this.captchaReviewMessageTimer);
      this.captchaReviewMessageTimer = null;
    }
    this.captchaReviewMessage.set(null);
  }

  private applyCaptchaPage(page: CaptchaEventsPage): void {
    this.captchaEvents.set(page.events);
    this.captchaPage.set(page.pagination.page);
    this.captchaPageSize.set(page.pagination.page_size);
    this.captchaTotal.set(page.pagination.total);
    this.captchaTotalPages.set(page.pagination.total_pages);
    const correction = this.captchaPendingCorrection();
    if (correction && !page.events.some((event) => event.event_id === correction.eventId)) {
      this.captchaPendingCorrection.set(null);
    }
    this.captchaDrafts.update((drafts) => {
      const next = { ...drafts };
      for (const event of page.events) {
        if (!(event.event_id in next) && event.human_label) {
          next[event.event_id] = event.human_label.answer;
        }
      }
      return next;
    });
  }

  public setCaptchaSamplingEnabled(enabled: boolean): void {
    if (this.captchaSamplingEnabled() === enabled) {
      return;
    }
    this.captchaSamplingEnabled.set(enabled);
    this.captchaSamplingDirty.set(true);
  }

  public setCaptchaSamplingLimit(value: number | string): void {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) {
      return;
    }
    const normalized = Math.min(50, Math.max(2, Math.round(parsed)));
    if (this.captchaSamplingLimit() === normalized) {
      return;
    }
    this.captchaSamplingLimit.set(normalized);
    this.captchaSamplingDirty.set(true);
  }

  public async saveCaptchaSamplingControl(): Promise<void> {
    if (this.captchaSamplingSaving()) {
      return;
    }
    this.captchaSamplingSaving.set(true);
    this.shell.errorMessage.set(null);
    try {
      const control = await this.api.updateCaptchaSamplingControl(
        this.captchaSamplingEnabled(),
        this.captchaSamplingLimit(),
      );
      this.captchaSamplingDirty.set(false);
      this.applyCaptchaSamplingControl(control);
      this.shell.showToast(
        control.enabled
          ? `Muestreo activado: ${control.sample_limit} CAPTCHA por lote`
          : 'Muestreo adicional desactivado',
      );
    } catch (error) {
      this.shell.errorMessage.set(this.shell.readError(error));
    } finally {
      this.captchaSamplingSaving.set(false);
    }
  }

  public applyCaptchaSamplingControl(control: CaptchaSamplingControl): void {
    this.captchaSamplingControl.set(control);
    if (!this.captchaSamplingDirty()) {
      this.captchaSamplingEnabled.set(control.enabled);
      this.captchaSamplingLimit.set(control.sample_limit);
    }
  }

  public requestCaptchaAuthorityFallback(): void {
    this.shell.setPendingAction({
      title: 'Usar 2Captcha como autoridad',
      message:
        'V6 seguirá comparando en sombra, pero desde el siguiente CAPTCHA final la respuesta se pedirá a 2Captcha.',
      execute: async () => {
        this.captchaAuthorityControl.set(
          await this.api.updateCaptchaAuthorityControl('2captcha'),
        );
        return { status: 'ok' };
      },
      successMessage: '2Captcha quedó como autoridad del CAPTCHA final',
    });
  }

  public requestCaptchaAuthorityCanary(): void {
    const resetCircuit = this.captchaAuthorityControl()?.circuit_state === 'open';
    this.shell.setPendingAction({
      title: resetCircuit ? 'Reactivar canario V6' : 'Activar canario V6',
      message: resetCircuit
        ? 'Se cerrará el circuito después de tu revisión. V6 volverá a resolver únicamente dentro del límite restante y con fallback a 2Captcha.'
        : 'V6 resolverá dentro del límite restante y con los umbrales guardados. 2Captcha seguirá disponible como fallback.',
      execute: async () => {
        this.captchaAuthorityControl.set(
          await this.api.updateCaptchaAuthorityControl('canary', resetCircuit),
        );
        return { status: 'ok' };
      },
      successMessage: 'Canario V6 activo para el siguiente CAPTCHA compatible',
    });
  }

  private get shell() { return this.injector.get(DASHBOARD_CAPTCHAS_SHELL); }
}
