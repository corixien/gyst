# GYST

Get Your Shit Together. A browser extension for Firefox and Chromium browsers that blocks distracting sites.

- **Master switch:** one big button turns blocking on or off.
- **Blocked sites:** add a domain (or the current tab). It blocks the domain, its subdomains and all paths.
- **Friction:** turning off or removing a site opens a popup. You type a sentence exactly and wait 10 seconds.
- **Block page:** a blocked site shows your own message.
- **Back where you were:** when a site is unblocked, its tab returns to the page you tried to open (for this session).
- **Languages:** English and German, automatic from the browser or set manually.

All data stays in the browser (`storage.local`). No network calls, no accounts.

## Develop

Requires Node 22+.

```bash
npm install
npm run dev:firefox   # or: npm run dev
npm run check         # typecheck, tests, both builds
```

### Firefox for Android

Every API GYST uses is supported on Firefox for Android (checked against MDN compat data). Not tested on a device yet. Release Firefox for Android only installs signed add-ons, so it needs an AMO listing (or Firefox Nightly with signature checks disabled for testing).

## Install from source

### Chrome / Brave / Edge

```bash
npm run build
```

1. Open `chrome://extensions`, enable **Developer mode**.
2. **Load unpacked** and select `.output/chrome-mv3`.

### Firefox

```bash
npm run build:firefox
```

1. Open `about:debugging#/runtime/this-firefox`.
2. **Load Temporary Add-on** and select `.output/firefox-mv3/manifest.json`.

## Permissions

- `storage`: save settings locally.
- `webNavigation`: catch navigations to blocked sites and send them to the block page.
- `tabs`: read the current tab's domain for the "Current tab" button.
- `<all_urls>` host access: needed so blocking works for any domain you add.

## License

MIT
