# GYST sync server

FastAPI app with Postgres (Neon). Serves the API and the partner page at `/partner`.

## Local test
Needs a Postgres at `DATABASE_URL` (test database only, never the production one):

```bash
cd server
pip install -r requirements.txt pytest httpx
DATABASE_URL=postgresql://postgres:test@localhost:55432/gyst python3 -m unittest tests.test_api
```

## Render + Neon setup (one time)
1. Neon: create a new project and copy the connection string (`postgresql://…?sslmode=require`). Do not reuse any existing project.
2. Render: New > Blueprint, point it at this repo (uses `render.yaml`) or New > Web Service with:
   - Root directory: `server`
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
   - Environment variable: `DATABASE_URL` = the Neon string
3. Open `https://<service>.onrender.com/` to check it answers `{"service": "gyst", ...}`.
4. Put the URL into the add-on popup (Server-Adresse) and the companion config.

The schema is created on startup (`schema.sql`, idempotent).

## API (all JSON, bearer token where noted)
| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/p/signup` | none | partner creates a login (username, password), returns session token |
| POST | `/api/p/login` | none | partner login, returns session token (30 days) |
| POST | `/api/p/logout` | session | end session |
| GET | `/api/p/me` | session | username |
| GET | `/api/p/accounts` | session | owners this partner is linked to: name, grant state, partners |
| POST | `/api/p/accounts` | session | create owner; this partner is its first partner; returns code (24 h) and partner username |
| POST | `/api/p/accounts/{id}/device-codes` | session | code (10 min) for one more device of the owner |
| POST | `/api/p/accounts/{id}/pairings` | session | add another partner by username; returns code (24 h) for that partner |
| POST | `/api/p/pairings/accept` | session | invited partner enters the code |
| POST | `/api/p/accounts/{id}/grant` | session | grant: 30m, 1h, day, settings, end |
| POST | `/api/p/accounts/{id}/leave` | session | partner leaves an owner |
| POST | `/api/devices/claim` | partner username + code | owner's add-on connects; one use |
| GET | `/api/state` | device token | settings, free windows, grant times, partner count |
| PUT | `/api/settings` | device token | Save: with a partner needs a time grant or a settings grant (used up by the save) |
| POST | `/api/sites` | device token | add a blocked site, always free |
| POST | `/api/enabled` | device token | on (free, ends a grant) or off (needs a running time grant) |
| GET | `/api/partners` | device token | partner usernames |
| POST | `/api/partners/remove` | device token | owner removes a partner; needs a running time grant |

Invites expire after 1 day and are single use. Grant rules: each grant is signed by a registered partner key over domain `gyst-grant-v2`, account id, tier and a unix stamp. Stamps must rise per account (single use) and be within 5 minutes of server time.
