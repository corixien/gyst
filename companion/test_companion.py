import datetime
import unittest

from gyst_companion import WINDOW_SECONDS, in_free_window, match_partner_code, partner_code, valid_free_windows

SECRET = '00' * 32
MONDAY = datetime.date(2026, 11, 23)  # weekday() == 0


def at(day_offset, hour, minute=0):
    day = MONDAY + datetime.timedelta(days=day_offset)
    return datetime.datetime(day.year, day.month, day.day, hour, minute)


class PartnerCodeTest(unittest.TestCase):
    def test_code_is_eight_digits(self):
        self.assertRegex(partner_code(SECRET, '1h', 1000), r'^\d{8}$')

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
        self.assertIsNone(match_partner_code([SECRET], partner_code('ff' * 32, '1h', 1000), now))


class ValidWindowsTest(unittest.TestCase):
    def test_accepts_weekday_windows(self):
        self.assertTrue(valid_free_windows([{'day': 0, 'from': '20:00', 'to': '22:30'}]))
        self.assertTrue(valid_free_windows([]))

    def test_rejects_bad_input(self):
        self.assertFalse(valid_free_windows([{'day': 0, 'from': '24:00', 'to': '22:00'}]))
        self.assertFalse(valid_free_windows([{'day': 0, 'from': '9:00', 'to': '22:00'}]))
        self.assertFalse(valid_free_windows([{'day': 0, 'from': '20:00', 'to': '20:00'}]))
        self.assertFalse(valid_free_windows([{'day': 7, 'from': '20:00', 'to': '21:00'}]))
        self.assertFalse(valid_free_windows([{'from': '20:00', 'to': '21:00'}]))
        self.assertFalse(valid_free_windows('20:00'))


class FreeWindowTest(unittest.TestCase):
    def test_only_on_its_weekday(self):
        windows = [{'day': 0, 'from': '07:00', 'to': '09:00'}]
        self.assertTrue(in_free_window(windows, at(0, 7)))
        self.assertFalse(in_free_window(windows, at(0, 9)))
        self.assertFalse(in_free_window(windows, at(1, 7)))

    def test_each_weekday_separately(self):
        windows = [{'day': 5, 'from': '10:00', 'to': '12:00'}]
        self.assertTrue(in_free_window(windows, at(5, 11)))
        self.assertFalse(in_free_window(windows, at(6, 11)))

    def test_window_wraps_midnight_into_next_day(self):
        windows = [{'day': 4, 'from': '22:00', 'to': '02:00'}]
        self.assertTrue(in_free_window(windows, at(4, 23)))
        self.assertTrue(in_free_window(windows, at(5, 1)))
        self.assertFalse(in_free_window(windows, at(5, 3)))
        self.assertFalse(in_free_window(windows, at(4, 12)))

    def test_wrap_from_sunday_to_monday(self):
        windows = [{'day': 6, 'from': '23:00', 'to': '01:00'}]
        self.assertTrue(in_free_window(windows, at(0, 0, 30)))

    def test_no_windows(self):
        self.assertFalse(in_free_window([], at(0, 12)))


if __name__ == '__main__':
    unittest.main()
