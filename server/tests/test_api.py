import os
import sys
import time
import unittest
from pathlib import Path

os.environ.setdefault('DATABASE_URL', 'postgresql://postgres:test@localhost:55432/gyst')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import app as server  # noqa: E402
from gating import hash_password, verify_password  # noqa: E402

BASE_SETTINGS = {
    'enabled': True, 'sites': ['youtube.com'], 'popupMessage': '', 'blockMessage': '',
    'language': 'auto', 'unlock': 'text', 'free_windows': [],
}


def reset_db():
    server.init_schema()
    with server.connect() as conn:
        conn.execute('TRUNCATE partner_sessions, partner_users, pairings, claims, devices, links, account_state, accounts CASCADE')


class ApiTest(unittest.TestCase):
    def setUp(self):
        reset_db()
        self.client = TestClient(server.app)
        self.p1 = self.partner('anna')  # partner headers
        self.owner_id, self.owner = self.new_owner(self.p1)  # owner headers
        self.client.put('/api/settings', json=BASE_SETTINGS, headers=self.owner)  # first save: setup, no grant

    # helpers
    def partner(self, username, password='geheim123'):
        r = self.client.post('/api/p/signup', json={'username': username, 'password': password})
        self.assertEqual(r.status_code, 200, r.text)
        return {'Authorization': f"Bearer {r.json()['token']}"}

    def new_owner(self, partner_headers):
        r = self.client.post('/api/p/accounts', headers=partner_headers)
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        claim = self.client.post('/api/devices/claim', json={'partner_username': data['partner_username'], 'code': data['code']})
        self.assertEqual(claim.status_code, 200, claim.text)
        return data['account_id'], {'Authorization': f"Bearer {claim.json()['token']}"}

    def grant(self, partner_headers, tier, account_id=None):
        return self.client.post(f'/api/p/accounts/{account_id or self.owner_id}/grant', json={'tier': tier}, headers=partner_headers)

    def pair(self, inviter, invitee_username, account_id=None):
        return self.client.post(f'/api/p/accounts/{account_id or self.owner_id}/pairings',
                                json={'username': invitee_username}, headers=inviter)

    def test_signup_login_and_username_rules(self):
        self.assertEqual(self.client.post('/api/p/signup', json={'username': 'anna', 'password': 'geheim123'}).status_code, 409)
        self.assertEqual(self.client.post('/api/p/signup', json={'username': 'Bad Name', 'password': 'geheim123'}).status_code, 422)
        self.assertEqual(self.client.post('/api/p/login', json={'username': 'anna', 'password': 'falsch99'}).status_code, 401)
        r = self.client.post('/api/p/login', json={'username': 'ANNA', 'password': 'geheim123'})
        self.assertEqual(r.status_code, 200)
        me = self.client.get('/api/p/me', headers={'Authorization': f"Bearer {r.json()['token']}"})
        self.assertEqual(me.json()['username'], 'anna')

    def test_logout_ends_session(self):
        self.assertEqual(self.client.post('/api/p/logout', headers=self.p1).status_code, 200)
        self.assertEqual(self.client.get('/api/p/accounts', headers=self.p1).status_code, 401)

    def test_password_hash_roundtrip(self):
        stored = hash_password('geheim123')
        self.assertTrue(verify_password('geheim123', stored))
        self.assertFalse(verify_password('geheim124', stored))

    def test_no_public_account_or_invite_routes(self):
        self.assertIn(self.client.post('/api/accounts').status_code, (404, 405))
        self.assertIn(self.client.post('/api/invites', headers=self.owner).status_code, (404, 405))

    def test_owner_device_cannot_use_partner_routes(self):
        self.assertEqual(self.client.get('/api/p/accounts', headers=self.owner).status_code, 401)
        self.assertEqual(self.client.post('/api/p/accounts', headers=self.owner).status_code, 401)
        self.assertEqual(self.pair(self.owner, 'anna').status_code, 401)

    def test_claim_needs_right_partner_name_and_is_single_use(self):
        r = self.client.post('/api/p/accounts', headers=self.p1).json()
        wrong = self.client.post('/api/devices/claim', json={'partner_username': 'nobody', 'code': r['code']})
        self.assertEqual(wrong.status_code, 400)
        ok = self.client.post('/api/devices/claim', json={'partner_username': 'anna', 'code': r['code'].lower()})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(self.client.post('/api/devices/claim', json={'partner_username': 'anna', 'code': r['code']}).status_code, 400)

    def test_claim_fails_for_partner_not_linked_to_owner(self):
        carl = self.partner('carl')
        r = self.client.post('/api/p/accounts', headers=carl).json()
        self.client.post(f"/api/p/accounts/{r['account_id']}/leave", headers=carl)
        self.assertEqual(self.client.post('/api/devices/claim', json={'partner_username': 'carl', 'code': r['code']}).status_code, 400)

    def test_extra_device_code_by_partner(self):
        code = self.client.post(f'/api/p/accounts/{self.owner_id}/device-codes', headers=self.p1)
        self.assertEqual(code.status_code, 200)
        r = self.client.post('/api/devices/claim', json={'partner_username': 'anna', 'code': code.json()['code']})
        self.assertEqual(r.status_code, 200)
        state = self.client.get('/api/state', headers={'Authorization': f"Bearer {r.json()['token']}"})
        self.assertEqual(state.status_code, 200)

    def test_save_needs_grant_with_partner(self):
        r = self.client.put('/api/settings', headers=self.owner, json={**BASE_SETTINGS, 'popupMessage': 'x'})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()['detail']['error'], 'grant_required')
        self.assertEqual(self.grant(self.p1, '1h').status_code, 200)
        self.assertEqual(self.client.put('/api/settings', headers=self.owner, json={**BASE_SETTINGS, 'popupMessage': 'x'}).status_code, 200)

    def test_adding_site_is_free_even_with_partner(self):
        r = self.client.post('/api/sites', headers=self.owner, json={'domain': 'X.com'})
        self.assertEqual(r.status_code, 200)
        self.assertIn('x.com', r.json()['sites'])

    def test_enable_free_disable_needs_time_grant_and_enable_ends_grant(self):
        self.assertEqual(self.client.post('/api/enabled', headers=self.owner, json={'enabled': False}).status_code, 403)
        self.assertEqual(self.grant(self.p1, 'settings').status_code, 200)
        self.assertEqual(self.client.post('/api/enabled', headers=self.owner, json={'enabled': False}).status_code, 403)
        self.assertEqual(self.grant(self.p1, '1h').status_code, 200)
        self.assertEqual(self.client.post('/api/enabled', headers=self.owner, json={'enabled': False}).status_code, 200)
        self.assertEqual(self.client.post('/api/enabled', headers=self.owner, json={'enabled': True}).status_code, 200)
        self.assertEqual(self.client.get('/api/state', headers=self.owner).json()['grant_until'], 0)
        self.assertEqual(self.client.post('/api/enabled', headers=self.owner, json={'enabled': False}).status_code, 403)

    def test_settings_grant_cannot_switch_block_off(self):
        self.assertEqual(self.grant(self.p1, 'settings').status_code, 200)
        r = self.client.put('/api/settings', headers=self.owner, json={**BASE_SETTINGS, 'enabled': False})
        self.assertEqual(r.status_code, 403)

    def test_settings_grant_used_up_by_one_save(self):
        self.grant(self.p1, 'settings')
        self.assertEqual(self.client.put('/api/settings', headers=self.owner, json={**BASE_SETTINGS, 'popupMessage': 'a'}).status_code, 200)
        self.assertEqual(self.client.put('/api/settings', headers=self.owner, json={**BASE_SETTINGS, 'popupMessage': 'b'}).status_code, 403)

    def test_end_grant_stops_everything(self):
        self.grant(self.p1, '1h')
        self.grant(self.p1, 'settings')
        r = self.grant(self.p1, 'end').json()
        self.assertEqual((r['grant_until'], r['settings_until']), (0, 0))

    def test_day_grant_extends_running_grant(self):
        self.grant(self.p1, '1h')
        first = self.client.get('/api/p/accounts', headers=self.p1).json()['accounts'][0]['grant_until']
        r = self.grant(self.p1, 'day').json()
        self.assertGreater(r['grant_until'], first + 23 * 3600)

    def test_unlinked_partner_cannot_grant_or_see(self):
        other = self.partner('bert')
        self.assertEqual(self.grant(other, '1h').status_code, 404)
        self.assertEqual(self.client.get('/api/p/accounts', headers=other).json()['accounts'], [])

    def test_dashboard_shows_owner_name_and_partners(self):
        self.assertEqual(self.client.put('/api/owner/name', json={'name': 'Max'}, headers=self.owner).status_code, 200)
        acc = self.client.get('/api/p/accounts', headers=self.p1).json()['accounts'][0]
        self.assertEqual(acc['owner_name'], 'Max')
        self.assertEqual(acc['partners'], ['anna'])
        self.assertEqual(self.client.get('/api/state', headers=self.owner).json()['owner_name'], 'Max')

    def test_owner_name_needs_no_grant_and_no_save(self):
        self.assertEqual(self.client.put('/api/owner/name', json={'name': 'Neu'}, headers=self.owner).status_code, 200)

    def test_removing_site_needs_time_grant(self):
        r = self.client.put('/api/settings', headers=self.owner, json={**BASE_SETTINGS, 'sites': []})
        self.assertEqual(r.status_code, 403)
        self.grant(self.p1, 'settings')
        self.assertEqual(self.client.put('/api/settings', headers=self.owner, json={**BASE_SETTINGS, 'sites': []}).status_code, 403)
        self.grant(self.p1, '30m')
        self.assertEqual(self.client.put('/api/settings', headers=self.owner, json={**BASE_SETTINGS, 'sites': []}).status_code, 200)

    def test_adding_free_window_needs_time_grant_removing_does_not(self):
        window = {'day': 0, 'from': '00:01', 'to': '23:59'}
        self.assertEqual(self.client.put('/api/settings', headers=self.owner,
                                         json={**BASE_SETTINGS, 'free_windows': [window]}).status_code, 403)
        self.grant(self.p1, 'settings')
        self.assertEqual(self.client.put('/api/settings', headers=self.owner,
                                         json={**BASE_SETTINGS, 'free_windows': [window]}).status_code, 403)
        self.grant(self.p1, '30m')
        self.assertEqual(self.client.put('/api/settings', headers=self.owner,
                                         json={**BASE_SETTINGS, 'free_windows': [window]}).status_code, 200)
        self.grant(self.p1, 'settings')
        self.assertEqual(self.client.put('/api/settings', headers=self.owner,
                                         json={**BASE_SETTINGS, 'free_windows': []}).status_code, 200)

    def test_tightening_settings_with_settings_grant_ok(self):
        self.grant(self.p1, 'settings')
        self.assertEqual(self.client.put('/api/settings', headers=self.owner,
                                         json={**BASE_SETTINGS, 'sites': ['youtube.com', 'x.com'], 'popupMessage': 'hi'}).status_code, 200)

    def test_pairing_by_username_and_accept_with_code(self):
        bert = self.partner('bert')
        code = self.pair(self.p1, 'bert').json()['code']
        self.assertEqual(self.client.post('/api/p/pairings/accept', json={'code': code}, headers=self.p1).status_code, 400)
        self.assertEqual(self.client.post('/api/p/pairings/accept', json={'code': code}, headers=bert).status_code, 200)
        self.assertEqual(self.grant(bert, '30m').status_code, 200)
        self.assertEqual(self.client.post('/api/p/pairings/accept', json={'code': code}, headers=bert).status_code, 400)

    def test_pairing_errors(self):
        self.assertEqual(self.pair(self.p1, 'niemand').status_code, 404)
        self.assertEqual(self.pair(self.p1, 'anna').status_code, 422)
        self.partner('bert')
        self.assertEqual(self.pair(self.p1, 'bert').status_code, 200)
        self.assertEqual(self.pair(self.p1, 'bert').status_code, 200)  # new code, still allowed until accepted
        carl = self.partner('carl')
        self.assertEqual(self.pair(carl, 'bert').status_code, 404)  # carl is not partner of this owner

    def test_pairing_code_needs_inviter_still_partner(self):
        bert = self.partner('bert')
        code = self.pair(self.p1, 'bert').json()['code']
        self.assertEqual(self.client.post(f'/api/p/accounts/{self.owner_id}/leave', headers=self.p1).status_code, 200)
        self.assertEqual(self.client.post('/api/p/pairings/accept', json={'code': code}, headers=bert).status_code, 403)

    def test_partner_leave_is_free(self):
        self.assertEqual(self.client.post(f'/api/p/accounts/{self.owner_id}/leave', headers=self.p1).status_code, 200)
        self.assertEqual(self.client.get('/api/state', headers=self.owner).json()['partners'], 0)
        self.assertEqual(self.client.get('/api/p/accounts', headers=self.p1).json()['accounts'], [])

    def test_owner_remove_partner_needs_grant(self):
        pid = self.client.get('/api/partners', headers=self.owner).json()['partners'][0]['id']
        self.assertEqual(self.client.post('/api/partners/remove', headers=self.owner, json={'partner_id': pid}).status_code, 403)
        self.grant(self.p1, '1h')
        self.assertEqual(self.client.post('/api/partners/remove', headers=self.owner, json={'partner_id': pid}).status_code, 200)
        self.assertEqual(self.client.get('/api/state', headers=self.owner).json()['partners'], 0)

    def test_remove_rejects_bad_id(self):
        self.grant(self.p1, '1h')
        self.assertEqual(self.client.post('/api/partners/remove', headers=self.owner, json={'partner_id': 'nope'}).status_code, 422)

    def test_accounts_are_isolated(self):
        _, other = self.new_owner(self.partner('carl'))
        self.client.put('/api/settings', headers=other, json={**BASE_SETTINGS, 'sites': ['other.com']})
        self.assertEqual(self.client.get('/api/state', headers=self.owner).json()['settings']['sites'], ['youtube.com'])

    def test_invalid_free_window_rejected(self):
        r = self.client.put('/api/settings', headers=self.owner,
                            json={**BASE_SETTINGS, 'free_windows': [{'day': 9, 'from': '10:00', 'to': '11:00'}]})
        self.assertEqual(r.status_code, 422)

    def test_grant_sets_time_for_feedback(self):
        self.grant(self.p1, '30m')
        self.assertGreater(self.client.get('/api/state', headers=self.owner).json()['grant_until'], time.time())


if __name__ == '__main__':
    unittest.main()
