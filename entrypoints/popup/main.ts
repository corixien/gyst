import { browser } from 'wxt/browser';
import { askCompanion, type FreeWindow } from '../../src/companion';
import { normalizeDomain } from '../../src/blocklist';
import { matchesSentence } from '../../src/confirm';
import { defaultPopupMessage, resolveLocale, t, type Locale, type MessageKey } from '../../src/i18n';
import { normalizeSettings, type Settings, type UnlockMode } from '../../src/settings';
import { readSettings, settingsItem } from '../../src/storage';

const CONFIRM_SECONDS = 10;

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

let settings: Settings;
let locale: Locale;
let freeWindows: FreeWindow[] = [];

const toggle = $<HTMLButtonElement>('toggle');
const siteInput = $<HTMLInputElement>('siteInput');
const siteError = $<HTMLParagraphElement>('siteError');
const sitesList = $<HTMLUListElement>('sites');
const popupMessageInput = $<HTMLInputElement>('popupMessage');
const blockMessageInput = $<HTMLInputElement>('blockMessage');
const languageSelect = $<HTMLSelectElement>('language');
const unlockSelect = $<HTMLSelectElement>('unlock');
const saved = $<HTMLElement>('saved');
const dialog = $<HTMLDialogElement>('confirm');
const confirmForm = $<HTMLFormElement>('confirmForm');
const confirmInput = $<HTMLInputElement>('confirmInput');
const confirmOk = $<HTMLButtonElement>('confirmOk');
const confirmWait = $<HTMLParagraphElement>('confirmWait');
const confirmError = $<HTMLParagraphElement>('confirmError');
const freeList = $<HTMLUListElement>('free');
const freeFrom = $<HTMLInputElement>('freeFrom');
const freeTo = $<HTMLInputElement>('freeTo');
const freeError = $<HTMLParagraphElement>('freeError');
const freeOffline = $<HTMLParagraphElement>('freeOffline');

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

function renderFree() {
  freeList.replaceChildren(
    ...freeWindows.map((window, index) => {
      const item = document.createElement('li');
      const range = document.createElement('span');
      range.textContent = `${window.from} – ${window.to}`;
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'btn ghost small';
      remove.textContent = t('remove', locale);
      remove.onclick = () => saveFree(freeWindows.filter((_, i) => i !== index));
      item.append(range, remove);
      return item;
    }),
  );
  if (freeWindows.length === 0) {
    const empty = document.createElement('li');
    empty.className = 'empty';
    empty.textContent = t('freeEmpty', locale);
    freeList.append(empty);
  }
}

// The companion stores the windows, so they are read from and written to it.
async function loadFree() {
  const reply = await askCompanion({ type: 'getConfig' });
  freeOffline.hidden = reply !== null;
  freeWindows = reply?.config?.free_windows ?? [];
  renderFree();
}

async function saveFree(windows: FreeWindow[]): Promise<boolean> {
  const reply = await askCompanion({ type: 'setFreeWindows', windows });
  freeOffline.hidden = reply !== null;
  if (!reply?.ok) return false;
  freeWindows = windows;
  renderFree();
  return true;
}

const popupMessage = () => settings.popupMessage.trim() || defaultPopupMessage(locale);

// Turning off, removing a site, adding a free window or changing the unlock mode needs a 10 s wait
// and either the typed sentence or a partner code. Adding a site and enabling do not.
function askConfirm(title: string, required: string, onConfirm: () => Promise<unknown>) {
  const partner = settings.unlock === 'partner';
  let remaining = CONFIRM_SECONDS;
  const accepts = () => (partner ? /^\d{8}$/.test(confirmInput.value) : matchesSentence(confirmInput.value, required));

  $('confirmTitle').textContent = title;
  $('confirmHint').textContent = t(partner ? 'partnerCodeHint' : 'confirmHint', locale);
  $('confirmRequired').textContent = partner ? '' : required;
  $('confirmRequired').hidden = partner;
  confirmInput.value = '';
  confirmInput.inputMode = partner ? 'numeric' : 'text';
  confirmError.hidden = true;

  const updateState = () => {
    confirmOk.disabled = !(remaining === 0 && accepts());
    confirmWait.textContent = remaining > 0 ? t('confirmWait', locale, { seconds: remaining }) : '';
  };

  const timer = setInterval(() => {
    remaining = Math.max(0, remaining - 1);
    updateState();
    if (remaining === 0) clearInterval(timer);
  }, 1000);

  const submit = async () => {
    if (confirmOk.disabled) return;
    if (partner && !(await askCompanion({ type: 'verifyCode', code: confirmInput.value }))?.ok) {
      confirmError.hidden = false;
      return;
    }
    dialog.close();
    await onConfirm();
  };

  confirmInput.oninput = () => {
    confirmError.hidden = true;
    updateState();
  };
  // Enter confirms when allowed; it used to close the dialog and drop the typed text.
  confirmForm.onsubmit = (event) => {
    event.preventDefault();
    void submit();
  };
  confirmOk.onclick = () => void submit();
  $<HTMLButtonElement>('confirmCancel').onclick = () => dialog.close();
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

$<HTMLFormElement>('freeForm').onsubmit = (event) => {
  event.preventDefault();
  const from = freeFrom.value;
  const to = freeTo.value;
  const valid = from !== '' && to !== '' && from !== to;
  freeError.hidden = valid;
  if (!valid) return;
  askConfirm(t('confirmFreeTitle', locale), popupMessage(), async () => {
    if (await saveFree([...freeWindows, { from, to }])) {
      freeFrom.value = '';
      freeTo.value = '';
    }
  });
};

async function saveSettings() {
  await save({
    popupMessage: popupMessageInput.value.trim(),
    blockMessage: blockMessageInput.value.trim(),
    language: languageSelect.value as Settings['language'],
    unlock: unlockSelect.value as UnlockMode,
  });
  saved.hidden = false;
  setTimeout(() => (saved.hidden = true), 1500);
}

// Switching to the easier unlock mode must pass the current one, otherwise it is a bypass.
$<HTMLButtonElement>('save').onclick = () => {
  if (unlockSelect.value !== settings.unlock) {
    askConfirm(t('confirmUnlockTitle', locale), popupMessage(), saveSettings);
  } else {
    void saveSettings();
  }
};

async function init() {
  settings = await readSettings();
  popupMessageInput.value = settings.popupMessage;
  blockMessageInput.value = settings.blockMessage;
  languageSelect.value = settings.language;
  unlockSelect.value = settings.unlock;
  applyLocale();
  render();
  void loadFree();

  settingsItem.watch((value) => {
    settings = normalizeSettings(value);
    applyLocale();
    render();
    renderFree();
  });
}

void init();
