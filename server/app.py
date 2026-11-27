"""GYST sync server: owner settings and free time, partner logins, partner dashboard. Postgres (Neon) via DATABASE_URL."""
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
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row

from gating import apply_grant, hash_password, valid_username, verify_password

HERE = Path(__file__).parent
SCHEMA = (HERE / 'schema.sql').read_text()
CLAIM_MINUTES = 10  # device code for an extra device
OWNER_CODE_HOURS = 24  # first code for a new owner, and partner-to-partner pairing codes
SESSION_DAYS = 30
MAX_SITES = 500
MAX_WINDOWS = 200
DOMAIN = re.compile(r'[a-z0-9-]+(\.[a-z0-9-]+)+')


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


def bearer(authorization: str | None) -> str:
    token = authorization.removeprefix('Bearer ').strip() if authorization else ''
    if not token:
        raise HTTPException(401, 'token required')
    return token


def device_account(authorization: str | None = Header(default=None), conn=Depends(db)) -> str:
    """Owner's add-on: device token -> account."""
    row = conn.execute('SELECT account_id FROM devices WHERE token_hash = %s', (sha(bearer(authorization)),)).fetchone()
    if row is None:
        raise HTTPException(401, 'unknown token')
    return str(row['account_id'])


def partner_of(authorization: str | None = Header(default=None), conn=Depends(db)) -> str:
    """Partner dashboard: session token -> partner id."""
    row = conn.execute(
        'SELECT partner_id FROM partner_sessions WHERE token_hash = %s AND expires_at > now()',
        (sha(bearer(authorization)),),
    ).fetchone()
    if row is None:
        raise HTTPException(401, 'login required')
    return str(row['partner_id'])


def linked(conn, account_id: str, partner_id: str) -> bool:
    return conn.execute('SELECT 1 FROM links WHERE account_id = %s AND partner_id = %s', (account_id, partner_id)).fetchone() is not None


def new_code() -> str:
    raw = ''.join(secrets.choice('ABCDEFGHJKMNPQRSTUVWXYZ23456789') for _ in range(8))
    return f'{raw[:4]}-{raw[4:]}'


def normalize_code(code: str) -> str:
    return code.replace('-', '').replace(' ', '').upper()


class SettingsIn(BaseModel):
    enabled: bool
    sites: list[str] = Field(max_length=MAX_SITES)
    popupMessage: str = Field(max_length=300)
    blockMessage: str = Field(max_length=300)
    language: str = Field(pattern=r'^(auto|de|en)$')
    unlock: str = Field(pattern=r'^(text|partner)$')
    displayName: str = Field(default='', max_length=40)
    free_windows: list[dict] = Field(max_length=MAX_WINDOWS)


class SiteIn(BaseModel):
    domain: str = Field(min_length=1, max_length=253)


class EnabledIn(BaseModel):
    enabled: bool


class ClaimIn(BaseModel):
    partner_username: str = Field(min_length=3, max_length=20)
    code: str = Field(min_length=4, max_length=20)


class CredentialsIn(BaseModel):
    username: str = Field(min_length=3, max_length=20)
    password: str = Field(min_length=8, max_length=200)


class NewOwnerIn(BaseModel):
    label: str = Field(default='', max_length=40)


class PairingIn(BaseModel):
    username: str = Field(min_length=3, max_length=20)


class AcceptIn(BaseModel):
    code: str = Field(min_length=4, max_length=20)


class GrantIn(BaseModel):
    tier: str = Field(pattern=r'^(30m|1h|day|settings|end)$')


class RemoveIn(BaseModel):
    partner_id: uuid.UUID


def settings_row(conn, account_id: str):
    return conn.execute('SELECT settings, free_windows, grant_until, settings_until FROM account_state WHERE account_id = %s',
                        (account_id,)).fetchone()


def locked_state(conn, account_id: str):
    row = conn.execute('SELECT settings, free_windows, grant_until, settings_until FROM account_state WHERE account_id = %s FOR UPDATE',
                       (account_id,)).fetchone()
    has_partner = conn.execute('SELECT 1 FROM links WHERE account_id = %s LIMIT 1', (account_id,)).fetchone() is not None
    return row, has_partner


def valid_window(w: dict) -> bool:
    hhmm = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')
    return (isinstance(w.get('day'), int) and 0 <= w['day'] <= 6
            and isinstance(w.get('from'), str) and hhmm.match(w['from'])
            and isinstance(w.get('to'), str) and hhmm.match(w['to']) is not None)


# ---------- owner add-on (device token) ----------

@app.post('/api/devices/claim')
def claim_device(body: ClaimIn, conn=Depends(db)):
    """Owner's add-on connects with a code and the name of the partner who issued it. One use."""
    row = conn.execute(
        """DELETE FROM claims c USING partner_users u
           WHERE c.code_hash = %s AND c.expires_at > now() AND u.id = c.issuer_id AND lower(u.username) = lower(%s)
             AND EXISTS (SELECT 1 FROM links l WHERE l.account_id = c.account_id AND l.partner_id = c.issuer_id)
           RETURNING c.account_id""",
        (sha(normalize_code(body.code)), body.partner_username),
    ).fetchone()
    if row is None:
        raise HTTPException(400, 'code or partner name wrong, expired or used')
    token = secrets.token_urlsafe(32)
    conn.execute('INSERT INTO devices (token_hash, account_id) VALUES (%s, %s)', (sha(token), row['account_id']))
    return {'account_id': str(row['account_id']), 'token': token}


@app.get('/api/state')
def get_state(account_id: str = Depends(device_account), conn=Depends(db)):
    row = settings_row(conn, account_id)
    partners = conn.execute('SELECT count(*) AS n FROM links WHERE account_id = %s', (account_id,)).fetchone()['n']
    return {
        'settings': row['settings'],
        'free_windows': row['free_windows'],
        'grant_until': row['grant_until'],
        'settings_until': row['settings_until'],
        'partners': partners,
        'now': int(time.time()),
    }


@app.put('/api/settings')
def put_settings(body: SettingsIn, account_id: str = Depends(device_account), conn=Depends(db)):
    """Save button. With a partner, saving needs a time grant or a settings grant. A settings grant is used up by this save."""
    if any(not valid_window(w) for w in body.free_windows):
        raise HTTPException(422, 'invalid free window')
    row, has_partner = locked_state(conn, account_id)
    now = int(time.time())
    time_grant = row['grant_until'] > now
    settings_grant = row['settings_until'] > now
    first_save = not row['settings']
    if has_partner and not first_save and not (time_grant or settings_grant):
        raise HTTPException(403, {'error': 'grant_required'})
    # A settings grant must not switch the block off: switching off always needs a time grant.
    switching_off = not first_save and (row['settings'] or {}).get('enabled') and not body.enabled
    if has_partner and switching_off and not time_grant:
        raise HTTPException(403, {'error': 'grant_required'})
    settings_until = row['settings_until'] if (time_grant or first_save or not has_partner) else 0
    settings = body.model_dump(exclude={'free_windows'})
    conn.execute(
        'UPDATE account_state SET settings = %s, free_windows = %s, settings_until = %s WHERE account_id = %s',
        (json.dumps(settings), json.dumps(body.free_windows), settings_until, account_id),
    )
    return {'ok': True, 'settings_until': settings_until}


@app.post('/api/sites')
def add_site(body: SiteIn, account_id: str = Depends(device_account), conn=Depends(db)):
    """Adding a site is always free: a block can be extended without a partner."""
    domain = body.domain.strip().lower()
    if not DOMAIN.fullmatch(domain):
        raise HTTPException(422, 'invalid domain')
    row, _ = locked_state(conn, account_id)
    settings = row['settings'] or {}
    sites = list(settings.get('sites', []))
    if domain not in sites:
        sites.append(domain)
    settings = {**settings, 'sites': sites[:MAX_SITES]}
    conn.execute('UPDATE account_state SET settings = %s WHERE account_id = %s', (json.dumps(settings), account_id))
    return {'ok': True, 'sites': settings['sites']}


@app.post('/api/enabled')
def set_enabled(body: EnabledIn, account_id: str = Depends(device_account), conn=Depends(db)):
    """Turning the block on is free and ends a running grant: the rest of the grant is lost.
    Turning it off needs a running time grant (partner)."""
    row, has_partner = locked_state(conn, account_id)
    now = int(time.time())
    if not body.enabled and has_partner and row['grant_until'] <= now:
        raise HTTPException(403, {'error': 'grant_required'})
    settings = {**(row['settings'] or {}), 'enabled': body.enabled}
    grant_until = 0 if body.enabled else row['grant_until']
    conn.execute('UPDATE account_state SET settings = %s, grant_until = %s WHERE account_id = %s',
                 (json.dumps(settings), grant_until, account_id))
    return {'ok': True}


@app.get('/api/partners')
def list_partners(account_id: str = Depends(device_account), conn=Depends(db)):
    rows = conn.execute(
        'SELECT u.id, u.username, l.created_at FROM links l JOIN partner_users u ON u.id = l.partner_id '
        'WHERE l.account_id = %s ORDER BY l.created_at', (account_id,)).fetchall()
    return {'partners': [{'id': str(r['id']), 'name': r['username'], 'since': r['created_at'].isoformat()} for r in rows]}


@app.post('/api/partners/remove')
def remove_partner(body: RemoveIn, account_id: str = Depends(device_account), conn=Depends(db)):
    """Owner removes a partner from the add-on. Needs a running time grant, like switching the block off."""
    row, _ = locked_state(conn, account_id)
    if row['grant_until'] <= int(time.time()):
        raise HTTPException(403, {'error': 'grant_required'})
    deleted = conn.execute('DELETE FROM links WHERE account_id = %s AND partner_id = %s RETURNING partner_id',
                           (account_id, body.partner_id)).fetchone()
    if deleted is None:
        raise HTTPException(404, 'partner not found')
    return {'ok': True}


# ---------- partner accounts ----------

@app.post('/api/p/signup')
def signup(body: CredentialsIn, conn=Depends(db)):
    if not valid_username(body.username):
        raise HTTPException(422, 'username: 3-20 characters, a-z 0-9 . _ -')
    partner_id = uuid.uuid4()
    try:
        conn.execute('INSERT INTO partner_users (id, username, pass_hash) VALUES (%s, %s, %s)',
                     (partner_id, body.username, hash_password(body.password)))
    except UniqueViolation:
        raise HTTPException(409, 'username taken')
    return start_session(conn, partner_id, body.username)


@app.post('/api/p/login')
def login(body: CredentialsIn, conn=Depends(db)):
    row = conn.execute('SELECT id, username, pass_hash FROM partner_users WHERE username = %s', (body.username.lower(),)).fetchone()
    if row is None or not verify_password(body.password, row['pass_hash']):
        raise HTTPException(401, 'username or password wrong')
    return start_session(conn, row['id'], row['username'])


def start_session(conn, partner_id, username: str) -> dict:
    token = secrets.token_urlsafe(32)
    conn.execute("INSERT INTO partner_sessions (token_hash, partner_id, expires_at) VALUES (%s, %s, now() + make_interval(days => %s))",
                 (sha(token), partner_id, SESSION_DAYS))
    return {'token': token, 'username': username}


@app.post('/api/p/logout')
def logout(authorization: str | None = Header(default=None), conn=Depends(db)):
    conn.execute('DELETE FROM partner_sessions WHERE token_hash = %s', (sha(bearer(authorization)),))
    return {'ok': True}


@app.get('/api/p/me')
def me(partner_id: str = Depends(partner_of), conn=Depends(db)):
    row = conn.execute('SELECT username FROM partner_users WHERE id = %s', (partner_id,)).fetchone()
    return {'username': row['username']}


@app.get('/api/p/accounts')
def my_accounts(partner_id: str = Depends(partner_of), conn=Depends(db)):
    rows = conn.execute(
        """SELECT a.id, l.label, s.settings, s.grant_until, s.settings_until
           FROM links l JOIN accounts a ON a.id = l.account_id JOIN account_state s ON s.account_id = a.id
           WHERE l.partner_id = %s ORDER BY l.created_at""", (partner_id,)).fetchall()
    out = []
    for r in rows:
        partners = conn.execute(
            'SELECT u.username FROM links l JOIN partner_users u ON u.id = l.partner_id WHERE l.account_id = %s ORDER BY l.created_at',
            (r['id'],)).fetchall()
        out.append({
            'account_id': str(r['id']),
            'label': r['label'],
            'owner_name': (r['settings'] or {}).get('displayName', ''),
            'enabled': (r['settings'] or {}).get('enabled'),
            'grant_until': r['grant_until'],
            'settings_until': r['settings_until'],
            'partners': [p['username'] for p in partners],
        })
    return {'accounts': out, 'now': int(time.time())}


@app.post('/api/p/accounts')
def new_owner(body: NewOwnerIn, partner_id: str = Depends(partner_of), conn=Depends(db)):
    """Creates an owner. This partner is the owner's first partner. The owner claims the code with this username."""
    account_id = uuid.uuid4()
    conn.execute('INSERT INTO accounts (id) VALUES (%s)', (account_id,))
    conn.execute('INSERT INTO account_state (account_id) VALUES (%s)', (account_id,))
    conn.execute('INSERT INTO links (account_id, partner_id, label) VALUES (%s, %s, %s)', (account_id, partner_id, body.label.strip()))
    code = new_code()
    conn.execute("INSERT INTO claims (code_hash, account_id, issuer_id, expires_at) VALUES (%s, %s, %s, now() + make_interval(hours => %s))",
                 (sha(normalize_code(code)), account_id, partner_id, OWNER_CODE_HOURS))
    username = conn.execute('SELECT username FROM partner_users WHERE id = %s', (partner_id,)).fetchone()['username']
    return {'account_id': str(account_id), 'code': code, 'partner_username': username, 'expires_in_hours': OWNER_CODE_HOURS}


@app.post('/api/p/accounts/{account_id}/device-codes')
def device_code(account_id: uuid.UUID, partner_id: str = Depends(partner_of), conn=Depends(db)):
    """Code for one more device of an owner (10 minutes). The partner's name goes with it."""
    if not linked(conn, str(account_id), partner_id):
        raise HTTPException(404, 'not your owner')
    code = new_code()
    conn.execute("INSERT INTO claims (code_hash, account_id, issuer_id, expires_at) VALUES (%s, %s, %s, now() + make_interval(mins => %s))",
                 (sha(normalize_code(code)), str(account_id), partner_id, CLAIM_MINUTES))
    username = conn.execute('SELECT username FROM partner_users WHERE id = %s', (partner_id,)).fetchone()['username']
    return {'code': code, 'partner_username': username, 'expires_in_minutes': CLAIM_MINUTES}


@app.post('/api/p/accounts/{account_id}/pairings')
def pair_partner(account_id: uuid.UUID, body: PairingIn, partner_id: str = Depends(partner_of), conn=Depends(db)):
    """A partner of this owner adds another partner by username. The new partner must enter the code (24 h, one use)."""
    if not linked(conn, str(account_id), partner_id):
        raise HTTPException(404, 'not your owner')
    invitee = conn.execute('SELECT id FROM partner_users WHERE username = %s', (body.username.lower(),)).fetchone()
    if invitee is None:
        raise HTTPException(404, 'no partner with this username')
    if str(invitee['id']) == partner_id:
        raise HTTPException(422, 'that is you')
    if linked(conn, str(account_id), str(invitee['id'])):
        raise HTTPException(409, 'already partner of this owner')
    code = new_code()
    conn.execute("INSERT INTO pairings (code_hash, account_id, inviter_id, invitee_id, expires_at) "
                 "VALUES (%s, %s, %s, %s, now() + make_interval(hours => %s))",
                 (sha(normalize_code(code)), str(account_id), partner_id, invitee['id'], OWNER_CODE_HOURS))
    return {'code': code, 'username': body.username.lower(), 'expires_in_hours': OWNER_CODE_HOURS}


@app.post('/api/p/pairings/accept')
def accept_pairing(body: AcceptIn, partner_id: str = Depends(partner_of), conn=Depends(db)):
    """The invited partner enters the code. Only the invitee can use it, and the inviter must still be a partner."""
    row = conn.execute(
        """DELETE FROM pairings p WHERE p.code_hash = %s AND p.expires_at > now() AND p.invitee_id = %s
           RETURNING p.account_id, p.inviter_id""",
        (sha(normalize_code(body.code)), partner_id)).fetchone()
    if row is None:
        raise HTTPException(400, 'code wrong, expired, used, or for another partner')
    if not linked(conn, str(row['account_id']), str(row['inviter_id'])):
        raise HTTPException(403, 'the partner who invited you is no longer partner of this owner')
    conn.execute('INSERT INTO links (account_id, partner_id, label) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING',
                 (row['account_id'], partner_id, ''))
    return {'account_id': str(row['account_id'])}


@app.post('/api/p/accounts/{account_id}/grant')
def grant(account_id: uuid.UUID, body: GrantIn, partner_id: str = Depends(partner_of), conn=Depends(db)):
    """Partner grant from the dashboard. Only linked partners."""
    if not linked(conn, str(account_id), partner_id):
        raise HTTPException(404, 'not your owner')
    now = int(time.time())
    row = conn.execute('SELECT grant_until, settings_until FROM account_state WHERE account_id = %s FOR UPDATE',
                       (account_id,)).fetchone()
    grant_until, settings_until = apply_grant(body.tier, now, row['grant_until'], row['settings_until'])
    conn.execute('UPDATE account_state SET grant_until = %s, settings_until = %s WHERE account_id = %s',
                 (grant_until, settings_until, account_id))
    return {'ok': True, 'grant_until': grant_until, 'settings_until': settings_until, 'now': now}


@app.post('/api/p/accounts/{account_id}/leave')
def leave(account_id: uuid.UUID, partner_id: str = Depends(partner_of), conn=Depends(db)):
    """A partner ends its own role for one owner. Always allowed."""
    deleted = conn.execute('DELETE FROM links WHERE account_id = %s AND partner_id = %s RETURNING account_id',
                           (str(account_id), partner_id)).fetchone()
    if deleted is None:
        raise HTTPException(404, 'not your owner')
    return {'ok': True}


@app.get('/partner')
def partner_page():
    return FileResponse(HERE / 'static' / 'partner.html')


@app.get('/')
def root():
    return {'service': 'gyst', 'partner_page': '/partner'}
