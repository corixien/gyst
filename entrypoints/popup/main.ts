import { browser } from 'wxt/browser';
import {
  ApiError,
  DEFAULT_SERVER,
  addSite,
  claimDevice,
  fetchPartners,
  putSettings,
  setOwnerName,
  removePartner,
  setEnabled,
  type PartnerInfo,
} from '../../src/api';
import { normalizeDomain } from '../../src/blocklist';
import { matchesSentence } from '../../src/confirm';
import { defaultPopupMessage, resolveLocale, t, type Locale, type MessageKey } from '../../src/i18n';
import type { FreeWindow } from '../../src/schedule';
import { normalizeSettings, type Draft, type Language, type Settings } from '../../src/settings';
import { draftItem, settingsItem } from '../../src/storage';
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

// Unsaved edits live in `draft` and in storage (draftItem), so they survive closing the popup.
let draft: Draft = { popupMessage: '', blockMessage: '', language: 'auto', sites: [], free: [] };
let ready = false; // set once the first draft is built from the saved state

const toggle = $<HTMLButtonElement>('toggle');
const siteInput = $<HTMLInputElement>('siteInput');
const siteError = $<HTMLParagraphElement>('siteError');
const sitesList = $<HTMLUListElement>('sites');
const popupMessageInput = $<HTMLInputElement>('popupMessage');
const popupField = $<HTMLLabelElement>('popupField');
const blockMessageInput = $<HTMLInputElement>('blockMessage');
const languageSelect = $<HTMLSelectElement>('language');
const ruleHint = $<HTMLParagraphElement>('ruleHint');
const saveButton = $<HTMLButtonElement>('save');
const saveHint = $<HTMLElement>('saveHint');
const resetDraftButton = $<HTMLButtonElement>('resetDraft');
const sitesNote = $<HTMLParagraphElement>('sitesNote');
const freeNote = $<HTMLParagraphElement>('freeNote');
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
const toggleError = $<HTMLParagraphElement>('toggleError');
const saveError = $<HTMLParagraphElement>('saveError');
const siteServerError = $<HTMLParagraphElement>('siteServerError');
const partnerError = $<HTMLParagraphElement>('partnerError');
const connectError = $<HTMLParagraphElement>('connectError');
const nameBox = $<HTMLElement>('nameBox');
const nameInput = $<HTMLInputElement>('ownerName');
const nameStatus = $<HTMLParagraphElement>('nameStatus');
const syncState = $<HTMLParagraphElement>('syncState');
const partnerList = $<HTMLUListElement>('partnerList');
const deviceBox = $<HTMLDetailsElement>('device');
const connectHint = $<HTMLParagraphElement>('connectHint');
const showTokenButton = $<HTMLButtonElement>('showToken');
const tokenBox = $<HTMLDivElement>('tokenBox');
const tokenValue = $<HTMLElement>('tokenValue');
const connectToken = $<HTMLInputElement>('connectToken');
const connectPartner = $<HTMLInputElement>('connectPartner');

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

// Errors show right next to the control that failed. Null clears.
function showError(el: HTMLElement, text: string | null) {
  el.hidden = !text;
  el.textContent = text ?? '';
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

const pendingSites = () => settings.sites.filter((site) => !draft.sites.includes(site));
const addedWindows = () => draft.free.filter((w) => !freeWindows.some((f) => sameWindow(f, w)));
const removedWindows = () => freeWindows.filter((f) => !draft.free.some((d) => sameWindow(d, f)));

type TextKey = 'popupMessage' | 'blockMessage' | 'language';
const fieldInputs: Record<TextKey, HTMLInputElement | HTMLSelectElement> = {
  popupMessage: popupMessageInput,
  blockMessage: blockMessageInput,
  language: languageSelect,
};

// Every edit stays visible: changed fields and list rows are yellow, and each has a button back to the saved value.
function renderDraft() {
  popupMessageInput.value = draft.popupMessage;
  blockMessageInput.value = draft.blockMessage;
  languageSelect.value = draft.language;
  for (const key of Object.keys(fieldInputs) as TextKey[]) {
    const changed = draft[key] !== settings[key];
    fieldInputs[key].classList.toggle('changed', changed);
    document.querySelector<HTMLButtonElement>(`[data-reset="${key}"]`)!.hidden = !changed;
  }
  renderSites();
  renderFree();
  renderNotes();
  void draftItem.setValue(dirty() ? draft : null);
}

function row(text: string, pending: boolean, button: string, onClick: () => void): HTMLLIElement {
  const item = document.createElement('li');
  if (pending) item.classList.add('pending');
  const label = document.createElement('span');
  label.textContent = text;
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'btn ghost small';
  btn.textContent = button;
  btn.onclick = onClick;
  item.append(label, btn);
  return item;
}

function emptyRow(text: string): HTMLLIElement {
  const item = document.createElement('li');
  item.className = 'empty';
  item.textContent = text;
  return item;
}

function renderSites() {
  const items = [
    ...draft.sites.map((site) => row(site, !settings.sites.includes(site), t('remove', locale), () => {
      draft = { ...draft, sites: draft.sites.filter((s) => s !== site) };
      renderDraft();
    })),
    ...pendingSites().map((site) => row(site, true, t('undo', locale), () => {
      draft = { ...draft, sites: [...draft.sites, site] };
      renderDraft();
    })),
  ];
  sitesList.replaceChildren(...(items.length ? items : [emptyRow(t('noSites', locale))]));
}

const weekdayOrder = (a: FreeWindow, b: FreeWindow) => a.day - b.day || a.from.localeCompare(b.from);

function renderFree() {
  const window = (w: FreeWindow) => `${weekdayName(w.day)} ${w.from} – ${w.to}`;
  const items = [
    ...[...draft.free].sort(weekdayOrder).map((w) => {
      const pending = !freeWindows.some((f) => sameWindow(f, w));
      return row(window(w), pending, t('remove', locale), () => {
        draft = { ...draft, free: draft.free.filter((x) => !sameWindow(x, w)) };
        renderDraft();
      });
    }),
    ...removedWindows().sort(weekdayOrder).map((w) => row(window(w), true, t('undo', locale), () => {
      draft = { ...draft, free: [...draft.free, w] };
      renderDraft();
    })),
  ];
  freeList.replaceChildren(...(items.length ? items : [emptyRow(t('freeEmpty', locale))]));
}

// With partners, Save needs a grant (time or one-time settings grant). Until then the edits stay as drafts.
function renderNotes() {
  const locked = partners > 0 && !grantActive() && !settingsOpen();
  const dirtyNow = dirty();
  sitesNote.hidden = !(locked && pendingSites().length > 0);
  sitesNote.textContent = t('needsGrantNote', locale);
  freeNote.hidden = !(locked && addedWindows().length > 0);
  freeNote.textContent = t('needsGrantNote', locale);
  saveHint.hidden = !dirtyNow;
  saveHint.textContent = locked ? t('draftNeedsGrant', locale) : t('unsaved', locale);
  resetDraftButton.hidden = !dirtyNow;
}

resetDraftButton.onclick = () => {
  draft = fromSettings();
  renderDraft();
};

for (const key of Object.keys(fieldInputs) as TextKey[]) {
  document.querySelector<HTMLButtonElement>(`[data-reset="${key}"]`)!.onclick = () => {
    draft = { ...draft, [key]: settings[key] };
    renderDraft();
  };
}

const sameWindow = (a: FreeWindow, b: FreeWindow) => a.day === b.day && a.from === b.from && a.to === b.to;

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
    showError(partnerError, err instanceof ApiError && err.status === 403 ? t('grantRequired', locale) : t('errorGeneric', locale));
    return;
  }
  showError(partnerError, null);
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
  deviceBox.hidden = partners > 0; // the device form only shows while no partner is connected
  const signedIn = (await accountItem.getValue()) !== null;
  syncState.hidden = !signedIn || remote.synced !== false;
  connectHint.hidden = signedIn;
  nameBox.hidden = !signedIn;
  if (document.activeElement !== nameInput) nameInput.value = remote.owner_name ?? '';
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
    showError(saveError, t('saveNeedsGrant', locale));
    return;
  }
  const write = async () => {
    try {
      await putSettings(account.server, account.token, next, draft.free);
    } catch (err) {
      showError(saveError, err instanceof ApiError && err.status === 403 ? t('saveNeedsGrant', locale) : t('errorGeneric', locale));
      return;
    }
    showError(saveError, null);
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
      showError(toggleError, err instanceof ApiError && err.status === 403 ? t('grantRequired', locale) : t('errorGeneric', locale));
      return;
    }
    showError(toggleError, null);
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
      showError(siteServerError, t('errorGeneric', locale));
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

for (const input of [popupMessageInput, blockMessageInput, languageSelect]) {
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
// Owner name: no Save button. Saved on change, shown to every partner.
nameInput.addEventListener('change', async () => {
  const account = await accountItem.getValue();
  if (!account) return;
  nameStatus.hidden = false;
  try {
    await setOwnerName(account.server, account.token, nameInput.value.trim());
    nameStatus.className = 'ok';
    nameStatus.textContent = t('nameSaved', locale);
    await syncNow();
  } catch {
    nameStatus.className = 'error';
    nameStatus.textContent = t('errorGeneric', locale);
  }
});

$<HTMLButtonElement>('connect').onclick = async () => {
  const code = connectToken.value.trim();
  const partnerName = connectPartner.value.trim();
  if (!code || !partnerName) return;
  try {
    const claimed = await claimDevice(DEFAULT_SERVER, partnerName, code);
    await accountItem.setValue({ server: DEFAULT_SERVER, token: claimed.token, accountId: claimed.account_id });
    connectToken.value = '';
    connectPartner.value = '';
    await syncNow();
    await refreshAuthoritative();
  } catch (err) {
    showError(connectError, err instanceof ApiError && err.status === 400 ? t('errorCode', locale) : t('errorGeneric', locale));
  }
};

// Draft starts as a copy of the last saved state. Reopening the popup therefore discards unsaved edits.
function fromSettings(): Draft {
  return {
    popupMessage: settings.popupMessage,
    blockMessage: settings.blockMessage,
    language: settings.language,
    sites: [...settings.sites],
    free: [...freeWindows],
  };
}

async function init() {
  settings = normalizeSettings(await settingsItem.getValue());
  draft = (await draftItem.getValue()) ?? fromSettings();
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
  ready = true;
  renderDraft();
  setInterval(renderGrant, 1000);
  setInterval(() => void syncNow().then(refreshAuthoritative), 10_000);
  settingsItem.watch(() => void refreshAuthoritative());
  remoteItem.watch(() => void refreshAuthoritative());
}

void init();
