import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import type { RequestScope } from '../../request-cancellation';

@Injectable({ providedIn: 'root' })
export class ApiTransport {
  private readonly http = inject(HttpClient);

  async read<T>(url: string, scope?: RequestScope): Promise<T> {
    const request = this.http.get<T>(url);
    return scope ? scope.read(request) : firstValueFrom(request);
  }

  async post<T>(url: string, payload: unknown): Promise<T> {
    return firstValueFrom(this.http.post<T>(url, payload));
  }

  async put<T>(url: string, payload: unknown): Promise<T> {
    return firstValueFrom(this.http.put<T>(url, payload));
  }

  async blob(url: string, scope?: RequestScope): Promise<Blob> {
    const request = this.http.get(url, { responseType: 'blob' });
    return scope ? scope.read(request) : firstValueFrom(request);
  }
}
