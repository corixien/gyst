import type { Language } from './settings';

const de = {
  appName: 'GYST',
  tagline: 'Get Your Shit Together',
  on: 'An',
  off: 'Aus',
  sitesTitle: 'Gesperrte Seiten',
  siteInput: 'z.B. youtube.com',
  add: 'Hinzufügen',
  addCurrent: 'Aktueller Tab',
  remove: 'Entfernen',
  noSites: 'Noch keine Seiten gesperrt.',
  invalidSite: 'Ungültige Domain.',
  settingsTitle: 'Einstellungen',
  popupMessageLabel: 'Nachricht zum Ausschalten/Entfernen',
  blockMessageLabel: 'Nachricht auf der Blockseite',
  defaultPopupMessage: 'Ich will das wirklich.',
  defaultBlockMessage: 'Get your shit together. Diese Seite ist gesperrt.',
  save: 'Speichern',
  saved: 'Gespeichert',
  language: 'Sprache',
  languageAuto: 'Automatisch',
  confirmTitle: 'Wirklich ausschalten?',
  confirmRemoveTitle: 'Wirklich entfernen?',
  confirmHint: 'Tippe diesen Satz exakt ab, dann warte 10 Sekunden.',
  confirmWait: 'Warte noch {seconds} s',
  confirmDo: 'Bestätigen',
  cancel: 'Abbrechen',
  mismatch: 'Bisher falsch.',
  blockedTitle: 'Gesperrt',
  footer: 'Alle Daten bleiben lokal. Keine Accounts, keine Netzwerkaufrufe.',
};

export type MessageKey = keyof typeof de;

const en: Record<MessageKey, string> = {
  appName: 'GYST',
  tagline: 'Get Your Shit Together',
  on: 'On',
  off: 'Off',
  sitesTitle: 'Blocked sites',
  siteInput: 'e.g. youtube.com',
  add: 'Add',
  addCurrent: 'Current tab',
  remove: 'Remove',
  noSites: 'No sites blocked yet.',
  invalidSite: 'Invalid domain.',
  settingsTitle: 'Settings',
  popupMessageLabel: 'Message to turn off/remove',
  blockMessageLabel: 'Message on the block page',
  defaultPopupMessage: 'I really want this.',
  defaultBlockMessage: 'Get your shit together. This site is blocked.',
  save: 'Save',
  saved: 'Saved',
  language: 'Language',
  languageAuto: 'Automatic',
  confirmTitle: 'Really turn off?',
  confirmRemoveTitle: 'Really remove?',
  confirmHint: 'Type this sentence exactly, then wait 10 seconds.',
  confirmWait: 'Wait {seconds} s',
  confirmDo: 'Confirm',
  cancel: 'Cancel',
  mismatch: 'Wrong so far.',
  blockedTitle: 'Blocked',
  footer: 'All data stays local. No accounts, no network calls.',
};

const messages = { de, en } as const;

export type Locale = keyof typeof messages;

export function resolveLocale(language: Language, browserLanguage: string): Locale {
  if (language !== 'auto') return language;
  return browserLanguage.toLowerCase().startsWith('de') ? 'de' : 'en';
}

export function t(key: MessageKey, locale: Locale, vars: Record<string, string | number> = {}): string {
  return Object.entries(vars).reduce(
    (text, [name, value]) => text.replace(`{${name}}`, String(value)),
    messages[locale][key],
  );
}

export function defaultPopupMessage(locale: Locale): string {
  return t('defaultPopupMessage', locale);
}

export function defaultBlockMessage(locale: Locale): string {
  return t('defaultBlockMessage', locale);
}
