import { browser } from 'wxt/browser';
import { ApiError, DEFAULT_SERVER, createAccount, createInvite, putSettings } from '../../src/api';
import { normalizeDomain } from '../../src/blocklist';
import { matchesSentence } from '../../src/confirm';
import { defaultPopupMessage, resolveLocale, t, type Locale, type MessageKey } from '../../src/i18n';
import { gatedChanges } from '../../src/rules';
import type { FreeWindow } from '../../src/schedule';
import { normalizeSettings, type Settings } from '../../src/settings';
import { readSettings, settingsItem } from '../../src/storage';
import { accountItem, remoteItem, syncNow } from '../../src/sync';

const CONFIRM_SECONDS = 10;

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

let settings: Settings;
let locale: Locale;
let freeWindows: FreeWindow[] = [];
let grantUntil = 0;
let settingsUntil = 0;
let partners = 0;
let signedIn = false;

const toggle = $<HTMLButtonElement>('toggle');
const siteInput = $<HTMLInputElement>('siteInput');
const siteError = $<HTMLParagraphElement>('siteError');
const sitesList = $<HTMLUListElement>('sites');
const popupMessageInput = $<HTMLInputElement>('popupMessage');
const blockMessageInput = $<HTMLInputElement>('blockMessage');
const languageSelect = $<HTMLSelectElement>('language');
const saved = $<HTMLElement>('saved');
const dialog = $<HTMLDialogElement>('confirm');
const confirmForm = $<HTMLFormElement>('confirmForm');
const confirmInput = $<HTMLInputElement>('confirmInput');
const confirmOk = $<HTMLButtonElement>('confirmOk');
const confirmWait = $<HTMLParagraphElement>('confirmWait');
const confirmError = $<HTMLParagraphElement>('confirmError');
const freeList = $<HTMLUListElement>('free');
const freeDaysBox = $<HTMLDivElement>('freeDays');
const freeFrom = $<HTMLInputElement>('freeFrom');
const freeTo = $<HTMLInputElement>('freeTo');
const freeError = $<HTMLParagraphElement>('freeError');
const grantBox = $<HTMLDivElement>('grant');
const grantText = $<HTMLSpanElement>('grantText');
const grantNeeded = $<HTMLParagraphElement>('grantNeeded');
const syncState = $<HTMLParagraphElement>('syncState');
const partnersText = $<HTMLParagraphElement>('partners');
const inviteButton = $<HTMLButtonElement>('invite');
const inviteCode = $<HTMLElement>('inviteCode');
const accountStatus = $<HTMLParagraphElement>('accountStatus');
const accountForm = $<HTMLDivElement>('accountForm');
const serverUrl = $<HTMLInputElement>('serverUrl');
const tokenBox = $<HTMLDivElement>('tokenBox');
const tokenValue = $<HTMLElement>('tokenValue');

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

const popupMessage = () => settings.popupMessage.trim() || defaultPopupMessage(locale);
const nowSeconds = () => Date.now() / 1000;

function formatLeft(seconds: number): string {
  const units: [number, MessageKey, MessageKey][] = [
    [3600, 'unitHour', 'unitHours'],
    [60, 'unitMinute', 'unitMinutes'],
    [1, 'unitSecond', 'unitSeconds'],
  ];
  let rest = seconds;
  const parts: string[] = [];
  for (const [size, one, many] of units) {
    const n = Math.floor(rest / size);
    rest -= n * size;
    if (n > 0) parts.push(`${n} ${t(n === 1 ? one : many, locale)}`);
  }
  return parts.join(' ');
}

function renderGrant() {
  const now = nowSeconds();
  const parts: string[] = [];
  if (grantUntil > now) parts.push(t('grantLeft', locale, { time: formatLeft(Math.ceil(grantUntil - now)) }));
  if (settingsUntil > now) parts.push(t('settingsLeft', locale, { time: formatLeft(Math.ceil(settingsUntil - now)) }));
  grantBox.hidden = parts.length === 0;
  grantText.textContent = parts.join(' · ');
}

function renderSites() {
  sitesList.replaceChildren(
    ...settings.sites.map((site) => {
      const item = document.createElement('li');
      const name = document.createElement('span');
      name.textContent = site;
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'btn ghost small';
      remove.textContent = t('remove', locale);
      remove.onclick = () => change({ ...settings, sites: settings.sites.filter((s) => s !== site) }, freeWindows, t('confirmRemoveTitle', locale));
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

// Day 0 is Monday. 5 Jan 2026 was a Monday, so the names follow the UI language.
const weekdayName = (day: number, style: 'long' | 'short' = 'long') =>
  new Intl.DateTimeFormat(locale, { weekday: style }).format(new Date(2026, 0, 5 + day));

function renderFree() {
  const sorted = freeWindows
    .map((window, index) => ({ window, index }))
    .sort((a, b) => a.window.day - b.window.day || a.window.from.localeCompare(b.window.from));
  freeList.replaceChildren(
    ...sorted.map(({ window, index }) => {
      const item = document.createElement('li');
      const range = document.createElement('span');
      range.textContent = `${weekdayName(window.day)} ${window.from} – ${window.to}`;
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'btn ghost small';
      remove.textContent = t('remove', locale);
      remove.onclick = () => change(settings, freeWindows.filter((_, i) => i !== index), null);
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

function renderToggle() {
  toggle.textContent = t(settings.enabled ? 'on' : 'off', locale);
  toggle.classList.toggle('on', settings.enabled);
  toggle.setAttribute('aria-pressed', String(settings.enabled));
}

function renderAccount() {
  accountStatus.hidden = false;
  accountForm.hidden = signedIn;
  accountStatus.textContent = signedIn ? `${t('partnersCount', locale, { count: partners })}` : t('notSignedIn', locale);
  partnersText.textContent = signedIn ? t('partnersCount', locale, { count: partners }) : '';
  inviteButton.disabled = !signedIn;
}

// Reads the local copies that sync keeps up to date.
async function refresh() {
  const remote = await remoteItem.getValue();
  freeWindows = (remote.free_windows ?? []) as FreeWindow[];
  grantUntil = remote.grant_until ?? 0;
  settingsUntil = remote.settings_until ?? 0;
  partners = remote.partners ?? 0;
  signedIn = (await accountItem.getValue()) !== null;
  syncState.hidden = !signedIn || remote.synced !== false;
  settings = normalizeSettings(await settingsItem.getValue());
  renderToggle();
  renderSites();
  renderFree();
  renderGrant();
  renderAccount();
}

// Confirmation with typed sentence and 10 s wait. Only used when no partner exists for the account.
function askSentence(title: string, onConfirm: () => Promise<boolean>) {
  let remaining = CONFIRM_SECONDS;
  const required = popupMessage();
  const accepts = () => matchesSentence(confirmInput.value, required);

  $('confirmTitle').textContent = title;
  $('confirmRequired').textContent = required;
  confirmInput.value = '';
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
    dialog.close();
    await onConfirm();
  };
  confirmInput.oninput = () => {
    confirmError.hidden = true;
    updateState();
  };
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

// Every change goes through here. Loosening changes need a partner grant when a partner exists,
// otherwise the typed sentence. The server enforces the same rules.
// Changes run one after another: each starts from the state the previous one wrote.
let queued: Promise<void> = Promise.resolve();
function change(next: Settings, nextWindows: FreeWindow[], title: string | null): Promise<void> {
  queued = queued.then(() => applyChange(next, nextWindows, title));
  return queued;
}

async function applyChange(next: Settings, nextWindows: FreeWindow[], title: string | null): Promise<void> {
  const gated = gatedChanges(settings, next, freeWindows, nextWindows);
  const hasGrant = grantUntil > nowSeconds() || settingsUntil > nowSeconds();
  if (gated.length > 0 && partners > 0 && !hasGrant) {
    grantNeeded.hidden = false;
    return;
  }
  const apply = async () => {
    grantNeeded.hidden = true;
    const account = await accountItem.getValue();
    if (account) {
      try {
        await putSettings(account.server, account.token, next, nextWindows);
      } catch (err) {
        if (err instanceof ApiError && err.status === 403) {
          grantNeeded.hidden = false;
          return;
        }
        syncState.hidden = false;
        return;
      }
      settings = next;
      freeWindows = nextWindows;
      await syncNow();
    } else {
      await settingsItem.setValue(next);
      await remoteItem.setValue({ ...(await remoteItem.getValue()), free_windows: nextWindows });
    }
    await refresh();
    saved.hidden = false;
    setTimeout(() => (saved.hidden = true), 1500);
  };
  if (gated.length > 0 && partners === 0 && !hasGrant && title) {
    askSentence(title, async () => {
      await apply();
      return true;
    });
    return;
  }
  await apply();
}

toggle.onclick = () => {
  if (settings.enabled) {
    void change({ ...settings, enabled: false }, freeWindows, t('confirmTitle', locale));
  } else {
    void change({ ...settings, enabled: true }, freeWindows, null);
  }
};

$<HTMLFormElement>('siteForm').onsubmit = (event) => {
  event.preventDefault();
  const domain = normalizeDomain(siteInput.value);
  siteError.hidden = domain !== null;
  if (domain === null) return;
  siteInput.value = '';
  if (!settings.sites.includes(domain)) void change({ ...settings, sites: [...settings.sites, domain] }, freeWindows, null);
};

$<HTMLButtonElement>('addCurrent').onclick = async () => {
  const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
  const domain = normalizeDomain(tab?.url ?? '');
  siteError.hidden = domain !== null;
  if (domain === null) return;
  if (!settings.sites.includes(domain)) void change({ ...settings, sites: [...settings.sites, domain] }, freeWindows, null);
};

$<HTMLFormElement>('freeForm').onsubmit = (event) => {
  event.preventDefault();
  const days = [...freeDaysBox.querySelectorAll<HTMLInputElement>('input:checked')].map((box) => Number(box.value));
  const from = freeFrom.value;
  const to = freeTo.value;
  const valid = days.length > 0 && from !== '' && to !== '' && from !== to;
  freeError.textContent = days.length === 0 ? t('freeNoDay', locale) : t('freeInvalid', locale);
  freeError.hidden = valid;
  if (!valid) return;
  const windows = [...freeWindows, ...days.map((day) => ({ day, from, to }))];
  void change(settings, windows, t('confirmFreeTitle', locale)).then(() => {
    freeFrom.value = '';
    freeTo.value = '';
    freeDaysBox.querySelectorAll('input').forEach((box) => (box.checked = false));
  });
};

$<HTMLButtonElement>('save').onclick = () => {
  const next: Settings = {
    ...settings,
    popupMessage: popupMessageInput.value.trim(),
    blockMessage: blockMessageInput.value.trim(),
    language: languageSelect.value as Settings['language'],
  };
  void change(next, freeWindows, t('confirmSettingsTitle', locale));
};

inviteButton.onclick = async () => {
  const account = await accountItem.getValue();
  if (!account) return;
  try {
    const { code } = await createInvite(account.server, account.token);
    inviteCode.textContent = code;
    inviteCode.hidden = false;
    inviteCode.onclick = () => void navigator.clipboard?.writeText(code);
  } catch {
    syncState.hidden = false;
  }
};

$<HTMLButtonElement>('createAccount').onclick = async () => {
  const server = serverUrl.value.trim() || DEFAULT_SERVER;
  try {
    const created = await createAccount(server);
    await accountItem.setValue({ server, token: created.token, accountId: created.account_id });
    tokenValue.textContent = created.token;
    tokenBox.hidden = false;
  } catch {
    syncState.hidden = false;
  }
};

$<HTMLButtonElement>('connect').onclick = async () => {
  const token = $<HTMLInputElement>('connectToken').value.trim();
  if (!token) return;
  const server = serverUrl.value.trim() || DEFAULT_SERVER;
  await accountItem.setValue({ server, token, accountId: '' });
  await syncNow();
  await refresh();
};

$<HTMLButtonElement>('tokenSaved').onclick = async () => {
  tokenBox.hidden = true;
  tokenValue.textContent = '';
  await refresh();
};

async function init() {
  settings = await readSettings();
  popupMessageInput.value = settings.popupMessage;
  blockMessageInput.value = settings.blockMessage;
  languageSelect.value = settings.language;
  serverUrl.value = (await accountItem.getValue())?.server ?? DEFAULT_SERVER;
  applyLocale();
  freeDaysBox.replaceChildren(
    ...[0, 1, 2, 3, 4, 5, 6].map((day) => {
      const label = document.createElement('label');
      const box = document.createElement('input');
      box.type = 'checkbox';
      box.value = String(day);
      label.append(box, weekdayName(day, 'short'));
      return label;
    }),
  );
  await syncNow();
  await refresh();
  setInterval(renderGrant, 1000);
  setInterval(() => void syncNow().then(refresh), 10_000);
  settingsItem.watch(() => void refresh());
  remoteItem.watch(() => void refresh());
}

void init();
