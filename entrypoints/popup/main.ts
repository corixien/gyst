import { browser } from 'wxt/browser';
import { normalizeDomain } from '../../src/blocklist';
import { matchesSentence } from '../../src/confirm';
import { defaultPopupMessage, resolveLocale, t, type Locale, type MessageKey } from '../../src/i18n';
import { normalizeSettings, type Settings } from '../../src/settings';
import { readSettings, settingsItem } from '../../src/storage';

const CONFIRM_SECONDS = 10;

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

let settings: Settings;
let locale: Locale;

const toggle = $<HTMLButtonElement>('toggle');
const siteInput = $<HTMLInputElement>('siteInput');
const siteError = $<HTMLParagraphElement>('siteError');
const sitesList = $<HTMLUListElement>('sites');
const popupMessageInput = $<HTMLInputElement>('popupMessage');
const blockMessageInput = $<HTMLInputElement>('blockMessage');
const languageSelect = $<HTMLSelectElement>('language');
const saved = $<HTMLElement>('saved');
const dialog = $<HTMLDialogElement>('confirm');
const confirmInput = $<HTMLInputElement>('confirmInput');
const confirmOk = $<HTMLButtonElement>('confirmOk');
const confirmWait = $<HTMLParagraphElement>('confirmWait');

const save = (patch: Partial<Settings>) => settingsItem.setValue({ ...settings, ...patch });

function applyLocale() {
  locale = resolveLocale(settings.language, browser.i18n.getUILanguage());
  document.documentElement.lang = locale;
  document.querySelectorAll<HTMLElement>('[data-i18n]').forEach((el) => {
    el.textContent = t(el.dataset.i18n as MessageKey, locale);
  });
  document.querySelectorAll<HTMLInputElement>('[data-i18n-placeholder]').forEach((el) => {
    el.placeholder = t(el.dataset.i18nPlaceholder as MessageKey, locale);
  });
}

function render() {
  toggle.textContent = t(settings.enabled ? 'on' : 'off', locale);
  toggle.classList.toggle('on', settings.enabled);
  toggle.setAttribute('aria-pressed', String(settings.enabled));

  sitesList.replaceChildren(
    ...settings.sites.map((site) => {
      const item = document.createElement('li');
      const name = document.createElement('span');
      name.textContent = site;
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'btn ghost small';
      remove.textContent = t('remove', locale);
      remove.onclick = () => askConfirm(t('confirmRemoveTitle', locale), popupMessage(), () => save({ sites: settings.sites.filter((s) => s !== site) }));
      item.append(name, remove);
      return item;
    }),
  );
  if (settings.sites.length === 0) {
    const empty = document.createElement('li');
    empty.className = 'empty';
    empty.textContent = t('noSites', locale);
    sitesList.append(empty);
  }
}

const popupMessage = () => settings.popupMessage.trim() || defaultPopupMessage(locale);

// Turning off or removing a site needs the typed sentence and a 10 s wait. Adding and enabling do not.
function askConfirm(title: string, required: string, onConfirm: () => Promise<unknown>) {
  let remaining = CONFIRM_SECONDS;
  $('confirmTitle').textContent = title;
  $('confirmRequired').textContent = required;
  confirmInput.value = '';

  const updateState = () => {
    confirmOk.disabled = !(remaining === 0 && matchesSentence(confirmInput.value, required));
    confirmWait.textContent = remaining > 0 ? t('confirmWait', locale, { seconds: remaining }) : '';
  };

  const timer = setInterval(() => {
    remaining = Math.max(0, remaining - 1);
    updateState();
    if (remaining === 0) clearInterval(timer);
  }, 1000);

  confirmInput.oninput = updateState;
  $<HTMLButtonElement>('confirmCancel').onclick = () => dialog.close();
  confirmOk.onclick = async () => {
    dialog.close();
    await onConfirm();
  };
  dialog.onclose = () => clearInterval(timer);

  updateState();
  dialog.showModal();
  confirmInput.focus();
}

toggle.onclick = () => {
  if (settings.enabled) {
    askConfirm(t('confirmTitle', locale), popupMessage(), () => save({ enabled: false }));
  } else {
    save({ enabled: true });
  }
};

function showSiteError(show: boolean) {
  siteError.hidden = !show;
}

$<HTMLFormElement>('siteForm').onsubmit = async (event) => {
  event.preventDefault();
  const domain = normalizeDomain(siteInput.value);
  showSiteError(domain === null);
  if (domain === null) return;
  siteInput.value = '';
  if (!settings.sites.includes(domain)) await save({ sites: [...settings.sites, domain] });
};

$<HTMLButtonElement>('addCurrent').onclick = async () => {
  const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
  const domain = normalizeDomain(tab?.url ?? '');
  showSiteError(domain === null);
  if (domain === null) return;
  if (!settings.sites.includes(domain)) await save({ sites: [...settings.sites, domain] });
};

$<HTMLButtonElement>('save').onclick = async () => {
  await save({
    popupMessage: popupMessageInput.value.trim(),
    blockMessage: blockMessageInput.value.trim(),
    language: languageSelect.value as Settings['language'],
  });
  saved.hidden = false;
  setTimeout(() => (saved.hidden = true), 1500);
};

async function init() {
  settings = await readSettings();
  popupMessageInput.value = settings.popupMessage;
  blockMessageInput.value = settings.blockMessage;
  languageSelect.value = settings.language;
  applyLocale();
  render();

  settingsItem.watch((value) => {
    settings = normalizeSettings(value);
    applyLocale();
    render();
  });
}

void init();
