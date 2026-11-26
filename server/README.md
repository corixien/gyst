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
| POST | `/api/accounts` | none | create account, returns token once |
| GET | `/api/state` | token | settings, free windows, grant times, partner count |
| PUT | `/api/settings` | token | save settings; loosening changes need a grant when a partner exists |
| POST | `/api/invites` | token | one-time partner invite (7 days) |
| POST | `/api/partners/register` | invite | register a partner public key |
| POST | `/api/grant` | partner signature | apply a grant (tiers 30m, 1h, day, settings) |
| GET | `/partner` | none | partner page |

Grant rules: each grant is signed by a registered partner key over domain `gyst-grant-v2`, account id, tier and a unix stamp. Stamps must rise per account (single use) and be within 5 minutes of server time.
