import type { FreeWindow } from './schedule';
import type { Settings } from './settings';

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(`HTTP ${status}`);
  }
}

export interface RemoteState {
  settings: Settings;
  free_windows: FreeWindow[];
  grant_until: number; // unix seconds, 0 = none
  settings_until: number;
  partners: number;
  now: number;
}

export const DEFAULT_SERVER = 'https://gyst-sync-y5x4.onrender.com'; // change in the popup if your service has another URL

export async function apiCall<T>(server: string, path: string, init: { method?: string; body?: unknown; token?: string } = {}): Promise<T> {
  const response = await fetch(`${server.replace(/\/$/, '')}${path}`, {
    method: init.method ?? 'GET',
    headers: {
      ...(init.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(init.token ? { Authorization: `Bearer ${init.token}` } : {}),
    },
    body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(response.status, data.detail);
  return data as T;
}

// Connects this device with the code a partner issued (10 minutes, one use).
export const claimDevice = (server: string, partnerUsername: string, code: string) =>
  apiCall<{ account_id: string; token: string }>(server, '/api/devices/claim', {
    method: 'POST',
    body: { partner_username: partnerUsername, code },
  });

export const fetchState = (server: string, token: string) => apiCall<RemoteState>(server, '/api/state', { token });

export const putSettings = (server: string, token: string, settings: Settings, freeWindows: FreeWindow[]) =>
  apiCall<{ ok: boolean }>(server, '/api/settings', {
    method: 'PUT',
    token,
    body: { ...settings, free_windows: freeWindows },
  });

export interface PartnerInfo {
  id: string;
  name: string;
  since: string;
}

export const fetchPartners = (server: string, token: string) =>
  apiCall<{ partners: PartnerInfo[] }>(server, '/api/partners', { token });

export const removePartner = (server: string, token: string, partnerId: string) =>
  apiCall<{ ok: boolean }>(server, '/api/partners/remove', { method: 'POST', token, body: { partner_id: partnerId } });

export const addSite = (server: string, token: string, domain: string) =>
  apiCall<{ ok: boolean; sites: string[] }>(server, '/api/sites', { method: 'POST', token, body: { domain } });

export const setEnabled = (server: string, token: string, enabled: boolean) =>
  apiCall<{ ok: boolean }>(server, '/api/enabled', { method: 'POST', token, body: { enabled } });

