# GYST: project resume

## What
Firefox + Chromium (+ Firefox Android, not tested yet) extension "GYST" (Get Your Shit Together). Blocks sites, free windows per weekday, partner grants (30 min / 1 h / day / settings), sync via server. Linux companion draws the lock screen on Firefox desktop. EN/DE.

## Architecture (0.2.0)
- `server/`: FastAPI + Postgres (Neon). Accounts, settings, free windows, partners (Ed25519 public keys), grants. Deploy on Render (`server/render.yaml`, `server/README.md`).
- Extension: talks only to the server. Local cache in `local:remote`. Every change goes through `change()` in the popup; the server checks it again.
- `companion/`: polls the server (`config.json`: `server`, `token`), keeps last state in `~/.local/state/gyst-companion/`.
- Plan and decisions: `docs/PLAN-sync.md`.

## Stack
WXT 0.21 + TypeScript + Vitest, MV3. Vanilla TS + CSS. `storage.local`, DNR dynamic rules. Same stack as `yt-hard-mode`.

## Layout
- `entrypoints/background.ts`: webNavigation redirect to block page; reloads open tabs on new blocks.
- `entrypoints/popup/`: UI (toggle, sites, confirm dialog, settings).
- `entrypoints/blocked/`: block page.
- `src/blocklist.ts`, `src/i18n.ts`, `src/settings.ts`, `src/storage.ts`.

## Commands
`npm run check`, `npm test`, `npm run dev:firefox`.

## Current state (0.2.0, version kept until the Freigabe feature is done; zips are overwritten)
- Known limit: the account token on the device can create invites, so the owner can register a partner key of their own. Only a third party identity (e.g. email confirmation to an address the owner does not control) closes this. Not built, decision pending.
- Partner removal: partner page button (signed `gyst-leave-v1`, always free). Owner removal in add-on needs a running time grant (`POST /api/partners/remove`).
- Toggle: a running grant shows Off; tapping turns the block on at once and ends the grant (`/api/enabled` with true zeroes `grant_until`). Settings grant cannot switch the block off.
- Without partners the typed sentence (10 s) guards turn-off and Save; with partners the sentence field is hidden and rule hint says so.
- Popup: no "Konto" section. Account is created on first open (default server). Token and connect-by-token live in a collapsed "Gerät verbinden" block.
- Server: 27 API tests against local Postgres (podman container, port 55432, test only). Partner page served at `/partner`.
- Add-on: account, invite, sync, gated changes, blocking, block-page release. Verified in headless Chrome (popup, partner grant, gated removal refused, block and release).
- NOT done: Firefox desktop run with companion, Firefox Android test, Render deploy, Neon DB (user creates both), companion lock on real hardware.
- Dev DB container: `podman run -d --name gyst-pg-test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=gyst -p 55432:5432 docker.io/library/postgres:16-alpine`

## Companion (Linux, `companion/`)
- `gyst_companion.py`: systemd user daemon. Polls the server every 10 s (`config.json`: `server`, `token`). Free = grant running or in a free window. Lock screen (tk ring + GYST wordmark, evdev grab, no sudo) on `blocked` from Firefox.
- `gyst_native_host.py`: native messaging bridge for Firefox (`gyst_companion`).
- Fail closed: no server config or no state = nothing free. Default server: `https://gyst-sync-y5x4.onrender.com` (add-on `src/api.ts` DEFAULT_SERVER, companion DEFAULT_CONFIG). Existing `config.json` on disk keeps its own `server` value.

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
- Bump `package.json` version (`npm version X --no-git-tag-version`) on every new zip build. Zip names follow the version.
- AMO: ID `gyst@corixien.github.io` is a NEW add-on. Upload via "Submit a New Add-on", not as a new version of `yt-hard-mode`.
