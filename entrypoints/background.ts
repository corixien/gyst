import { browser } from 'wxt/browser';
import { isBlockedUrl } from '../src/blocklist';
import { DEFAULT_SETTINGS, type Settings } from '../src/settings';
import { blockedTabsItem, readSettings, settingsItem } from '../src/storage';

const BLOCK_PAGE = '/blocked.html';

const blockPageUrl = () => browser.runtime.getURL(BLOCK_PAGE);
const blockedDomains = (settings: Settings) => (settings.enabled ? settings.sites : []);

export default defineBackground(() => {
  // Serialize writes to the tab map and the tab updates that depend on it.
  let queue: Promise<unknown> = Promise.resolve();
  const serial = <T>(task: () => Promise<T>): Promise<T> => {
    const result = queue.then(task);
    queue = result.catch(() => undefined);
    return result;
  };

  // Redirect before the page loads. Firefox refuses DNR redirects to extension pages, so tabs.update is used.
  browser.webNavigation.onBeforeNavigate.addListener(
    async (details) => {
      if (details.frameId !== 0) return;
      const settings = await readSettings();
      if (!isBlockedUrl(details.url, blockedDomains(settings))) return;
      await serial(async () => {
        const tabs = await blockedTabsItem.getValue();
        await blockedTabsItem.setValue({ ...tabs, [details.tabId]: details.url });
        await browser.tabs.update(details.tabId, { url: blockPageUrl() });
      });
    },
    { url: [{ schemes: ['http', 'https'] }] },
  );

  browser.tabs.onRemoved.addListener((tabId) =>
    serial(async () => {
      const tabs = { ...(await blockedTabsItem.getValue()) };
      if (!(tabId in tabs)) return;
      delete tabs[tabId];
      await blockedTabsItem.setValue(tabs);
    }),
  );

  // Send tabs back to the page they wanted once their domain is no longer blocked.
  const restoreTabs = (domains: string[]) =>
    serial(async () => {
      const tabs = await blockedTabsItem.getValue();
      const kept: Record<string, string> = {};
      for (const [key, url] of Object.entries(tabs)) {
        if (isBlockedUrl(url, domains)) {
          kept[key] = url;
          continue;
        }
        const tabId = Number(key);
        const tab = await browser.tabs.get(tabId).catch(() => undefined);
        if (tab?.url?.startsWith(blockPageUrl())) await browser.tabs.update(tabId, { url });
      }
      await blockedTabsItem.setValue(kept);
    });

  // Tabs already open on a newly blocked site reload, which runs the redirect above.
  const reloadTabs = async (domains: string[]) => {
    const tabs = await browser.tabs.query({});
    await Promise.all(
      tabs
        .filter((tab) => tab.id !== undefined && isBlockedUrl(tab.url ?? '', domains))
        .map((tab) => browser.tabs.reload(tab.id!)),
    );
  };

  settingsItem.watch(async (next, previous) => {
    const current = blockedDomains(next);
    const before = blockedDomains(previous ?? DEFAULT_SETTINGS);
    await restoreTabs(current);
    const added = current.filter((domain) => !before.includes(domain));
    if (added.length > 0) await reloadTabs(added);
  });
});
