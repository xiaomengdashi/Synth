let serverTimeZone = 'UTC';

export function getServerTimeZone(): string {
  return serverTimeZone;
}

export function setServerTimeZone(timeZone: string): void {
  // Validate the server-provided zone before using it throughout the UI.
  new Intl.DateTimeFormat('en', { timeZone }).format();
  serverTimeZone = timeZone;
}

export async function initializeServerTimeZone(): Promise<void> {
  try {
    const response = await fetch('/api/v1/config/timezone', { signal: AbortSignal.timeout(5000) });
    if (!response.ok) return;
    const data = await response.json();
    if (typeof data.timeZone === 'string') setServerTimeZone(data.timeZone);
  } catch {
    // The backend may be unavailable; retain an unambiguous UTC fallback.
  }
}

export function formatDistanceToNow(date: Date): string {
  const now = new Date();
  const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (diffInSeconds < 60) {
    return '刚刚';
  }

  const diffInMinutes = Math.floor(diffInSeconds / 60);
  if (diffInMinutes < 60) {
    return `${diffInMinutes}分钟前`;
  }

  const diffInHours = Math.floor(diffInMinutes / 60);
  if (diffInHours < 24) {
    return `${diffInHours}小时前`;
  }

  const diffInDays = Math.floor(diffInHours / 24);
  if (diffInDays < 30) {
    return `${diffInDays}天前`;
  }

  const diffInMonths = Math.floor(diffInDays / 30);
  if (diffInMonths < 12) {
    return `${diffInMonths}个月前`;
  }

  const diffInYears = Math.floor(diffInDays / 365);
  return `${diffInYears}年前`;
}

/** 文章时间统一显示具体时间(与 publish_time 同精度),不用"6个月前"这类相对表述。 */
export function formatAbsolute(date: Date): string {
  if (Number.isNaN(date.getTime())) return '—';
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: getServerTimeZone(), year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(date);
  const value = (type: Intl.DateTimeFormatPartTypes) => parts.find(part => part.type === type)?.value;
  return `${value('year')}-${value('month')}-${value('day')} ${value('hour')}:${value('minute')}`;
}

export function serverDayKey(date: Date): string {
  return formatAbsolute(date).slice(0, 10);
}

export function recentServerDays(now = new Date(), count = 7): string[] {
  const [year, month, day] = serverDayKey(now).split('-').map(Number);
  // Work with calendar dates here; elapsed 24-hour periods do not model DST days.
  return Array.from({ length: count }, (_, index) => (
    new Date(Date.UTC(year, month - 1, day - (count - 1 - index))).toISOString().slice(0, 10)
  ));
}
