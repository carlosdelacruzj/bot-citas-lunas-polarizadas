const PERU_TIME_ZONE = 'America/Lima';
const ISO_DATE_ONLY_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;
const DAY_FIRST_DATE_ONLY_PATTERN = /^(\d{1,2})[\/-](\d{1,2})[\/-](\d{4})$/;
const TIME_ONLY_PATTERN = /^(\d{1,2}):(\d{2})(?::\d{2})?/;

const dateTimeFormatter = new Intl.DateTimeFormat('es-PE', {
  timeZone: PERU_TIME_ZONE,
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
});

export function formatPeruDate(value: string | null | undefined, fallback = ''): string {
  if (!value) {
    return fallback;
  }
  const text = value.trim();
  const isoDate = ISO_DATE_ONLY_PATTERN.exec(text);
  if (isoDate) {
    return normalizedDate(isoDate[1], isoDate[2], isoDate[3], fallback || value);
  }
  const dayFirstDate = DAY_FIRST_DATE_ONLY_PATTERN.exec(text);
  if (dayFirstDate) {
    return normalizedDate(dayFirstDate[3], dayFirstDate[2], dayFirstDate[1], fallback || value);
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return fallback || value;
  }
  return formatParts(date).date;
}

function normalizedDate(year: string, month: string, day: string, fallback: string): string {
  const numericYear = Number(year);
  const numericMonth = Number(month);
  const numericDay = Number(day);
  const candidate = new Date(Date.UTC(numericYear, numericMonth - 1, numericDay));
  if (
    candidate.getUTCFullYear() !== numericYear ||
    candidate.getUTCMonth() !== numericMonth - 1 ||
    candidate.getUTCDate() !== numericDay
  ) {
    return fallback;
  }
  return `${String(numericDay).padStart(2, '0')}-${String(numericMonth).padStart(2, '0')}-${numericYear}`;
}

export function formatPeruTime(value: string | number | null | undefined, fallback = ''): string {
  if (value === null || value === undefined || value === '') {
    return fallback;
  }
  if (typeof value === 'number' || /^\d{1,2}$/.test(String(value).trim())) {
    const hour = Number(value);
    return Number.isInteger(hour) && hour >= 0 && hour <= 23
      ? `${String(hour).padStart(2, '0')}:00`
      : fallback || String(value);
  }
  const timeOnly = TIME_ONLY_PATTERN.exec(value.trim());
  if (timeOnly) {
    return `${timeOnly[1].padStart(2, '0')}:${timeOnly[2]}`;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return fallback || value;
  }
  return formatParts(date).time;
}

export function formatPeruDateTime(value: string | null | undefined, fallback = ''): string {
  if (!value) {
    return fallback;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return fallback || value;
  }
  const parts = formatParts(date);
  return `${parts.date} ${parts.time}`;
}

export function peruDateTimeSortValue(
  dateValue: string | null | undefined,
  timeValue?: string | number | null,
): number | null {
  if (!dateValue) {
    return null;
  }
  const text = dateValue.trim();
  const isoDate = ISO_DATE_ONLY_PATTERN.exec(text);
  const dayFirstDate = DAY_FIRST_DATE_ONLY_PATTERN.exec(text);
  if (isoDate || dayFirstDate) {
    const [year, month, day] = isoDate
      ? [Number(isoDate[1]), Number(isoDate[2]), Number(isoDate[3])]
      : [Number(dayFirstDate![3]), Number(dayFirstDate![2]), Number(dayFirstDate![1])];
    const timeMatch = TIME_ONLY_PATTERN.exec(String(timeValue ?? '').trim());
    const hour = timeMatch ? Number(timeMatch[1]) : 0;
    const minute = timeMatch ? Number(timeMatch[2]) : 0;
    const candidate = new Date(Date.UTC(year, month - 1, day, hour, minute));
    if (
      candidate.getUTCFullYear() !== year ||
      candidate.getUTCMonth() !== month - 1 ||
      candidate.getUTCDate() !== day ||
      hour > 23 ||
      minute > 59
    ) {
      return null;
    }
    return candidate.getTime();
  }
  const normalizedTimestamp = /^\d{4}-\d{2}-\d{2}\s/.test(text)
    ? text.replace(' ', 'T')
    : text;
  const timestamp = Date.parse(normalizedTimestamp);
  return Number.isNaN(timestamp) ? null : timestamp;
}

function formatParts(date: Date): { date: string; time: string } {
  const parts = Object.fromEntries(
    dateTimeFormatter.formatToParts(date).map((part) => [part.type, part.value]),
  );
  return {
    date: `${parts['day']}-${parts['month']}-${parts['year']}`,
    time: `${parts['hour']}:${parts['minute']}:${parts['second']}`,
  };
}
