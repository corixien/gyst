import { browser } from 'wxt/browser';
import {
  ApiError,
  DEFAULT_SERVER,
  addSite,
  claimDevice,
  fetchPartners,
  putSettings,
  removePartner,
  setEnabled,
  type PartnerInfo,
} from '../../src/api';
import { normalizeDomain } from '../../src/blocklist';
import { matchesSentence } from '../../src/confirm';
import { defaultPopupMessage, resolveLocale, t, type Locale, type MessageKey } from '../../src/i18n';
import type { FreeWindow } from '../../src/schedule';
import { normalizeSettings, type Language, type Settings } from '../../src/settings';
import { settingsItem } from '../../src/storage';
import { accountItem, remoteItem, syncNow } from '../../src/sync';

const CONFIRM_SECONDS = 10;

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

// Authoritative copy (last server state). Edits happen in `draft` and only reach the server on Save.
let settings: Settings;
let locale: Locale;
let freeWindows: FreeWindow[] = [];
let grantUntil = 0;
let settingsUntil = 0;
let partners = 0;

interface Draft {
  displayName: string;
  popupMessage: string;
  blockMessage: string;
  language: Language;
  sites: string[];
  free: FreeWindow[];
}
let draft: Draft = { displayName: '', popupMessage: '', blockMessage: '', language: 'auto', sites: [], free: [] };
let ready = false; // set once the first draft is built from the saved state

const toggle = $<HTMLButtonElement>('toggle');
const siteInput = $<HTMLInputElement>('siteInput');
const siteError = $<HTMLParagraphElement>('siteError');
const sitesList = $<HTMLUListElement>('sites');
const displayNameInput = $<HTMLInputElement>('displayName');
const popupMessageInput = $<HTMLInputElement>('popupMessage');
const popupField = $<HTMLLabelElement>('popupField');
const blockMessageInput = $<HTMLInputElement>('blockMessage');
const languageSelect = $<HTMLSelectElement>('language');
const ruleHint = $<HTMLParagraphElement>('ruleHint');
const saveButton = $<HTMLButtonElement>('save');
const saveHint = $<HTMLElement>('saveHint');
const saved = $<HTMLElement>('saved');
const dialog = $<HTMLDialogElement>('confirm');
const confirmForm = $<HTMLFormElement>('confirmForm');
const confirmInput = $<HTMLInputElement>('confirmInput');
const confirmOk = $<HTMLButtonElement>('confirmOk');
const confirmWait = $<HTMLParagraphElement>('confirmWait');
const freeList = $<HTMLUListElement>('free');
const freeDaysBox = $<HTMLDivElement>('freeDays');
const freeFrom = $<HTMLInputElement>('freeFrom');
const freeTo = $<HTMLInputElement>('freeTo');
const freeError = $<HTMLParagraphElement>('freeError');
const grantBox = $<HTMLDivElement>('grant');
const grantText = $<HTMLSpanElement>('grantText');
const notice = $<HTMLParagraphElement>('notice');
const syncState = $<HTMLParagraphElement>('syncState');
const partnerList = $<HTMLUListElement>('partnerList');
const deviceBox = $<HTMLDetailsElement>('device');
const connectHint = $<HTMLParagraphElement>('connectHint');
const showTokenButton = $<HTMLButtonElement>('showToken');
const tokenBox = $<HTMLDivElement>('tokenBox');
const tokenValue = $<HTMLElement>('tokenValue');
const connectToken = $<HTMLInputElement>('connectToken');

const nowSeconds = () => Date.now() / 1000;
const popupMessage = () => settings.popupMessage.trim() || defaultPopupMessage(locale);
const grantActive = () => grantUntil > nowSeconds();
const settingsOpen = () => settingsUntil > nowSeconds();
// On = enabled and not paused by a grant. A running grant shows Off; tapping it turns the block back on.
const isOn = () => settings.enabled && !grantActive();

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

function say(text: string | null, error = true) {
  notice.hidden = text === null;
  notice.className = error ? 'error' : 'ok';
  notice.textContent = text ?? '';
}

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

function dirty(): boolean {
  return (
    draft.displayName !== settings.displayName ||
    draft.popupMessage !== settings.popupMessage ||
    draft.blockMessage !== settings.blockMessage ||
    draft.language !== settings.language ||
    JSON.stringify(draft.sites) !== JSON.stringify(settings.sites) ||
    JSON.stringify(draft.free) !== JSON.stringify(freeWindows)
  );
}

function renderToggle() {
  const paused = settings.enabled && grantActive();
  const on = isOn();
  toggle.textContent = paused ? t('pausedByGrant', locale) : t(on ? 'on' : 'off', locale);
  toggle.classList.toggle('on', on);
  toggle.classList.toggle('paused', paused);
  toggle.setAttribute('aria-pressed', String(on));
  toggle.title = paused ? t('pausedHint', locale) : '';
}

// Which rule applies is shown in the settings. The typed sentence only exists without partners.
function renderRules() {
  const withPartner = partners > 0;
  ruleHint.textContent = t(withPartner ? 'ruleWithPartner' : 'ruleNoPartner', locale);
  popupField.hidden = withPartner;
}

function renderDraft() {
  displayNameInput.value = draft.displayName;
  popupMessageInput.value = draft.popupMessage;
  blockMessageInput.value = draft.blockMessage;
  languageSelect.value = draft.language;
  sitesList.replaceChildren(
    ...draft.sites.map((site) => {
      const item = document.createElement('li');
      const name = document.createElement('span');
      name.textContent = site;
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'btn ghost small';
      remove.textContent = t('remove', locale);
      remove.onclick = () => {
        draft = { ...draft, sites: draft.sites.filter((s) => s !== site) };
        renderDraft();
      };
      item.append(name, remove);
      return item;
    }),
  );
  if (draft.sites.length === 0) {
    const empty = document.createElement('li');
    empty.className = 'empty';
    empty.textContent = t('noSites', locale);
    sitesList.append(empty);
  }
  const sorted = draft.free
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
      remove.onclick = () => {
        draft = { ...draft, free: draft.free.filter((_, i) => i !== index) };
        renderDraft();
      };
      item.append(range, remove);
      return item;
    }),
  );
  if (draft.free.length === 0) {
    const empty = document.createElement('li');
    empty.className = 'empty';
    empty.textContent = t('freeEmpty', locale);
    freeList.append(empty);
  }
  saveHint.hidden = !dirty();
  saveHint.textContent = t('unsaved', locale);
}

// Day 0 is Monday. 5 Jan 2026 was a Monday, so the names follow the UI language.
const weekdayName = (day: number, style: 'long' | 'short' = 'long') =>
  new Intl.DateTimeFormat(locale, { weekday: style }).format(new Date(2026, 0, 5 + day));

// Partners of this account. Each one can be removed; removing a partner needs a running grant.
async function loadPartners() {
  const account = await accountItem.getValue();
  if (!account) return;
  try {
    const { partners: list } = await fetchPartners(account.server, account.token);
    renderPartners(list);
  } catch {
    syncState.hidden = false;
  }
}

function renderPartners(list: PartnerInfo[]) {
  partnerList.replaceChildren(
    ...list.map((partner) => {
      const item = document.createElement('li');
      const name = document.createElement('span');
      name.textContent = partner.name;
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'btn ghost small';
      remove.textContent = t('remove', locale);
      remove.onclick = () => void removePartnerNow(partner.id);
      item.append(name, remove);
      return item;
    }),
  );
  if (list.length === 0) {
    const empty = document.createElement('li');
    empty.className = 'empty';
    empty.textContent = t('noPartners', locale);
    partnerList.append(empty);
  }
}

async function removePartnerNow(partnerId: string) {
  const account = await accountItem.getValue();
  if (!account) return;
  try {
    await removePartner(account.server, account.token, partnerId);
  } catch (err) {
    say(err instanceof ApiError && err.status === 403 ? t('grantRequired', locale) : t('errorGeneric', locale));
    return;
  }
  say(null);
  await syncNow();
  await refreshAuthoritative();
}

// Reads the local copies that sync keeps up to date. The draft is left alone.
async function refreshAuthoritative() {
  const remote = await remoteItem.getValue();
  settings = normalizeSettings(await settingsItem.getValue());
  freeWindows = (remote.free_windows ?? []) as FreeWindow[];
  grantUntil = remote.grant_until ?? 0;
  settingsUntil = remote.settings_until ?? 0;
  partners = remote.partners ?? 0;
  const signedIn = (await accountItem.getValue()) !== null;
  syncState.hidden = !signedIn || remote.synced !== false;
  connectHint.hidden = signedIn;
  if (!signedIn) deviceBox.open = true;
  if (signedIn) void loadPartners();
  renderToggle();
  renderRules();
  renderGrant();
  if (ready) renderDraft();
}

// Confirmation with typed sentence and 10 s wait. Only used when no partner exists.
function askSentence(title: string, onConfirm: () => Promise<void>) {
  let remaining = CONFIRM_SECONDS;
  const required = popupMessage();
  const accepts = () => matchesSentence(confirmInput.value, required);

  $('confirmTitle').textContent = title;
  $('confirmRequired').textContent = required;
  confirmInput.value = '';
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
  confirmInput.oninput = updateState;
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

function readDraftInputs() {
  draft = {
    ...draft,
    displayName: displayNameInput.value.trim(),
    popupMessage: popupMessageInput.value.trim(),
    blockMessage: blockMessageInput.value.trim(),
    language: languageSelect.value as Language,
  };
}

// Save: the whole draft in one request. With a partner this needs a grant; a settings grant is used up here.
async function save() {
  readDraftInputs();
  const account = await accountItem.getValue();
  const next: Settings = {
    ...settings,
    displayName: draft.displayName,
    popupMessage: draft.popupMessage,
    blockMessage: draft.blockMessage,
    language: draft.language,
    sites: draft.sites,
  };
  if (!account) {
    await settingsItem.setValue(next);
    await remoteItem.setValue({ ...(await remoteItem.getValue()), free_windows: draft.free });
    await refreshAuthoritative();
    flashSaved();
    return;
  }
  if (partners > 0 && !grantActive() && !settingsOpen()) {
    say(t('saveNeedsGrant', locale));
    return;
  }
  const write = async () => {
    try {
      await putSettings(account.server, account.token, next, draft.free);
    } catch (err) {
      say(err instanceof ApiError && err.status === 403 ? t('saveNeedsGrant', locale) : t('errorGeneric', locale));
      return;
    }
    say(null);
    await syncNow();
    await refreshAuthoritative();
    flashSaved();
  };
  if (partners === 0) {
    askSentence(t('confirmSettingsTitle', locale), write);
  } else {
    await write();
  }
}

function flashSaved() {
  saved.hidden = false;
  setTimeout(() => (saved.hidden = true), 1500);
}

saveButton.onclick = () => void save();

// Tapping while a grant pauses the block turns it back on at once and ends the grant.
// Turning off needs a grant with partners, and the typed sentence without partners.
toggle.onclick = async () => {
  const account = await accountItem.getValue();
  const turnOn = !isOn();
  if (!account) {
    const apply = async () => {
      await settingsItem.setValue({ ...settings, enabled: turnOn });
      await refreshAuthoritative();
    };
    if (turnOn) return void apply();
    askSentence(t('confirmTitle', locale), apply);
    return;
  }
  const apply = async () => {
    try {
      await setEnabled(account.server, account.token, turnOn);
    } catch (err) {
      say(err instanceof ApiError && err.status === 403 ? t('grantRequired', locale) : t('errorGeneric', locale));
      return;
    }
    say(null);
    await syncNow();
    await refreshAuthoritative();
  };
  if (turnOn || partners > 0) return void apply();
  askSentence(t('confirmTitle', locale), apply);
};

$<HTMLFormElement>('siteForm').onsubmit = async (event) => {
  event.preventDefault();
  const domain = normalizeDomain(siteInput.value);
  siteError.hidden = domain !== null;
  if (domain === null) return;
  siteInput.value = '';
  await addSiteNow(domain);
};

$<HTMLButtonElement>('addCurrent').onclick = async () => {
  const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
  const domain = normalizeDomain(tab?.url ?? '');
  siteError.hidden = domain !== null;
  if (domain === null) return;
  await addSiteNow(domain);
};

// Adding a site is free and happens at once, also with partners.
async function addSiteNow(domain: string) {
  const account = await accountItem.getValue();
  if (account) {
    try {
      await addSite(account.server, account.token, domain);
    } catch {
      say(t('errorGeneric', locale));
      return;
    }
    await syncNow();
  } else {
    await settingsItem.setValue({ ...settings, sites: [...settings.sites, domain] });
  }
  draft = { ...draft, sites: draft.sites.includes(domain) ? draft.sites : [...draft.sites, domain] };
  await refreshAuthoritative();
}

$<HTMLFormElement>('freeForm').onsubmit = (event) => {
  event.preventDefault();
  const days = [...freeDaysBox.querySelectorAll<HTMLInputElement>('input:checked')].map((box) => Number(box.value));
  const from = freeFrom.value;
  const to = freeTo.value;
  const valid = days.length > 0 && from !== '' && to !== '' && from !== to;
  freeError.textContent = days.length === 0 ? t('freeNoDay', locale) : t('freeInvalid', locale);
  freeError.hidden = valid;
  if (!valid) return;
  draft = { ...draft, free: [...draft.free, ...days.map((day) => ({ day, from, to }))] };
  freeFrom.value = '';
  freeTo.value = '';
  freeDaysBox.querySelectorAll('input').forEach((box) => (box.checked = false));
  renderDraft();
};

for (const input of [displayNameInput, popupMessageInput, blockMessageInput, languageSelect]) {
  input.addEventListener('input', () => {
    readDraftInputs();
    renderDraft();
  });
}

showTokenButton.onclick = async () => {
  const account = await accountItem.getValue();
  if (!account) return;
  tokenValue.textContent = account.token;
  tokenBox.hidden = false;
};

// Connects this device with a code the partner issued. The device token then replaces any local-only state.
$<HTMLButtonElement>('connect').onclick = async () => {
  const code = connectToken.value.trim();
  if (!code) return;
  try {
    const claimed = await claimDevice(DEFAULT_SERVER, code);
    await accountItem.setValue({ server: DEFAULT_SERVER, token: claimed.token, accountId: claimed.account_id });
    connectToken.value = '';
    await syncNow();
    await refreshAuthoritative();
  } catch (err) {
    say(err instanceof ApiError && err.status === 400 ? t('errorCode', locale) : t('errorGeneric', locale));
  }
};

// Draft starts as a copy of the last saved state. Reopening the popup therefore discards unsaved edits.
function fromSettings(): Draft {
  return {
    displayName: settings.displayName,
    popupMessage: settings.popupMessage,
    blockMessage: settings.blockMessage,
    language: settings.language,
    sites: [...settings.sites],
    free: [...freeWindows],
  };
}

async function init() {
  settings = normalizeSettings(await settingsItem.getValue());
  draft = fromSettings();
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
  await refreshAuthoritative();
  draft = fromSettings();
  ready = true;
  renderDraft();
  setInterval(renderGrant, 1000);
  setInterval(() => void syncNow().then(refreshAuthoritative), 10_000);
  settingsItem.watch(() => void refreshAuthoritative());
  remoteItem.watch(() => void refreshAuthoritative());
}

void init();
