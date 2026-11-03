import { browser, type Browser } from 'wxt/browser';
import { buildBlockRules, isBlockedUrl } from '../src/blocklist';
import { readSettings, settingsItem } from '../src/storage';

const BLOCK_PAGE = '/blocked.html';

export default defineBackground(() => {
  // Rule updates are async; queue them so overlapping syncs cannot interleave.
  let queue: Promise<unknown> = Promise.resolve();

  const syncRules = () => {
    const result = queue.then(async () => {
      const settings = await readSettings();
      const domains = settings.enabled ? settings.sites : [];
      const existing = await browser.declarativeNetRequest.getDynamicRules();
      await browser.declarativeNetRequest.updateDynamicRules({
        removeRuleIds: existing.map((rule) => rule.id),
        addRules: buildBlockRules(domains, BLOCK_PAGE) as Browser.declarativeNetRequest.Rule[],
      });
      // Redirect rules only apply to new navigations, so reload open tabs that are now blocked.
      const previous = new Set(existing.map((rule) => rule.condition.urlFilter));
      const added = domains.filter((domain) => !previous.has(`||${domain}^`));
      if (added.length > 0) await reloadBlockedTabs(added);
    });
    queue = result.catch(() => undefined);
    return result;
  };

  const reloadBlockedTabs = async (domains: string[]) => {
    const tabs = await browser.tabs.query({});
    await Promise.all(
      tabs
        .filter((tab) => tab.id !== undefined && isBlockedUrl(tab.url ?? '', domains))
        .map((tab) => browser.tabs.reload(tab.id!)),
    );
  };

  browser.runtime.onInstalled.addListener(syncRules);
  browser.runtime.onStartup.addListener(syncRules);
  settingsItem.watch(syncRules);
});
