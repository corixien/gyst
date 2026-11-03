import { browser } from 'wxt/browser';
import { defaultBlockMessage, resolveLocale, t } from '../../src/i18n';
import { readSettings } from '../../src/storage';

async function init() {
  const settings = await readSettings();
  const locale = resolveLocale(settings.language, browser.i18n.getUILanguage());
  document.documentElement.lang = locale;
  document.title = t('appName', locale);
  document.getElementById('title')!.textContent = t('blockedTitle', locale);
  document.getElementById('message')!.textContent =
    settings.blockMessage.trim() || defaultBlockMessage(locale);
}

void init();
