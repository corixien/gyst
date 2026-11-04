# GYST: project resume

## What
Firefox + Chromium extension "GYST" (Get Your Shit Together). Big master switch, site list (domain + subdomains + all paths), 10 s typed-confirm on turn-off/remove, custom block page message. EN/DE.

## Stack
WXT 0.21 + TypeScript + Vitest, MV3. Vanilla TS + CSS. `storage.local`, DNR dynamic rules. Same stack as `yt-hard-mode`.

## Layout
- `entrypoints/background.ts`: webNavigation redirect to block page; reloads open tabs on new blocks.
- `entrypoints/popup/`: UI (toggle, sites, confirm dialog, settings).
- `entrypoints/blocked/`: block page.
- `src/blocklist.ts`, `src/i18n.ts`, `src/settings.ts`, `src/storage.ts`.

## Commands
`npm run check`, `npm test`, `npm run dev:firefox`.

## Current state
- MVP (milestones 1-5 in code): toggle, site list, confirm, block page, i18n, settings. Typecheck, 6 unit tests, Firefox + Chrome builds pass.
- NOT verified in a real browser yet: DNR redirect behavior, popup flow.
- Repo `corixien/gyst` (public, MIT), first commit pushed to `main`.

## Open
- Manual test in Firefox and Chrome.
- Store listings (AMO, Chrome Web Store): user creates accounts.
- Icons: `design/icon.svg` = blue glyph-only G, source of `public/icon/{16,32,48,96,128}.png` (render via Playwright, see scratchpad script). Toolbar size still to be checked by user.

## Decisions
- 10 s confirm applies to turn-off and site removal only, not to enable or add.
- Blocked page = extension page (`/blocked.html`), no original URL passed.
- Unblock restores tabs to their original URL (`session:blockedTabs`). Verified in Chromium (popup flow) and Firefox (storage flow).
- Blocking via webNavigation + tabs.update. DNR redirect to extension page broke in Firefox (NS_ERROR_DOM_BAD_URI).
- Accent `#3b82f6`.
