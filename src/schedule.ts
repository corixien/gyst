// Free windows: one entry per weekday (0 = Monday ... 6 = Sunday), local time, may wrap past midnight.
export interface FreeWindow {
  day: number;
  from: string; // "HH:MM"
  to: string; // "HH:MM"
}

const minuteOfDay = (hhmm: string) => {
  const [h = 0, m = 0] = hhmm.split(':').map(Number);
  return h * 60 + m;
};

// A window that wraps midnight belongs to the day it starts on.
export function inFreeWindow(windows: FreeWindow[], now: Date): boolean {
  const day = (now.getDay() + 6) % 7; // JS: Sunday = 0
  const minute = now.getHours() * 60 + now.getMinutes();
  return windows.some((w) => {
    const from = minuteOfDay(w.from);
    const to = minuteOfDay(w.to);
    if (from < to) return w.day === day && minute >= from && minute < to;
    if (from > to) {
      return (w.day === day && minute >= from) || (w.day === (day + 6) % 7 && minute < to);
    }
    return false;
  });
}
