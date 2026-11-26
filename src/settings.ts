export type Language = 'auto' | 'de' | 'en';

// How turning off or removing a site is confirmed: the typed sentence, or an 8-digit code from a partner.
export type UnlockMode = 'text' | 'partner';

export interface Settings {
  enabled: boolean; // master switch: when off, no site is blocked
  sites: string[]; // blocked domains, e.g. "youtube.com"; subdomains and all paths are included
  popupMessage: string; // text the user must type to turn off or unblock; empty = default
  blockMessage: string; // text on the block page; empty = default
  language: Language;
  unlock: UnlockMode;
  displayName: string; // shown to partners, e.g. "Mateo"
}

export const DEFAULT_SETTINGS: Settings = {
  enabled: false,
  sites: [],
  popupMessage: '',
  blockMessage: '',
  language: 'auto',
  unlock: 'text',
  displayName: '',
};

// Stored objects can miss keys from newer versions, so merge over defaults.
export function normalizeSettings(raw: Partial<Settings> | null | undefined): Settings {
  const merged = { ...DEFAULT_SETTINGS, ...raw };
  return {
    ...merged,
    sites: Array.isArray(merged.sites) ? merged.sites.filter((s) => typeof s === 'string') : [],
    unlock: merged.unlock === 'partner' ? 'partner' : 'text',
    displayName: typeof merged.displayName === 'string' ? merged.displayName : '',
  };
}
