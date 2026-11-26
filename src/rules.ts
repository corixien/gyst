import type { Settings } from './settings';
import type { FreeWindow } from './schedule';

// Same rules as the server (server/gating.py): these changes loosen the block and need a partner grant.
export function gatedChanges(old: Settings, next: Settings, oldWindows: FreeWindow[], nextWindows: FreeWindow[]): string[] {
  const gated: string[] = [];
  if (old.sites.some((site) => !next.sites.includes(site))) gated.push('remove_site');
  if (old.enabled && !next.enabled) gated.push('disable');
  if (old.unlock !== next.unlock) gated.push('unlock');
  if (old.popupMessage !== next.popupMessage) gated.push('popupMessage');
  if (old.blockMessage !== next.blockMessage) gated.push('blockMessage');
  if (old.language !== next.language) gated.push('language');
  const key = (w: FreeWindow) => `${w.day}|${w.from}|${w.to}`;
  const before = new Set(oldWindows.map(key));
  if (nextWindows.some((w) => !before.has(key(w)))) gated.push('add_free_window');
  return gated;
}
