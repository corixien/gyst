import { browser, type Browser } from 'wxt/browser';
import { buildBlockRules } from '../src/blocklist';
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
    });
    queue = result.catch(() => undefined);
    return result;
  };

  browser.runtime.onInstalled.addListener(syncRules);
  browser.runtime.onStartup.addListener(syncRules);
  settingsItem.watch(syncRules);
});
