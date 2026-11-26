"""GYST sync server: accounts, settings, partners and partner grants. Postgres (Neon) via DATABASE_URL."""
import hashlib
import json
import os
import re
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from psycopg.rows import dict_row

from gating import TIERS, gated_changes, verify_grant

HERE = Path(__file__).parent
SCHEMA = (HERE / 'schema.sql').read_text()
INVITE_DAYS = 7
MAX_SITES = 500
MAX_WINDOWS = 200


def connect():
    return psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row)


def init_schema():
    with connect() as conn:
        conn.execute(SCHEMA)


@asynccontextmanager
async def lifespan(app):
    init_schema()
    yield


app = FastAPI(title='GYST sync', lifespan=lifespan)
app.mount('/static', StaticFiles(directory=HERE / 'static'), name='static')


def db():
    with connect() as conn:
        yield conn


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def account_for(token: str | None, conn) -> str:
    if not token:
        raise HTTPException(401, 'token required')
    row = conn.execute('SELECT id FROM accounts WHERE token_hash = %s', (sha(token),)).fetchone()
    if row is None:
        raise HTTPException(401, 'unknown token')
    return str(row['id'])


def auth(authorization: str | None = Header(default=None), conn=Depends(db)) -> str:
    token = authorization.removeprefix('Bearer ').strip() if authorization else None
    return account_for(token, conn)


class SettingsIn(BaseModel):
    enabled: bool
    sites: list[str] = Field(max_length=MAX_SITES)
    popupMessage: str = Field(max_length=300)
    blockMessage: str = Field(max_length=300)
    language: str = Field(pattern=r'^(auto|de|en)$')
    unlock: str = Field(pattern=r'^(text|partner)$')
    free_windows: list[dict] = Field(max_length=MAX_WINDOWS)


class GrantIn(BaseModel):
    account_id: str
    pubkey: str = Field(pattern=r'^[0-9a-f]{64}$')
    tier: int
    stamp: int
    signature: str


class RegisterIn(BaseModel):
    invite: str
    pubkey: str = Field(pattern=r'^[0-9a-f]{64}$')
    name: str = Field(default='', max_length=60)


def valid_window(w: dict) -> bool:
    hhmm = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')
    return (isinstance(w.get('day'), int) and 0 <= w['day'] <= 6
            and isinstance(w.get('from'), str) and hhmm.match(w['from'])
            and isinstance(w.get('to'), str) and hhmm.match(w['to']) is not None)


@app.post('/api/accounts')
def create_account(conn=Depends(db)):
    token = secrets.token_urlsafe(32)
    account_id = uuid.uuid4()
    conn.execute('INSERT INTO accounts (id, token_hash) VALUES (%s, %s)', (account_id, sha(token)))
    conn.execute('INSERT INTO account_state (account_id) VALUES (%s)', (account_id,))
    return {'account_id': str(account_id), 'token': token}


@app.get('/api/state')
def get_state(account_id: str = Depends(auth), conn=Depends(db)):
    row = conn.execute('SELECT settings, free_windows, grant_until, settings_until FROM account_state WHERE account_id = %s',
                       (account_id,)).fetchone()
    partners = conn.execute('SELECT count(*) AS n FROM partners WHERE account_id = %s', (account_id,)).fetchone()['n']
    return {
        'settings': row['settings'],
        'free_windows': row['free_windows'],
        'grant_until': row['grant_until'],
        'settings_until': row['settings_until'],
        'partners': partners,
        'now': int(time.time()),
    }


@app.put('/api/settings')
def put_settings(body: SettingsIn, account_id: str = Depends(auth), conn=Depends(db)):
    if any(not valid_window(w) for w in body.free_windows):
        raise HTTPException(422, 'invalid free window')
    row = conn.execute('SELECT settings, free_windows, grant_until, settings_until FROM account_state WHERE account_id = %s FOR UPDATE',
                       (account_id,)).fetchone()
    old = {**row['settings'], 'free_windows': row['free_windows']}
    new = body.model_dump()
    now = int(time.time())
    # Gating only applies once a partner exists; the first save of a new account sets up the defaults.
    has_partner = conn.execute('SELECT 1 FROM partners WHERE account_id = %s LIMIT 1', (account_id,)).fetchone()
    gated = gated_changes(old, new) if row['settings'] and has_partner else []
    time_grant = row['grant_until'] > now
    settings_grant = row['settings_until'] > now
    if gated and not (time_grant or settings_grant):
        raise HTTPException(403, {'error': 'grant_required', 'changes': gated})
    settings = {k: v for k, v in new.items() if k != 'free_windows'}
    settings_until = 0 if (settings_grant and not time_grant and gated) else row['settings_until']
    conn.execute(
        'UPDATE account_state SET settings = %s, free_windows = %s, settings_until = %s WHERE account_id = %s',
        (json.dumps(settings), json.dumps(new['free_windows']), settings_until, account_id),
    )
    return {'ok': True, 'settings_until': settings_until}


@app.post('/api/invites')
def create_invite(account_id: str = Depends(auth), conn=Depends(db)):
    secret = secrets.token_urlsafe(16)
    code = f'{account_id}.{secret}'
    conn.execute(
        "INSERT INTO invites (code_hash, account_id, expires_at) VALUES (%s, %s, now() + make_interval(days => %s))",
        (sha(code), account_id, INVITE_DAYS),
    )
    return {'code': code, 'expires_in_days': INVITE_DAYS}


@app.post('/api/partners/register')
def register_partner(body: RegisterIn, conn=Depends(db)):
    account_id, _, _ = body.invite.partition('.')
    invite = conn.execute(
        'DELETE FROM invites WHERE code_hash = %s AND account_id = %s AND expires_at > now() RETURNING account_id',
        (sha(body.invite), account_id),
    ).fetchone()
    if invite is None:
        raise HTTPException(400, 'invite invalid, expired or used')
    partner_id = uuid.uuid4()
    conn.execute(
        'INSERT INTO partners (id, account_id, pubkey, name) VALUES (%s, %s, %s, %s) ON CONFLICT (account_id, pubkey) DO NOTHING',
        (partner_id, invite['account_id'], body.pubkey, body.name),
    )
    return {'account_id': str(invite['account_id'])}


@app.post('/api/grant')
def grant(body: GrantIn, request: Request, conn=Depends(db)):
    """Partner grant. The request is signed by a partner key registered for this account."""
    now = int(time.time())
    partner = conn.execute('SELECT id FROM partners WHERE account_id = %s AND pubkey = %s',
                           (body.account_id, body.pubkey)).fetchone()
    if partner is None:
        raise HTTPException(403, 'unknown partner')
    if not verify_grant(body.pubkey, body.account_id, body.tier, body.stamp, body.signature, now):
        raise HTTPException(403, 'signature invalid or stamp too old')
    tier, minutes = TIERS[body.tier]
    row = conn.execute('SELECT grant_until, settings_until, last_stamp FROM account_state WHERE account_id = %s FOR UPDATE',
                       (body.account_id,)).fetchone()
    if row is None:
        raise HTTPException(404, 'account not found')
    if body.stamp <= row['last_stamp']:
        raise HTTPException(409, 'token already used')
    if tier == 'settings':
        conn.execute('UPDATE account_state SET settings_until = %s, last_stamp = %s WHERE account_id = %s',
                     (now + minutes, body.stamp, body.account_id))
    else:
        grant_until = max(row['grant_until'], now) + minutes
        conn.execute('UPDATE account_state SET grant_until = %s, last_stamp = %s WHERE account_id = %s',
                     (grant_until, body.stamp, body.account_id))
    conn.execute('INSERT INTO grant_log (account_id, partner_id, tier) VALUES (%s, %s, %s)',
                 (body.account_id, partner['id'], tier))
    return {'ok': True, 'tier': tier}


@app.get('/partner')
def partner_page():
    return FileResponse(HERE / 'static' / 'partner.html')


@app.get('/')
def root():
    return {'service': 'gyst', 'partner_page': '/partner'}
