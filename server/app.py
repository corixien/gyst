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

from gating import DEVICE_DOMAIN, INVITE_DOMAIN, LEAVE_DOMAIN, TIERS, account_message, setup_message, verify_grant, verify_signed

HERE = Path(__file__).parent
SCHEMA = (HERE / 'schema.sql').read_text()
INVITE_DAYS = 1
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


def account_for(token: str | None, conn) -> str:
    if not token:
        raise HTTPException(401, 'token required')
    row = conn.execute('SELECT account_id AS id FROM devices WHERE token_hash = %s', (sha(token),)).fetchone()
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
    displayName: str = Field(default='', max_length=40)
    free_windows: list[dict] = Field(max_length=MAX_WINDOWS)


class SiteIn(BaseModel):
    domain: str = Field(min_length=1, max_length=253)


class EnabledIn(BaseModel):
    enabled: bool


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


class SetupIn(BaseModel):
    pubkey: str = Field(pattern=r'^[0-9a-f]{64}$')
    name: str = Field(default='', max_length=60)
    stamp: int
    signature: str


class PartnerActionIn(BaseModel):
    account_id: uuid.UUID
    pubkey: str = Field(pattern=r'^[0-9a-f]{64}$')
    stamp: int
    signature: str


class ClaimIn(BaseModel):
    code: str = Field(min_length=4, max_length=20)


class RemoveIn(BaseModel):
    partner_id: uuid.UUID


class LeaveIn(BaseModel):
    account_id: str
    pubkey: str = Field(pattern=r'^[0-9a-f]{64}$')
    stamp: int
    signature: str


def valid_window(w: dict) -> bool:
    hhmm = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')
    return (isinstance(w.get('day'), int) and 0 <= w['day'] <= 6
            and isinstance(w.get('from'), str) and hhmm.match(w['from'])
            and isinstance(w.get('to'), str) and hhmm.match(w['to']) is not None)


def partner_action(conn, body: PartnerActionIn, domain: bytes) -> None:
    """Checks a request signed by a partner of the account and consumes its stamp."""
    now = int(time.time())
    account_id = str(body.account_id)
    if conn.execute('SELECT 1 FROM partners WHERE account_id = %s AND pubkey = %s', (account_id, body.pubkey)).fetchone() is None:
        raise HTTPException(403, 'unknown partner')
    if not verify_signed(body.pubkey, account_message(domain, account_id, body.stamp), body.signature, body.stamp, now):
        raise HTTPException(403, 'signature invalid or stamp too old')
    row = conn.execute('SELECT last_stamp FROM account_state WHERE account_id = %s FOR UPDATE', (account_id,)).fetchone()
    if row is None:
        raise HTTPException(404, 'account not found')
    if body.stamp <= row['last_stamp']:
        raise HTTPException(409, 'token already used')
    conn.execute('UPDATE account_state SET last_stamp = %s WHERE account_id = %s', (body.stamp, account_id))


def new_code() -> str:
    raw = ''.join(secrets.choice('ABCDEFGHJKMNPQRSTUVWXYZ23456789') for _ in range(8))
    return f'{raw[:4]}-{raw[4:]}'


def normalize_code(code: str) -> str:
    return code.replace('-', '').replace(' ', '').upper()


@app.post('/api/partner-setup')
def partner_setup(body: SetupIn, conn=Depends(db)):
    """A partner creates an account. The partner is its first partner, so no owner ever creates an account itself."""
    now = int(time.time())
    if not verify_signed(body.pubkey, setup_message(body.pubkey, body.stamp), body.signature, body.stamp, now):
        raise HTTPException(403, 'signature invalid or stamp too old')
    account_id = uuid.uuid4()
    unusable_token = secrets.token_urlsafe(32)  # no one gets it: owners use device tokens only
    conn.execute('INSERT INTO accounts (id, token_hash) VALUES (%s, %s)', (account_id, sha(unusable_token)))
    conn.execute('INSERT INTO account_state (account_id) VALUES (%s)', (account_id,))
    conn.execute('INSERT INTO partners (id, account_id, pubkey, name) VALUES (%s, %s, %s, %s)',
                 (uuid.uuid4(), account_id, body.pubkey, body.name.strip()))
    return {'account_id': str(account_id)}


@app.post('/api/partner/device-codes')
def device_code(body: PartnerActionIn, conn=Depends(db)):
    """A partner issues a one-time code (10 min) that the owner enters to connect a device."""
    partner_action(conn, body, DEVICE_DOMAIN)
    code = new_code()
    conn.execute("INSERT INTO device_codes (code_hash, account_id, expires_at) VALUES (%s, %s, now() + interval '10 minutes')",
                 (sha(normalize_code(code)), str(body.account_id)))
    return {'code': code, 'expires_in_minutes': 10}


@app.post('/api/devices/claim')
def claim_device(body: ClaimIn, conn=Depends(db)):
    row = conn.execute(
        'DELETE FROM device_codes WHERE code_hash = %s AND expires_at > now() RETURNING account_id',
        (sha(normalize_code(body.code)),),
    ).fetchone()
    if row is None:
        raise HTTPException(400, 'code invalid, expired or used')
    token = secrets.token_urlsafe(32)
    conn.execute('INSERT INTO devices (token_hash, account_id) VALUES (%s, %s)', (sha(token), row['account_id']))
    return {'account_id': str(row['account_id']), 'token': token}


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


def locked_state(conn, account_id):
    row = conn.execute('SELECT settings, free_windows, grant_until, settings_until FROM account_state WHERE account_id = %s FOR UPDATE',
                       (account_id,)).fetchone()
    partner = conn.execute('SELECT 1 FROM partners WHERE account_id = %s LIMIT 1', (account_id,)).fetchone() is not None
    return row, partner


@app.put('/api/settings')
def put_settings(body: SettingsIn, account_id: str = Depends(auth), conn=Depends(db)):
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
def add_site(body: SiteIn, account_id: str = Depends(auth), conn=Depends(db)):
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
def set_enabled(body: EnabledIn, account_id: str = Depends(auth), conn=Depends(db)):
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
def list_partners(account_id: str = Depends(auth), conn=Depends(db)):
    rows = conn.execute('SELECT id, name, created_at FROM partners WHERE account_id = %s ORDER BY created_at',
                        (account_id,)).fetchall()
    return {'partners': [{'id': str(r['id']), 'name': r['name'] or 'Unbenannt', 'since': r['created_at'].isoformat()}
                         for r in rows]}


@app.post('/api/partners/remove')
def remove_partner(body: RemoveIn, account_id: str = Depends(auth), conn=Depends(db)):
    """Owner removes a partner. Needs a running time grant, like switching the block off; otherwise the owner
    could drop the partners that gate everything else."""
    row, _ = locked_state(conn, account_id)
    if row['grant_until'] <= int(time.time()):
        raise HTTPException(403, {'error': 'grant_required'})
    deleted = conn.execute('DELETE FROM partners WHERE id = %s AND account_id = %s RETURNING id',
                           (body.partner_id, account_id)).fetchone()
    if deleted is None:
        raise HTTPException(404, 'partner not found')
    return {'ok': True}


@app.post('/api/partners/leave')
def leave_account(body: LeaveIn, conn=Depends(db)):
    """Partner ends its own role for one account. Signed with the partner key, always allowed."""
    now = int(time.time())
    if not verify_signed(body.pubkey, account_message(LEAVE_DOMAIN, body.account_id, body.stamp), body.signature, body.stamp, now):
        raise HTTPException(403, 'signature invalid or stamp too old')
    row = conn.execute('SELECT last_stamp FROM account_state WHERE account_id = %s FOR UPDATE', (body.account_id,)).fetchone()
    if row is None:
        raise HTTPException(404, 'account not found')
    if body.stamp <= row['last_stamp']:
        raise HTTPException(409, 'token already used')
    deleted = conn.execute('DELETE FROM partners WHERE account_id = %s AND pubkey = %s RETURNING id',
                           (body.account_id, body.pubkey)).fetchone()
    if deleted is None:
        raise HTTPException(403, 'unknown partner')
    conn.execute('UPDATE account_state SET last_stamp = %s WHERE account_id = %s', (body.stamp, body.account_id))
    return {'ok': True}


@app.post('/api/partner/invites')
def create_invite(body: PartnerActionIn, conn=Depends(db)):
    """Only a partner can invite another partner (a device cannot), so an owner cannot add themselves."""
    partner_action(conn, body, INVITE_DOMAIN)
    code = f'{body.account_id}.{secrets.token_urlsafe(16)}'
    conn.execute(
        "INSERT INTO invites (code_hash, account_id, expires_at) VALUES (%s, %s, now() + make_interval(days => %s))",
        (sha(code), str(body.account_id), INVITE_DAYS),
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
        (partner_id, invite['account_id'], body.pubkey, body.name.strip()),
    )
    owner = conn.execute('SELECT settings FROM account_state WHERE account_id = %s', (invite['account_id'],)).fetchone()
    return {'account_id': str(invite['account_id']), 'owner_name': (owner['settings'] or {}).get('displayName', '')}


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
    if tier == 'end':
        conn.execute('UPDATE account_state SET grant_until = 0, settings_until = 0, last_stamp = %s WHERE account_id = %s',
                     (body.stamp, body.account_id))
    elif tier == 'settings':
        conn.execute('UPDATE account_state SET settings_until = %s, last_stamp = %s WHERE account_id = %s',
                     (now + minutes, body.stamp, body.account_id))
    else:
        grant_until = max(row['grant_until'], now) + minutes
        conn.execute('UPDATE account_state SET grant_until = %s, last_stamp = %s WHERE account_id = %s',
                     (grant_until, body.stamp, body.account_id))
    conn.execute('INSERT INTO grant_log (account_id, partner_id, tier) VALUES (%s, %s, %s)',
                 (body.account_id, partner['id'], tier))
    state = conn.execute('SELECT grant_until, settings_until FROM account_state WHERE account_id = %s',
                         (body.account_id,)).fetchone()
    return {'ok': True, 'tier': tier, 'grant_until': state['grant_until'], 'settings_until': state['settings_until'], 'now': now}


@app.get('/partner')
def partner_page():
    return FileResponse(HERE / 'static' / 'partner.html')


@app.get('/')
def root():
    return {'service': 'gyst', 'partner_page': '/partner'}
