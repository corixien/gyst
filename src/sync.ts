import { storage } from 'wxt/utils/storage';
import { fetchState, type RemoteState } from './api';
import type { FreeWindow } from './schedule';
import { inFreeWindow } from './schedule';
import { normalizeSettings } from './settings';
import { settingsItem } from './storage';

export interface Account {
  server: string;
  token: string;
  accountId: string;
}

export const accountItem = storage.defineItem<Account | null>('local:account', { fallback: null });

// Last state received from the server. Used for free checks, so blocking works offline with the last known state.
export const remoteItem = storage.defineItem<Partial<RemoteState> & { synced?: boolean }>('local:remote', {
  fallback: { free_windows: [], grant_until: 0, settings_until: 0, partners: 0, synced: false },
});

// Pull the server state into local storage. Settings from the server replace local ones.
export async function syncNow(): Promise<boolean> {
  const account = await accountItem.getValue();
  if (!account) return false;
  try {
    const state = await fetchState(account.server, account.token);
    const current = await settingsItem.getValue();
    if (JSON.stringify(normalizeSettings(current)) !== JSON.stringify(normalizeSettings(state.settings))) {
      await settingsItem.setValue(normalizeSettings(state.settings));
    }
    await remoteItem.setValue({ ...state, synced: true });
    return true;
  } catch {
    await remoteItem.setValue({ ...(await remoteItem.getValue()), synced: false });
    return false;
  }
}

export async function grantRunning(): Promise<boolean> {
  const remote = await remoteItem.getValue();
  return (remote.grant_until ?? 0) > Date.now() / 1000;
}

// Free means: a partner grant runs, or the current time is in a free window.
export async function isFreeNow(): Promise<boolean> {
  if (await grantRunning()) return true;
  const remote = await remoteItem.getValue();
  return inFreeWindow((remote.free_windows ?? []) as FreeWindow[], new Date());
}
