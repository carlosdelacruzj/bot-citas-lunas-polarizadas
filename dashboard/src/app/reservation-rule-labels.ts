import { ExcludedDateRange } from './reservation-rules.model';

interface ReservationDateRules {
  minimum_reservation_date: string | null;
  maximum_reservation_date: string | null;
  allowed_weekdays: number[] | null;
  excluded_date_ranges: readonly ExcludedDateRange[];
}

interface CalendarDate {
  year: number;
  month: number;
  day: number;
  timestamp: number;
}

const ISO_DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;
const MAX_ENUMERATED_WINDOW_DAYS = 62;
const MAX_VISIBLE_DATES = 16;
const MONTH_NAMES = [
  'enero',
  'febrero',
  'marzo',
  'abril',
  'mayo',
  'junio',
  'julio',
  'agosto',
  'septiembre',
  'octubre',
  'noviembre',
  'diciembre',
] as const;
const SPANISH_LIST_FORMAT = new Intl.ListFormat('es-PE', {
  style: 'long',
  type: 'conjunction',
});

export function formatReservationDateRules(rules: ReservationDateRules): string {
  const minimum = parseCalendarDate(rules.minimum_reservation_date);
  const maximum = parseCalendarDate(rules.maximum_reservation_date);
  const exclusions = rules.excluded_date_ranges ?? [];
  const weekdays = normalizedWeekdays(rules.allowed_weekdays);

  if (minimum && maximum && exclusions.length) {
    const concreteDates = enumerateConcreteDates(minimum, maximum, weekdays, exclusions);
    if (concreteDates && concreteDates.length <= MAX_VISIBLE_DATES) {
      return concreteDates.length
        ? `Solo: ${formatCalendarDateList(concreteDates)}`
        : 'Ninguna fecha permitida';
    }
  }

  const parts: string[] = [];
  if (minimum && maximum) {
    parts.push(
      minimum.timestamp === maximum.timestamp
        ? `Solo el ${formatCalendarDate(minimum)}`
        : capitalize(formatCalendarDateRange(minimum, maximum)),
    );
  } else if (minimum) {
    parts.push(`Desde el ${formatCalendarDate(minimum)}`);
  } else if (maximum) {
    parts.push(`Hasta el ${formatCalendarDate(maximum)}`);
  }

  const excludedLabels = exclusions.map(formatExcludedRange).filter(Boolean);
  if (excludedLabels.length) {
    parts.push(`Excepto ${SPANISH_LIST_FORMAT.format(excludedLabels)}`);
  }
  if (parts.length) {
    return parts.join(' · ');
  }
  return weekdays.length ? 'Sin límite de fechas' : 'Cualquier fecha';
}

export function formatReservationDateRange(startValue: string, endValue: string): string {
  const start = parseCalendarDate(startValue);
  const end = parseCalendarDate(endValue);
  if (!start || !end) {
    return startValue === endValue ? startValue : `${startValue} – ${endValue}`;
  }
  return start.timestamp === end.timestamp
    ? formatCalendarDate(start)
    : capitalize(formatCalendarDateRange(start, end));
}

function enumerateConcreteDates(
  minimum: CalendarDate,
  maximum: CalendarDate,
  weekdays: number[],
  exclusions: readonly ExcludedDateRange[],
): CalendarDate[] | null {
  if (maximum.timestamp < minimum.timestamp) {
    return null;
  }
  const windowDays = Math.floor((maximum.timestamp - minimum.timestamp) / 86_400_000) + 1;
  if (windowDays > MAX_ENUMERATED_WINDOW_DAYS || weekdays.length) {
    return null;
  }
  const excludedIntervals = exclusions
    .map((range) => [parseCalendarDate(range.start_date), parseCalendarDate(range.end_date)] as const)
    .filter(
      (range): range is readonly [CalendarDate, CalendarDate] => Boolean(range[0] && range[1]),
    );
  const dates: CalendarDate[] = [];
  for (let timestamp = minimum.timestamp; timestamp <= maximum.timestamp; timestamp += 86_400_000) {
    if (
      excludedIntervals.some(
        ([start, end]) => start.timestamp <= timestamp && timestamp <= end.timestamp,
      )
    ) {
      continue;
    }
    const date = new Date(timestamp);
    dates.push({
      year: date.getUTCFullYear(),
      month: date.getUTCMonth() + 1,
      day: date.getUTCDate(),
      timestamp,
    });
    if (dates.length > MAX_VISIBLE_DATES) {
      return dates;
    }
  }
  return dates;
}

function formatCalendarDateList(dates: readonly CalendarDate[]): string {
  const groups = new Map<string, CalendarDate[]>();
  for (const date of dates) {
    const key = `${date.year}-${String(date.month).padStart(2, '0')}`;
    groups.set(key, [...(groups.get(key) ?? []), date]);
  }
  return SPANISH_LIST_FORMAT.format(
    [...groups.values()].map((group) => {
      const first = group[0];
      const days = SPANISH_LIST_FORMAT.format(group.map((date) => String(date.day)));
      return `${days} de ${monthName(first)} de ${first.year}`;
    }),
  );
}

function formatExcludedRange(range: ExcludedDateRange): string {
  const start = parseCalendarDate(range.start_date);
  const end = parseCalendarDate(range.end_date);
  if (!start || !end) {
    return range.start_date === range.end_date
      ? `el ${range.start_date}`
      : `del ${range.start_date} al ${range.end_date}`;
  }
  return start.timestamp === end.timestamp
    ? `el ${formatCalendarDate(start)}`
    : formatCalendarDateRange(start, end);
}

function formatCalendarDateRange(start: CalendarDate, end: CalendarDate): string {
  if (start.year === end.year && start.month === end.month) {
    return `del ${start.day} al ${end.day} de ${monthName(start)} de ${start.year}`;
  }
  if (start.year === end.year) {
    return `del ${start.day} de ${monthName(start)} al ${end.day} de ${monthName(end)} de ${start.year}`;
  }
  return `del ${formatCalendarDate(start)} al ${formatCalendarDate(end)}`;
}

function formatCalendarDate(date: CalendarDate): string {
  return `${date.day} de ${monthName(date)} de ${date.year}`;
}

function monthName(date: CalendarDate): string {
  return MONTH_NAMES[date.month - 1];
}

function parseCalendarDate(value: string | null | undefined): CalendarDate | null {
  const match = ISO_DATE_PATTERN.exec(value?.trim() ?? '');
  if (!match) {
    return null;
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const timestamp = Date.UTC(year, month - 1, day);
  const date = new Date(timestamp);
  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day
  ) {
    return null;
  }
  return { year, month, day, timestamp };
}

function normalizedWeekdays(value: number[] | null): number[] {
  return [...new Set((value ?? []).filter((day) => day >= 1 && day <= 7))];
}

function capitalize(value: string): string {
  return value ? `${value.charAt(0).toUpperCase()}${value.slice(1)}` : value;
}
