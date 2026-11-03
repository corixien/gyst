# GYST: agent notes

Browser extension (WXT, TypeScript, MV3) for Firefox and Chromium. Blocks distracting sites until the user types a sentence and waits 10 s.

## Commands
- `npm run check`: typecheck, tests, both builds. Run before commit.
- `npm test`: Vitest, pure logic in `src/*.test.ts`.
- `npm run dev` / `npm run dev:firefox`: dev builds.

## Layout
- `entrypoints/background.ts`: `webNavigation` redirect to the block page (`tabs.update`). Reloads open tabs when a site becomes blocked.
- `entrypoints/popup/`: toggle, site list, 10 s confirm dialog, settings.
- `entrypoints/blocked/`: block page shown on redirect.
- `src/`: pure logic (`blocklist`, `i18n`, `settings`) and storage item.

## Invariants
- Popup writes `local:settings`, background reacts. Master off = nothing blocked.
- Sites in `sites` match the domain, its subdomains and all paths (`isBlockedUrl`).
- Do not use DNR redirect to extension pages: Firefox fails with NS_ERROR_DOM_BAD_URI.
- Turning off or removing a site always goes through the confirm dialog (typed sentence + 10 s).
- No network calls, no analytics, no accounts.
- Git: all work on `main`, push directly.
