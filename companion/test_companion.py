import datetime
import http.server
import json
import threading
import time
import unittest

import gyst_companion as gc

MONDAY = datetime.date(2026, 11, 23)  # weekday() == 0


def at(day_offset, hour, minute=0):
    day = MONDAY + datetime.timedelta(days=day_offset)
    return datetime.datetime(day.year, day.month, day.day, hour, minute)


class FreeWindowTest(unittest.TestCase):
    def test_only_on_its_weekday(self):
        windows = [{'day': 1, 'from': '20:00', 'to': '22:00'}]
        self.assertTrue(gc.in_free_window(windows, at(1, 21)))
        self.assertFalse(gc.in_free_window(windows, at(0, 21)))

    def test_end_is_exclusive(self):
        windows = [{'day': 0, 'from': '20:00', 'to': '22:00'}]
        self.assertFalse(gc.in_free_window(windows, at(0, 22)))

    def test_wraps_midnight_into_next_day(self):
        windows = [{'day': 4, 'from': '23:00', 'to': '01:00'}]
        self.assertTrue(gc.in_free_window(windows, at(4, 23, 30)))
        self.assertTrue(gc.in_free_window(windows, at(5, 0, 30)))
        self.assertFalse(gc.in_free_window(windows, at(5, 1, 30)))

    def test_sunday_wrap_goes_to_monday(self):
        windows = [{'day': 6, 'from': '23:00', 'to': '01:00'}]
        self.assertTrue(gc.in_free_window(windows, at(7, 0, 30)))

    def test_empty_is_never_free(self):
        self.assertFalse(gc.in_free_window([], at(0, 12)))


class FreeNowTest(unittest.TestCase):
    def make(self, remote):
        companion = gc.Companion.__new__(gc.Companion)
        companion.remote = remote
        return companion

    def test_grant_makes_free(self):
        self.assertTrue(self.make({'grant_until': time.time() + 60, 'free_windows': []}).free_now())

    def test_expired_grant_is_not_free(self):
        self.assertFalse(self.make({'grant_until': time.time() - 1, 'free_windows': []}).free_now())

    def test_no_state_is_not_free(self):
        self.assertFalse(self.make({}).free_now())


class SyncTest(unittest.TestCase):
    def test_state_is_fetched_with_token(self):
        seen = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                seen['auth'] = self.headers.get('Authorization')
                body = json.dumps({'grant_until': 5, 'free_windows': [], 'settings_until': 0}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            state = gc.fetch_state(f'http://127.0.0.1:{server.server_port}', 'SECRET')
            self.assertEqual(state['grant_until'], 5)
            self.assertEqual(seen['auth'], 'Bearer SECRET')
        finally:
            server.shutdown()


if __name__ == '__main__':
    unittest.main()
