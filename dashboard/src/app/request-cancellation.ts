import { Observable, Subject, firstValueFrom, takeUntil, throwIfEmpty } from 'rxjs';

export class RequestCancelledError extends Error {
  constructor() {
    super('Request cancelled');
    this.name = 'RequestCancelledError';
  }
}

export class RequestScope {
  private readonly cancelledSubject = new Subject<void>();
  private cancelled = false;

  get isCancelled(): boolean {
    return this.cancelled;
  }

  fork(): RequestScope {
    const child = new RequestScope();
    if (this.cancelled) {
      child.cancel();
    } else {
      const parentSubscription = this.cancelledSubject.subscribe(() => child.cancel());
      child.cancelledSubject.subscribe(() => parentSubscription.unsubscribe());
    }
    return child;
  }

  async read<T>(source: Observable<T>): Promise<T> {
    if (this.cancelled) {
      throw new RequestCancelledError();
    }
    return firstValueFrom(
      source.pipe(
        takeUntil(this.cancelledSubject),
        throwIfEmpty(() => new RequestCancelledError()),
      ),
    );
  }

  cancel(): void {
    if (this.cancelled) {
      return;
    }
    this.cancelled = true;
    this.cancelledSubject.next();
    this.cancelledSubject.complete();
  }
}

export function isRequestCancelled(error: unknown): error is RequestCancelledError {
  return error instanceof RequestCancelledError;
}
