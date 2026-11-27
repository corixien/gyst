import { browser } from 'wxt/browser';
import { isBlockedUrl } from '../src/blocklist';
import { readSettings } from '../src/storage';
import { isFreeNow } from '../src/sync';

const CHECK_MS = 1000; // a running grant or free window ending blocks an open page within this time
const RESUME_TRIES_MS = 30_000;

// The video that matters: the playing one, else the largest one.
function currentVideo(): HTMLVideoElement | undefined {
  const videos = [...document.querySelectorAll('video')];
  const playing = videos.find((v) => !v.paused && v.currentTime > 0);
  if (playing) return playing;
  return videos.sort((a, b) => b.clientWidth * b.clientHeight - a.clientWidth * a.clientHeight)[0];
}

// After a block is released the page loads again at the same URL: continue at the saved second.
async function resumeVideo() {
  const reply = await browser.runtime.sendMessage({ type: 'gyst-resume' });
  const time = reply?.time;
  if (typeof time !== 'number') return;
  const started = Date.now();
  const timer = setInterval(() => {
    const video = currentVideo();
    if (video && video.readyState >= 1) {
      video.currentTime = time;
      clearInterval(timer);
    } else if (Date.now() - started > RESUME_TRIES_MS) {
      clearInterval(timer);
    }
  }, 300);
}

async function guardPage() {
  const first = await readSettings();
  if (!first.enabled || !isBlockedUrl(location.href, first.sites)) return;
  void resumeVideo();
  let sending = false;
  setInterval(async () => {
    if (sending) return;
    const settings = await readSettings();
    if (!settings.enabled || !isBlockedUrl(location.href, settings.sites)) return;
    if (await isFreeNow()) return;
    sending = true;
    try {
      // The page is replaced by the block page. A failed send just retries on the next tick.
      await browser.runtime.sendMessage({ type: 'gyst-block', time: currentVideo()?.currentTime ?? 0 });
    } catch {
      // extension reloading: try again next tick
    } finally {
      sending = false;
    }
  }, CHECK_MS);
}

export default defineContentScript({
  matches: ['<all_urls>'],
  runAt: 'document_start',
  main() {
    void guardPage();
  },
});
