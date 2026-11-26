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
from gating import DEVICE_DOMAIN, INVITE_DOMAIN, LEAVE_DOMAIN, account_message, grant_message, setup_message  # noqa: E402

BASE_SETTINGS = {
    'enabled': True, 'sites': ['youtube.com'], 'popupMessage': '', 'blockMessage': '',
    'language': 'auto', 'unlock': 'text', 'free_windows': [],
}


def reset_db():
    server.init_schema()
    with server.connect() as conn:
        conn.execute('TRUNCATE device_codes, devices, grant_log, partners, invites, account_state, accounts CASCADE')


def pub_hex(key):
    return key.public_key().public_bytes_raw().hex()


def sig_b64(key, message):
    return base64.b64encode(key.sign(message)).decode()


class ApiTest(unittest.TestCase):
    """Every account starts with the partner that set it up. Owners only hold device tokens."""

    def setUp(self):
        reset_db()
        self.client = TestClient(server.app)
        self.key = Ed25519PrivateKey.generate()
        self.t = int(time.time())
        stamp = self.tick()
        r = self.client.post('/api/partner-setup', json={
            'pubkey': pub_hex(self.key), 'name': 'p0', 'stamp': stamp,
            'signature': sig_b64(self.key, setup_message(pub_hex(self.key), stamp))})
        self.assertEqual(r.status_code, 200, r.text)
        self.account_id = r.json()['account_id']
        self.token = self.claim(self.device_code(self.key, self.account_id))
        self.auth = {'Authorization': f'Bearer {self.token}'}
        self.client.put('/api/settings', json=BASE_SETTINGS, headers=self.auth)  # first save: setup, no grant

    def tick(self):
        self.t = max(int(time.time()), self.t + 1)  # every partner-signed request needs a newer stamp
        return self.t

    def device_code(self, key, account_id, stamp=None):
        stamp = stamp or self.tick()
        body = self.signed_action(key, account_id, DEVICE_DOMAIN, stamp)
        r = self.client.post('/api/partner/device-codes', json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()['code']

    def claim(self, code):
        r = self.client.post('/api/devices/claim', json={'code': code})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()['token']

    def signed_action(self, key, account_id, domain, stamp):
        return {'account_id': account_id, 'pubkey': pub_hex(key), 'stamp': stamp,
                'signature': sig_b64(key, account_message(domain, account_id, stamp))}

    def partner(self, name='p'):
        key = Ed25519PrivateKey.generate()
        stamp = self.tick()
        invite = self.client.post('/api/partner/invites', json=self.signed_action(self.key, self.account_id, INVITE_DOMAIN, stamp))
        self.assertEqual(invite.status_code, 200, invite.text)
        r = self.client.post('/api/partners/register', json={'invite': invite.json()['code'], 'pubkey': pub_hex(key), 'name': name})
        self.assertEqual(r.status_code, 200, r.text)
        return key, pub_hex(key)

    def new_account(self):
        key = Ed25519PrivateKey.generate()
        stamp = self.tick()
        r = self.client.post('/api/partner-setup', json={
            'pubkey': pub_hex(key), 'name': 'other', 'stamp': stamp,
            'signature': sig_b64(key, setup_message(pub_hex(key), stamp))})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()['account_id'], key

    def invite_code(self):
        r = self.client.post('/api/partner/invites', json=self.signed_action(self.key, self.account_id, INVITE_DOMAIN, self.tick()))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()['code']

    def no_partner(self):
        r = self.client.post('/api/partners/leave', json=self.leave_body(self.key))
        self.assertEqual(r.status_code, 200, r.text)

    def leave_body(self, key, stamp=None, account_id=None):
        stamp = stamp or self.tick()
        account_id = account_id or self.account_id
        return self.signed_action(key, account_id, LEAVE_DOMAIN, stamp)

    def sign(self, key, tier, stamp=None, account_id=None):
        stamp = stamp or self.tick()
        account_id = account_id or self.account_id
        msg = grant_message(account_id, tier, stamp)
        return {'account_id': account_id, 'tier': tier, 'stamp': stamp,
                'signature': sig_b64(key, msg), 'pubkey': pub_hex(key)}

    def grant(self, key, tier, **kw):
        body = self.sign(key, tier, **kw)
        return self.client.post('/api/grant', json=body)

    def test_state_and_defaults(self):
        state = self.client.get('/api/state', headers=self.auth).json()
        self.assertEqual(state['settings']['sites'], ['youtube.com'])
        self.assertEqual(state['grant_until'], 0)

    def test_unknown_token_rejected(self):
        self.assertEqual(self.client.get('/api/state', headers={'Authorization': 'Bearer nope'}).status_code, 401)

    def test_no_public_account_or_invite_creation(self):
        self.assertIn(self.client.post('/api/accounts').status_code, (404, 405))
        self.assertIn(self.client.post('/api/invites', headers=self.auth).status_code, (404, 405))

    def test_owner_device_cannot_invite_or_setup(self):
        # Only a partner signature can create invites; a device token has no way to sign one.
        self.assertEqual(self.client.post('/api/partner/invites', json=self.signed_action(
            Ed25519PrivateKey.generate(), self.account_id, INVITE_DOMAIN, self.tick())).status_code, 403)

    def test_device_code_single_use_and_wrong_code(self):
        code = self.device_code(self.key, self.account_id)
        self.assertEqual(self.client.post('/api/devices/claim', json={'code': code.lower()}).status_code, 200)
        self.assertEqual(self.client.post('/api/devices/claim', json={'code': code}).status_code, 400)
        self.assertEqual(self.client.post('/api/devices/claim', json={'code': 'ZZZZ-ZZZZ'}).status_code, 400)

    def test_setup_needs_valid_signature(self):
        key = Ed25519PrivateKey.generate()
        stamp = self.tick()
        r = self.client.post('/api/partner-setup', json={
            'pubkey': pub_hex(key), 'name': 'x', 'stamp': stamp,
            'signature': sig_b64(self.key, setup_message(pub_hex(key), stamp))})
        self.assertEqual(r.status_code, 403)

    def test_device_code_needs_partner_and_fresh_stamp(self):
        other = Ed25519PrivateKey.generate()
        stamp = self.tick()
        self.assertEqual(self.client.post('/api/partner/device-codes',
                                          json=self.signed_action(other, self.account_id, DEVICE_DOMAIN, stamp)).status_code, 403)
        self.assertEqual(self.client.post('/api/partner/device-codes',
                                          json=self.signed_action(self.key, self.account_id, DEVICE_DOMAIN, stamp - 1000)).status_code, 403)
        self.assertEqual(self.client.post('/api/partner/device-codes',
                                          json=self.signed_action(self.key, self.account_id, DEVICE_DOMAIN, stamp)).status_code, 200)
        self.assertEqual(self.client.post('/api/partner/device-codes',
                                          json=self.signed_action(self.key, self.account_id, DEVICE_DOMAIN, stamp)).status_code, 409)

    def test_without_partner_save_and_disable_are_free(self):
        self.no_partner()
        self.assertEqual(self.client.put('/api/settings', headers=self.auth, json={**BASE_SETTINGS, 'enabled': False}).status_code, 200)

    def test_save_needs_grant_when_partner_exists(self):
        self.partner()
        r = self.client.put('/api/settings', headers=self.auth, json={**BASE_SETTINGS, 'popupMessage': 'x'})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()['detail']['error'], 'grant_required')

    def test_adding_site_is_free_even_with_partner(self):
        self.partner()
        r = self.client.post('/api/sites', headers=self.auth, json={'domain': 'X.com'})
        self.assertEqual(r.status_code, 200)
        self.assertIn('x.com', r.json()['sites'])

    def test_invalid_domain_rejected(self):
        self.assertEqual(self.client.post('/api/sites', headers=self.auth, json={'domain': 'not a domain'}).status_code, 422)

    def test_enable_free_disable_needs_time_grant(self):
        key, _ = self.partner()
        self.assertEqual(self.client.post('/api/enabled', headers=self.auth, json={'enabled': False}).status_code, 403)
        self.assertEqual(self.grant(key, 3).status_code, 200)  # settings grant is not enough to switch off
        self.assertEqual(self.client.post('/api/enabled', headers=self.auth, json={'enabled': False}).status_code, 403)
        self.assertEqual(self.grant(key, 0, stamp=self.tick()).status_code, 200)
        self.assertEqual(self.client.post('/api/enabled', headers=self.auth, json={'enabled': False}).status_code, 200)
        self.assertEqual(self.client.post('/api/enabled', headers=self.auth, json={'enabled': True}).status_code, 200)

    def test_time_grant_allows_save(self):
        key, _ = self.partner()
        self.assertEqual(self.grant(key, 1).status_code, 200)
        self.assertEqual(self.client.put('/api/settings', headers=self.auth, json={**BASE_SETTINGS, 'enabled': False}).status_code, 200)
        self.assertGreater(self.client.get('/api/state', headers=self.auth).json()['grant_until'], time.time())

    def test_settings_grant_is_used_up_by_one_save(self):
        key, _ = self.partner()
        self.assertEqual(self.grant(key, 3).status_code, 200)
        self.assertEqual(self.client.put('/api/settings', headers=self.auth, json={**BASE_SETTINGS, 'popupMessage': 'a'}).status_code, 200)
        r = self.client.put('/api/settings', headers=self.auth, json={**BASE_SETTINGS, 'popupMessage': 'b'})
        self.assertEqual(r.status_code, 403)

    def test_end_grant_stops_time_and_settings(self):
        key, _ = self.partner()
        self.assertEqual(self.grant(key, 1).status_code, 200)
        self.assertEqual(self.grant(key, 3, stamp=self.tick()).status_code, 200)
        r = self.grant(key, 4, stamp=self.tick())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['grant_until'], 0)
        self.assertEqual(r.json()['settings_until'], 0)

    def test_grant_response_has_times_for_feedback(self):
        key, _ = self.partner()
        r = self.grant(key, 1).json()
        self.assertGreater(r['grant_until'], r['now'])

    def test_replayed_stamp_rejected(self):
        key, _ = self.partner()
        stamp = self.tick()
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
        body = self.sign(key, 0)
        body['account_id'] = self.new_account()[0]
        self.assertEqual(self.client.post('/api/grant', json=body).status_code, 403)

    def test_old_stamp_rejected(self):
        key, _ = self.partner()
        self.assertEqual(self.grant(key, 0, stamp=int(time.time()) - 3600).status_code, 403)

    def test_invite_single_use_and_returns_owner_name(self):
        self.assertEqual(self.grant(self.key, 1).status_code, 200)
        self.client.put('/api/settings', headers=self.auth, json={**BASE_SETTINGS, 'displayName': 'Mateo'})
        invite = self.invite_code()
        pub = Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex()
        r = self.client.post('/api/partners/register', json={'invite': invite, 'pubkey': pub, 'name': 'Anna'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['owner_name'], 'Mateo')
        self.assertEqual(self.client.post('/api/partners/register', json={'invite': invite, 'pubkey': pub}).status_code, 400)

    def test_partner_list_shows_names(self):
        self.partner('Anna')
        names = self.client.get('/api/partners', headers=self.auth).json()['partners']
        self.assertEqual([p['name'] for p in names], ['p0', 'Anna'])

    def test_multiple_partners_per_account(self):
        a, _ = self.partner('a')
        b, _ = self.partner('b')
        stamp = self.tick()
        self.assertEqual(self.grant(a, 0, stamp=stamp).status_code, 200)
        self.assertEqual(self.grant(b, 1, stamp=stamp + 1).status_code, 200)

    def test_accounts_are_isolated(self):
        other_id, other_key = self.new_account()
        other_auth = {'Authorization': f'Bearer {self.claim(self.device_code(other_key, other_id))}'}
        self.client.put('/api/settings', headers=other_auth, json={**BASE_SETTINGS, 'sites': ['other.com']})
        state = self.client.get('/api/state', headers=self.auth).json()
        self.assertEqual(state['settings']['sites'], ['youtube.com'])

    def test_enable_ends_running_grant(self):
        key, _ = self.partner()
        self.assertEqual(self.grant(key, 1).status_code, 200)
        self.assertEqual(self.client.post('/api/enabled', headers=self.auth, json={'enabled': True}).status_code, 200)
        self.assertEqual(self.client.get('/api/state', headers=self.auth).json()['grant_until'], 0)
        self.assertEqual(self.client.post('/api/enabled', headers=self.auth, json={'enabled': False}).status_code, 403)

    def test_settings_grant_cannot_switch_block_off(self):
        key, _ = self.partner()
        self.assertEqual(self.grant(key, 3).status_code, 200)
        r = self.client.put('/api/settings', headers=self.auth, json={**BASE_SETTINGS, 'enabled': False})
        self.assertEqual(r.status_code, 403)

    def test_owner_remove_partner_needs_grant(self):
        key, _ = self.partner('Anna')
        partner_id = [p for p in self.client.get('/api/partners', headers=self.auth).json()['partners'] if p['name'] == 'Anna'][0]['id']
        self.assertEqual(self.client.post('/api/partners/remove', headers=self.auth, json={'partner_id': partner_id}).status_code, 403)
        self.assertEqual(self.grant(key, 1).status_code, 200)
        self.assertEqual(self.client.post('/api/partners/remove', headers=self.auth, json={'partner_id': partner_id}).status_code, 200)
        self.assertEqual(self.client.get('/api/state', headers=self.auth).json()['partners'], 1)  # p0 stays

    def test_owner_remove_rejects_bad_or_unknown_id(self):
        key, _ = self.partner()
        self.assertEqual(self.grant(key, 1).status_code, 200)
        self.assertEqual(self.client.post('/api/partners/remove', headers=self.auth, json={'partner_id': 'nope'}).status_code, 422)
        self.assertEqual(self.client.post('/api/partners/remove', headers=self.auth,
                                          json={'partner_id': str(uuid.uuid4())}).status_code, 404)

    def test_partner_leave_is_free_and_final(self):
        key, _ = self.partner()
        r = self.client.post('/api/partners/leave', json=self.leave_body(key))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.client.get('/api/state', headers=self.auth).json()['partners'], 1)
        self.assertIn(self.client.post('/api/partners/leave', json=self.leave_body(key)).status_code, (403, 409))
        self.assertEqual(self.grant(key, 0).status_code, 403)

    def test_leave_needs_valid_signature_and_fresh_stamp(self):
        key, _ = self.partner()
        body = self.leave_body(key)
        body['signature'] = base64.b64encode(key.sign(b'other')).decode()
        self.assertEqual(self.client.post('/api/partners/leave', json=body).status_code, 403)
        old = self.leave_body(key, stamp=int(time.time()) - 3600)
        self.assertEqual(self.client.post('/api/partners/leave', json=old).status_code, 403)
        self.assertEqual(self.client.get('/api/state', headers=self.auth).json()['partners'], 2)

    def test_leave_replay_rejected_for_other_partner_stamp(self):
        key, _ = self.partner('a')
        other, _ = self.partner('b')
        stamp = self.tick()
        self.assertEqual(self.grant(key, 0, stamp=stamp).status_code, 200)
        self.assertEqual(self.client.post('/api/partners/leave', json=self.leave_body(other, stamp=stamp)).status_code, 409)

    def test_invalid_free_window_rejected(self):
        r = self.client.put('/api/settings', headers=self.auth,
                            json={**BASE_SETTINGS, 'free_windows': [{'day': 9, 'from': '10:00', 'to': '11:00'}]})
        self.assertEqual(r.status_code, 422)


if __name__ == '__main__':
    unittest.main()
