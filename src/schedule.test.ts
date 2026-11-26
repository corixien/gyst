import { describe, expect, it } from 'vitest';
import { inFreeWindow } from './schedule';

// 2026-01-05 is a Monday.
const at = (dayOffset: number, hour: number, minute = 0) => new Date(2026, 0, 5 + dayOffset, hour, minute);

describe('inFreeWindow', () => {
  it('matches only on its weekday and inside the range', () => {
    const windows = [{ day: 1, from: '20:00', to: '22:00' }];
    expect(inFreeWindow(windows, at(1, 21))).toBe(true);
    expect(inFreeWindow(windows, at(1, 22))).toBe(false);
    expect(inFreeWindow(windows, at(0, 21))).toBe(false);
  });

  it('wraps midnight into the next day, counted to the start day', () => {
    const windows = [{ day: 4, from: '23:00', to: '01:00' }];
    expect(inFreeWindow(windows, at(4, 23, 30))).toBe(true);
    expect(inFreeWindow(windows, at(5, 0, 30))).toBe(true);
    expect(inFreeWindow(windows, at(5, 1, 30))).toBe(false);
  });

  it('Sunday wrap goes to Monday', () => {
    const windows = [{ day: 6, from: '23:00', to: '01:00' }];
    expect(inFreeWindow(windows, at(7, 0, 30))).toBe(true); // Monday 00:30 still belongs to Sunday's window
  });

  it('empty list is never free', () => {
    expect(inFreeWindow([], at(0, 12))).toBe(false);
  });
});

