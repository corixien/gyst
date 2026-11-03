import { storage } from 'wxt/utils/storage';
import { DEFAULT_SETTINGS, normalizeSettings, type Settings } from './settings';

export const settingsItem = storage.defineItem<Settings>('local:settings', {
  fallback: DEFAULT_SETTINGS,
});

export const readSettings = async () => normalizeSettings(await settingsItem.getValue());

// Tab id -> URL the tab wanted before it was sent to the block page. Session-scoped, so it is lost on browser restart.
export const blockedTabsItem = storage.defineItem<Record<string, string>>('session:blockedTabs', {
  fallback: {},
});
