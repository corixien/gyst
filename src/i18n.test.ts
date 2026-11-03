import { describe, expect, it } from 'vitest';
import { resolveLocale, t } from './i18n';

describe('resolveLocale', () => {
  it('uses the explicit language when set', () => {
    expect(resolveLocale('en', 'de-DE')).toBe('en');
    expect(resolveLocale('de', 'en-US')).toBe('de');
  });

  it('follows the browser language on auto', () => {
    expect(resolveLocale('auto', 'de-DE')).toBe('de');
    expect(resolveLocale('auto', 'fr-FR')).toBe('en');
  });
});

describe('t', () => {
  it('interpolates variables', () => {
    expect(t('confirmWait', 'en', { seconds: 7 })).toBe('Wait 7 s');
    expect(t('confirmWait', 'de', { seconds: 7 })).toBe('Warte noch 7 s');
  });
});
