const PERU_TIME_ZONE = 'America/Lima';
const DATE_ONLY_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;
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
  const dateOnly = DATE_ONLY_PATTERN.exec(value.trim());
  if (dateOnly) {
    return `${dateOnly[3]}-${dateOnly[2]}-${dateOnly[1]}`;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return fallback || value;
  }
  return formatParts(date).date;
}

export function formatPeruTime(
  value: string | number | null | undefined,
  fallback = '',
): string {
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

export function formatPeruDateTime(
  value: string | null | undefined,
  fallback = '',
): string {
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

function formatParts(date: Date): { date: string; time: string } {
  const parts = Object.fromEntries(
    dateTimeFormatter.formatToParts(date).map((part) => [part.type, part.value]),
  );
  return {
    date: `${parts['day']}-${parts['month']}-${parts['year']}`,
    time: `${parts['hour']}:${parts['minute']}:${parts['second']}`,
  };
}
