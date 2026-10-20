import { signal } from '@angular/core';
import { apiErrorMessage } from './api/shared/api-error';
import { RequestCancelledError, RequestScope, isRequestCancelled } from './request-cancellation';

export class LoadSection {
  private generation = 0;
  private readonly loadingState = signal(false);
  private readonly errorState = signal<string | null>(null);
  private readonly updatedState = signal<Date | null>(null);
  readonly loading = this.loadingState.asReadonly();
  readonly error = this.errorState.asReadonly();
  readonly updatedAt = this.updatedState.asReadonly();

  constructor(readonly label: string) { }

  reset(): void {
    this.generation++;
    this.loadingState.set(false);
    this.errorState.set(null);
    this.updatedState.set(null);
  }

  async load<T>(scope: RequestScope, request: () => Promise<T>, publish: (value: T) => void): Promise<boolean> {
    const generation = ++this.generation;
    const current = () => generation === this.generation && !scope.isCancelled;
    this.loadingState.set(true);
    this.errorState.set(null);
    try {
      if (scope.isCancelled) return false;
      const value = await request();
      if (!current()) return true;
      publish(value);
      this.updatedState.set(new Date());
      return true;
    } catch (error) {
      if (!current() || isRequestCancelled(error)) return true;
      this.errorState.set(apiErrorMessage(error));
      return false;
    } finally {
      if (generation === this.generation) this.loadingState.set(false);
    }
  }
}

export async function loadSections(
  scope: RequestScope,
  essential: Promise<boolean>[],
  auxiliary: Promise<unknown>[] = [],
): Promise<void> {
  const [results] = await Promise.all([Promise.all(essential), Promise.allSettled(auxiliary)]);
  if (scope.isCancelled) throw new RequestCancelledError();
  if (results.some((success) => !success)) throw new Error('No se pudo actualizar el bloque principal. Revisa su estado.');
}
