import { browser } from 'wxt/browser';
import { defaultBlockMessage, resolveLocale, t } from '../../src/i18n';
import { askCompanion } from '../../src/companion';
import { blockedTabsItem, readSettings } from '../../src/storage';
import { isFreeNow, syncNow } from '../../src/sync';

async function init() {
  const settings = await readSettings();
  const locale = resolveLocale(settings.language, browser.i18n.getUILanguage());
  document.documentElement.lang = locale;
  document.title = t('appName', locale);
  document.getElementById('title')!.textContent = t('blockedTitle', locale);
  document.getElementById('message')!.textContent =
    settings.blockMessage.trim() || defaultBlockMessage(locale);
}

// A partner grant or free window ends the block while this page is open: go back to the wanted page.
async function watchForFree() {
  const tabId = (await browser.tabs.getCurrent())?.id;
  if (tabId === undefined) return;
  const timer = setInterval(async () => {
    await syncNow();
    const companionFree = (await askCompanion({ type: 'check' }))?.free === true;
    if (!companionFree && !(await isFreeNow())) return;
    const url = (await blockedTabsItem.getValue())[tabId];
    if (!url) return;
    clearInterval(timer);
    location.replace(url);
  }, 3000);
}

void init();
void watchForFree();
