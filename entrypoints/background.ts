import { browser } from 'wxt/browser';
import { isBlockedUrl } from '../src/blocklist';
import { DEFAULT_SETTINGS, type Settings } from '../src/settings';
import { readSettings, settingsItem } from '../src/storage';

const BLOCK_PAGE = '/blocked.html';

const blockedDomains = (settings: Settings) => (settings.enabled ? settings.sites : []);

export default defineBackground(() => {
  // Redirect before the page loads. Firefox refuses DNR redirects to extension pages, so tabs.update is used.
  browser.webNavigation.onBeforeNavigate.addListener(
    async (details) => {
      if (details.frameId !== 0) return;
      const settings = await readSettings();
      if (!isBlockedUrl(details.url, blockedDomains(settings))) return;
      await browser.tabs.update(details.tabId, { url: browser.runtime.getURL(BLOCK_PAGE) });
    },
    { url: [{ schemes: ['http', 'https'] }] },
  );

  // Tabs already open on a newly blocked site reload, which runs the redirect above.
  settingsItem.watch(async (next, previous) => {
    const before = blockedDomains(previous ?? DEFAULT_SETTINGS);
    const added = blockedDomains(next).filter((domain) => !before.includes(domain));
    if (added.length === 0) return;
    const tabs = await browser.tabs.query({});
    await Promise.all(
      tabs
        .filter((tab) => tab.id !== undefined && isBlockedUrl(tab.url ?? '', added))
        .map((tab) => browser.tabs.reload(tab.id!)),
    );
  });
});
