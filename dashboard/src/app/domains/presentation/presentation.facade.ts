import { Injectable } from '@angular/core';
import { apiErrorMessage } from '../../api/shared/api-error';

import { STATUS_PRESENTATIONS, StatusTone } from '../../dashboard-domain.contracts';
import { formatPeruDate, formatPeruDateTime, formatPeruTime } from '../../peru-date-time';

@Injectable()
export class DashboardPresentation {

  public readonly formatDate = formatPeruDate;

  public readonly formatDateTime = formatPeruDateTime;

  public readonly formatTime = formatPeruTime;

  public formatMoney(value: number): string {
    return new Intl.NumberFormat('es-PE', {
      style: 'currency',
      currency: 'PEN',
      minimumFractionDigits: 2,
    }).format(value);
  }

  public formatPercent(value: number): string {
    return new Intl.NumberFormat('es-PE', {
      style: 'percent',
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    }).format(value);
  }

  public statusLabel(
    value: string | boolean | null | undefined,
    fallback = 'Sin estado',
  ): string {
    if (value === null || value === undefined || value === '') {
      return fallback;
    }
    if (typeof value === 'boolean') {
      return value ? 'Activo' : 'Inactivo';
    }
    const normalized = value.trim().toLowerCase();
    return (
      STATUS_PRESENTATIONS[normalized]?.label ?? this.capitalize(normalized.replaceAll('_', ' '))
    );
  }

  public statusTone(value: string | boolean | null | undefined): StatusTone {
    if (typeof value === 'boolean') {
      return value ? 'good' : 'bad';
    }
    if (!value) {
      return 'neutral';
    }
    return STATUS_PRESENTATIONS[value.trim().toLowerCase()]?.tone ?? 'neutral';
  }

  public readError(error: unknown): string {
    return apiErrorMessage(error);
  }

  public formatClock(date: Date): string {
    return date.toLocaleTimeString('es-PE', {
      timeZone: 'America/Lima',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hourCycle: 'h23',
    });
  }

  public capitalize(value: string): string {
    return value ? `${value.charAt(0).toUpperCase()}${value.slice(1)}` : value;
  }

  public optionalText(value: string): string | null {
    const trimmed = value.trim();
    return trimmed || null;
  }
}
