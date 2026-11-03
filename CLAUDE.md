# GYST: agent notes

Browser extension (WXT, TypeScript, MV3) for Firefox and Chromium. Blocks distracting sites until the user types a sentence and waits 10 s.

## Commands
- `npm run check`: typecheck, tests, both builds. Run before commit.
- `npm test`: Vitest, pure logic in `src/*.test.ts`.
- `npm run dev` / `npm run dev:firefox`: dev builds.

## Layout
- `entrypoints/background.ts`: single writer of DNR block rules. Syncs on install, startup, and settings change.
- `entrypoints/popup/`: toggle, site list, 10 s confirm dialog, settings.
- `entrypoints/blocked/`: block page shown on redirect.
- `src/`: pure logic (`blocklist`, `i18n`, `settings`) and storage item.

## Invariants
- Only the background writes DNR rules. Popup writes `local:settings`, background reacts.
- Master off = no rules. Sites in `sites` are matched as `||domain^` (subdomains and all paths).
- Turning off or removing a site always goes through the confirm dialog (typed sentence + 10 s).
- No network calls, no analytics, no accounts.
- Git: all work on `main`, push directly.
