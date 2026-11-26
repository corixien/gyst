import { describe, expect, it } from 'vitest';
import { inFreeWindow } from './schedule';
import { gatedChanges } from './rules';
import { DEFAULT_SETTINGS } from './settings';

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

describe('gatedChanges', () => {
  const base = { ...DEFAULT_SETTINGS, enabled: true, sites: ['youtube.com'] };

  it('adding a site and enabling are free', () => {
    expect(gatedChanges(base, { ...base, sites: ['youtube.com', 'x.com'] }, [], [])).toEqual([]);
    expect(gatedChanges({ ...base, enabled: false }, { ...base, enabled: true }, [], [])).toEqual([]);
  });

  it('removing a site, disabling, messages and new windows are gated', () => {
    expect(gatedChanges(base, { ...base, sites: [] }, [], [])).toContain('remove_site');
    expect(gatedChanges(base, { ...base, enabled: false }, [], [])).toContain('disable');
    expect(gatedChanges(base, { ...base, blockMessage: 'x' }, [], [])).toContain('blockMessage');
    expect(gatedChanges(base, base, [], [{ day: 0, from: '10:00', to: '11:00' }])).toContain('add_free_window');
  });

  it('removing a free window is free', () => {
    expect(gatedChanges(base, base, [{ day: 0, from: '10:00', to: '11:00' }], [])).toEqual([]);
  });
});
