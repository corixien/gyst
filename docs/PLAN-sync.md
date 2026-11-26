# Plan: GYST sync server, Android, multiple users and partners

Status (0.2.0): phases 1-5 built and tested locally (server, add-on, companion, partner page). Open: Render deploy, Neon DB, Firefox desktop + Android run, companion lock on hardware. Decisions below marked **?** still open.

## Goal
- Firefox (desktop + Android) and Chrome add-on, Linux companion (lock screen) on the user's PC.
- Server + DB syncs settings, free windows, sites and partner grants between devices.
- Many main users, each with their own partners. Partners act from a web page (phone or PC), no install.

## Why the current design cannot do this
- Firefox for Android has no native messaging. The add-on cannot reach the companion, so the server must be the bridge.
- Partner tokens go through ntfy and a root-owned public key. One partner per PC, and each change needs sudo. Does not scale to many partners.

## Target architecture
```
Partner web page ──(signed grant)──▶ Server (API + DB) ◀──(poll/stream)── Linux companion (lock screen)
                                        ▲        ▲
                       Add-on (Firefox/Chrome/Android) ──(REST, account token)
```
- **Server:** one small API service plus DB. Stores accounts, devices, settings, free windows, sites, partners (public keys) and an audit log of grants.
- **Add-on:** talks to the server only. Native messaging is dropped, so Android works. Blocking logic stays in the add-on (webNavigation / redirect). Sync replaces `companion` checks.
- **Companion:** keeps the lock screen and evdev grab. Gets state from the server over HTTPS (SSE or polling). Enforces the lock locally, offline cache for free windows.
- **Partner page:** static page served by the server. Partner keeps the private key in the browser, the server stores only the public key. Grant = signed request. Server checks signature, applies grant, logs it.
- **Multi-user:** accounts are isolated. A partner belongs to one main user. Users never see each other's data.

## Trust model (decides everything else)
- The server must not be run by the blocked person. If the blocked person controls the server DB or its admin login, they can add their own partner key.
- Options:
  1. Partner hosts the server (or one partner does) for their friend. Strong, needs a second person with a server.
  2. Hosted by us. Simple for users, but we hold data and become operator. Not recommended for a "no accounts, no network" product.
  3. Self-hosted by the user, with the partner keys set only by partners' signed invites. Weaker, friction only.
- **?** Which option? Recommendation: option 1 (partner hosts), with option 3 as fallback.

## Phases
1. **Decisions and spec:** trust model, server stack, DB, hosting. Define API (accounts, devices, state, grants).
2. **Server v1:** accounts, devices, partner invites (signed by an existing partner or by the setup partner), state sync, grant endpoint with signature check, audit log. Tests for the signature and replay rules (reuse `match_partner_code` logic with the stamp rule).
3. **Add-on v2:** account login, state sync, remove native messaging path. Keep sentence confirm and 10 s wait as today. Test on Firefox desktop, Chrome, then Firefox Android.
4. **Companion v2:** sync client, lock screen, offline cache. Remove ntfy and `/etc/gyst` key.
5. **Partner page v2:** hosted by server, one-button grant, settings grant, schedule editor for the main user to see.
6. **Multi-partner and multi-user:** invites, per-partner revoke, account isolation tests.
7. **Packaging:** server docker-compose, companion installer (see below), release zips.

## Android notes
- Firefox Android supports WebExtensions and AMO installs. Test blocking with webNavigation on a real phone first, it is the riskiest part.
- No keyboard grab on Android, so the lock is browser-only there.

## Repo layout (proposed, replaces the current flat layout)
```
gyst/
  extension/        WXT add-on (entrypoints, src, public, wxt.config.ts)
  companion/        Linux sync client + lock screen (python, systemd unit, install script)
  server/           API + DB (migrations, tests, docker-compose)
  partner-web/      partner page (served by server)
  docs/             this plan, spec, trust model
```
Moving the WXT project into `extension/` is a larger change. Do it in its own commit after phase 1.

## /usr install (companion)
- Companion runs from the repo today. Proposed: `companion/install.sh` copies the daemon to `/usr/local/lib/gyst/` and installs the systemd unit system-wide or per user. Needs sudo once. I cannot run sudo here, you run it.
- **?** Confirm `/usr/local/lib/gyst` as target, or keep the user unit under `~/.config/systemd/user`.

## Decided
- Hosting: Render web service (API + partner page). Database: Neon Postgres (separate new project, not `gentle-morning-60095256`, never touched by tests or migrations).
- Why Neon: Render's free web services have no persistent disk, so SQLite is not safe there. One Render service alone is not enough.
- Platforms: all (Firefox, Chrome, Firefox Android, Linux companion) talk to the same server. Native messaging and ntfy go away.
- Free Render services sleep after idle. Grant and lock checks then wait for a cold start (tens of seconds). Paid instance or accepting the delay is a cost decision.
- The footer claim "no network calls" no longer holds. Update the store text and README.

## Open questions
1. Trust model: who holds the Render and Neon accounts. If the blocked person does, they can change partner keys. Option 1 (partner hosts) is the only strong one.
2. Paid Render instance (no cold start) or free (delay)?
3. Keep ntfy during the transition, or go straight to the server?
