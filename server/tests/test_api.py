import base64
import os
import sys
import time
import unittest
import uuid
from pathlib import Path

os.environ.setdefault('DATABASE_URL', 'postgresql://postgres:test@localhost:55432/gyst')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app as server  # noqa: E402
from gating import grant_message  # noqa: E402

BASE_SETTINGS = {
    'enabled': True, 'sites': ['youtube.com'], 'popupMessage': '', 'blockMessage': '',
    'language': 'auto', 'unlock': 'text', 'free_windows': [],
}


def reset_db():
    server.init_schema()
    with server.connect() as conn:
        conn.execute('TRUNCATE grant_log, partners, invites, account_state, accounts CASCADE')


class ApiTest(unittest.TestCase):
    def setUp(self):
        reset_db()
        self.client = TestClient(server.app)
        self.account = self.client.post('/api/accounts').json()
        self.auth = {'Authorization': f"Bearer {self.account['token']}"}
        self.client.put('/api/settings', json=BASE_SETTINGS, headers=self.auth)  # first save: setup, no grant

    def partner(self, name='p'):
        key = Ed25519PrivateKey.generate()
        pub = key.public_key().public_bytes_raw().hex()
        invite = self.client.post('/api/invites', headers=self.auth).json()['code']
        r = self.client.post('/api/partners/register', json={'invite': invite, 'pubkey': pub, 'name': name})
        self.assertEqual(r.status_code, 200, r.text)
        return key, pub

    def sign(self, key, tier, stamp=None, account_id=None):
        stamp = stamp or int(time.time())
        msg = grant_message(account_id or self.account['account_id'], tier, stamp)
        return {'account_id': account_id or self.account['account_id'], 'tier': tier, 'stamp': stamp,
                'signature': base64.b64encode(key.sign(msg)).decode(), 'pubkey': key.public_key().public_bytes_raw().hex()}

    def grant(self, key, tier, **kw):
        body = self.sign(key, tier, **kw)
        return self.client.post('/api/grant', json=body)

    def test_state_and_defaults(self):
        state = self.client.get('/api/state', headers=self.auth).json()
        self.assertEqual(state['settings']['sites'], ['youtube.com'])
        self.assertEqual(state['grant_until'], 0)

    def test_unknown_token_rejected(self):
        self.assertEqual(self.client.get('/api/state', headers={'Authorization': 'Bearer nope'}).status_code, 401)

    def test_without_partner_nothing_is_gated(self):
        self.assertEqual(self.client.put('/api/settings', headers=self.auth, json={**BASE_SETTINGS, 'enabled': False}).status_code, 200)

    def test_adding_sites_and_enabling_free_but_disable_gated(self):
        self.partner()
        self.assertEqual(self.client.put('/api/settings', headers=self.auth,
                                         json={**BASE_SETTINGS, 'sites': ['youtube.com', 'x.com']}).status_code, 200)
        r = self.client.put('/api/settings', headers=self.auth, json={**BASE_SETTINGS, 'enabled': False})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()['detail']['error'], 'grant_required')

    def test_partner_count_in_state(self):
        self.partner()
        self.assertEqual(self.client.get('/api/state', headers=self.auth).json()['partners'], 1)

    def test_time_grant_allows_gated_change(self):
        key, _ = self.partner()
        self.assertEqual(self.grant(key, 1).status_code, 200)
        r = self.client.put('/api/settings', headers=self.auth, json={**BASE_SETTINGS, 'enabled': False})
        self.assertEqual(r.status_code, 200)
        self.assertGreater(self.client.get('/api/state', headers=self.auth).json()['grant_until'], time.time())

    def test_settings_grant_is_consumed_by_one_save(self):
        key, _ = self.partner()
        self.client.put('/api/settings', headers=self.auth, json={**BASE_SETTINGS, 'sites': ['youtube.com', 'b.com']})
        self.assertEqual(self.grant(key, 3).status_code, 200)
        self.assertEqual(self.client.put('/api/settings', headers=self.auth,
                                         json={**BASE_SETTINGS, 'sites': []}).status_code, 200)
        r = self.client.put('/api/settings', headers=self.auth, json={**BASE_SETTINGS, 'sites': ['a.com']})
        self.assertEqual(r.status_code, 200)  # adding a site is always free
        r = self.client.put('/api/settings', headers=self.auth, json={**BASE_SETTINGS, 'sites': []})
        self.assertEqual(r.status_code, 403)

    def test_replayed_stamp_rejected(self):
        key, _ = self.partner()
        stamp = int(time.time())
        self.assertEqual(self.grant(key, 0, stamp=stamp).status_code, 200)
        self.assertEqual(self.grant(key, 0, stamp=stamp).status_code, 409)

    def test_wrong_key_and_unknown_partner_rejected(self):
        key, _ = self.partner()
        other = Ed25519PrivateKey.generate()
        body = self.sign(key, 0)
        body['pubkey'] = other.public_key().public_bytes_raw().hex()
        self.assertEqual(self.client.post('/api/grant', json=body).status_code, 403)

    def test_signature_bound_to_account(self):
        key, _ = self.partner()
        other_account = self.client.post('/api/accounts').json()
        body = self.sign(key, 0)
        body['account_id'] = other_account['account_id']  # signed for the first account, sent for another
        self.assertEqual(self.client.post('/api/grant', json=body).status_code, 403)

    def test_old_stamp_rejected(self):
        key, _ = self.partner()
        self.assertEqual(self.grant(key, 0, stamp=int(time.time()) - 3600).status_code, 403)

    def test_invite_single_use(self):
        invite = self.client.post('/api/invites', headers=self.auth).json()['code']
        pub = Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex()
        self.assertEqual(self.client.post('/api/partners/register', json={'invite': invite, 'pubkey': pub}).status_code, 200)
        self.assertEqual(self.client.post('/api/partners/register', json={'invite': invite, 'pubkey': pub}).status_code, 400)

    def test_multiple_partners_per_account(self):
        a, _ = self.partner('a')
        b, _ = self.partner('b')
        stamp = int(time.time())
        self.assertEqual(self.grant(a, 0, stamp=stamp).status_code, 200)
        self.assertEqual(self.grant(b, 1, stamp=stamp + 1).status_code, 200)

    def test_accounts_are_isolated(self):
        other = self.client.post('/api/accounts').json()
        self.client.put('/api/settings', headers={'Authorization': f"Bearer {other['token']}"},
                        json={**BASE_SETTINGS, 'sites': ['other.com']})
        state = self.client.get('/api/state', headers=self.auth).json()
        self.assertEqual(state['settings']['sites'], ['youtube.com'])

    def test_invalid_free_window_rejected(self):
        r = self.client.put('/api/settings', headers=self.auth,
                            json={**BASE_SETTINGS, 'free_windows': [{'day': 9, 'from': '10:00', 'to': '11:00'}]})
        self.assertEqual(r.status_code, 422)


if __name__ == '__main__':
    unittest.main()
