import unittest

from gyst_companion import WINDOW_SECONDS, in_free_window, match_partner_code, partner_code

SECRET = '00' * 32


class PartnerCodeTest(unittest.TestCase):
    def test_code_is_eight_digits(self):
        code = partner_code(SECRET, '1h', 1000)
        self.assertRegex(code, r'^\d{8}$')

    def test_current_and_previous_window_accepted(self):
        now = 1000 * WINDOW_SECONDS + 5
        self.assertEqual(match_partner_code([SECRET], partner_code(SECRET, '30m', 1000), now)[0], '30m')
        self.assertEqual(match_partner_code([SECRET], partner_code(SECRET, '30m', 999), now)[0], '30m')

    def test_older_window_rejected(self):
        now = 1000 * WINDOW_SECONDS + 5
        self.assertIsNone(match_partner_code([SECRET], partner_code(SECRET, '30m', 998), now))

    def test_tier_sets_minutes(self):
        now = 1000 * WINDOW_SECONDS
        self.assertEqual(match_partner_code([SECRET], partner_code(SECRET, 'day', 1000), now)[1], 1440)

    def test_wrong_secret_rejected(self):
        now = 1000 * WINDOW_SECONDS
        other = 'ff' * 32
        self.assertIsNone(match_partner_code([SECRET], partner_code(other, '1h', 1000), now))


class FreeWindowTest(unittest.TestCase):
    def test_plain_window(self):
        windows = [{'from': '07:00', 'to': '09:00'}]
        self.assertTrue(in_free_window(windows, 7 * 60))
        self.assertFalse(in_free_window(windows, 9 * 60))

    def test_window_wraps_midnight(self):
        windows = [{'from': '22:00', 'to': '02:00'}]
        self.assertTrue(in_free_window(windows, 23 * 60))
        self.assertTrue(in_free_window(windows, 60))
        self.assertFalse(in_free_window(windows, 12 * 60))

    def test_no_windows(self):
        self.assertFalse(in_free_window([], 0))


if __name__ == '__main__':
    unittest.main()
