import { storage } from 'wxt/utils/storage';
import { DEFAULT_SETTINGS, normalizeSettings, type Draft, type Settings } from './settings';

export const settingsItem = storage.defineItem<Settings>('local:settings', {
  fallback: DEFAULT_SETTINGS,
});

export const readSettings = async () => normalizeSettings(await settingsItem.getValue());

// Tab id -> URL the tab wanted before it was sent to the block page. Session-scoped, so it is lost on browser restart.
export const blockedTabsItem = storage.defineItem<Record<string, string>>('session:blockedTabs', {
  fallback: {},
});

export const draftItem = storage.defineItem<Draft | null>('local:draft', { fallback: null });

// Time the page was on when it was sent to the block page, keyed by URL. Lets the video continue at the same second.
export interface Resume {
  time: number; // seconds
  at: number; // ms timestamp, entries expire
}
export const resumeItem = storage.defineItem<Record<string, Resume>>('session:resume', { fallback: {} });
