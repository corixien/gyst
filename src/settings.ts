export type Language = 'auto' | 'de' | 'en';

export interface Settings {
  enabled: boolean; // master switch: when off, no site is blocked
  sites: string[]; // blocked domains, e.g. "youtube.com"; subdomains and all paths are included
  popupMessage: string; // text the user must type to turn off or unblock; empty = default
  blockMessage: string; // text on the block page; empty = default
  language: Language;
}

export const DEFAULT_SETTINGS: Settings = {
  enabled: false,
  sites: [],
  popupMessage: '',
  blockMessage: '',
  language: 'auto',
};

// Stored objects can miss keys from newer versions, so merge over defaults.
export function normalizeSettings(raw: Partial<Settings> | null | undefined): Settings {
  const merged = { ...DEFAULT_SETTINGS, ...raw };
  return {
    ...merged,
    sites: Array.isArray(merged.sites) ? merged.sites.filter((s) => typeof s === 'string') : [],
  };
}
