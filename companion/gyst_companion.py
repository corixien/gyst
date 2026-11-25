#!/usr/bin/env python3
"""GYST companion: full-screen lock with a system-wide keyboard/mouse grab, daily free windows, partner codes."""

import datetime
import fcntl
import glob
import hashlib
import hmac
import json
import math
import os
import queue
import re
import select
import socket
import struct
import sys
import threading
import time
import tkinter as tk
from pathlib import Path

CONFIG_PATH = Path.home() / '.config/gyst-companion/config.json'
STATE_PATH = Path.home() / '.local/state/gyst-companion/state.json'
SOCKET_PATH = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'gyst-companion.sock'

DEFAULT_CONFIG = {
    'lock_seconds': 10,
    'max_lock_seconds': 120,
    'message': 'Get your shit together. Diese Seite ist gesperrt.',
    'free_windows': [],  # [{"day": 0, "from": "20:00", "to": "22:00"}], day 0 = Monday
    'partner_secrets': [],  # hex strings, one per partner
}

TIERS = {'30m': 30, '1h': 60, 'day': 24 * 60}  # tier -> minutes granted
WINDOW_SECONDS = 300  # partner codes change every 5 min; previous window is still accepted
TICK_MS = 100
RING_SIZE = 220
RING_WIDTH = 14

EV_KEY = 0x01
EVENT = struct.Struct('llHHi')  # struct input_event, 64-bit Linux
EVIOCGRAB = 0x40044590  # _IOW('E', 0x90, int)
KEY_BACKSPACE = 14
KEY_ENTER = 28
KEY_KPENTER = 96
KEY_A = 30
BTN_LEFT = 0x110
DIGIT_KEYS = {
    2: '1', 3: '2', 4: '3', 5: '4', 6: '5', 7: '6', 8: '7', 9: '8', 10: '9', 11: '0',
    79: '1', 80: '2', 81: '3', 75: '4', 76: '5', 77: '6', 71: '7', 72: '8', 73: '9', 82: '0',
}


def load_config():
    try:
        return {**DEFAULT_CONFIG, **json.loads(CONFIG_PATH.read_text())}
    except FileNotFoundError:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + '\n')
        return dict(DEFAULT_CONFIG)


def load_state():
    try:
        return json.loads(STATE_PATH.read_text())
    except (FileNotFoundError, ValueError):
        return {}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state))


def partner_code(secret_hex, tier, window):
    mac = hmac.new(bytes.fromhex(secret_hex), f'{tier}:{window}'.encode(), hashlib.sha256).digest()
    return f'{int.from_bytes(mac[:4], "big") % 10**8:08d}'


def match_partner_code(secrets, typed, now):
    """Return (tier, minutes, expires) for a valid code, else None. Accepts the current and previous window."""
    window = int(now // WINDOW_SECONDS)
    for tier, minutes in TIERS.items():
        for secret in secrets:
            for w in (window, window - 1):
                if hmac.compare_digest(partner_code(secret, tier, w), typed):
                    return tier, minutes, (w + 2) * WINDOW_SECONDS
    return None


HHMM = re.compile(r'([01]\d|2[0-3]):[0-5]\d')


def valid_free_windows(windows):
    """Each window: {"day": 0-6 (0 = Monday), "from": "HH:MM", "to": "HH:MM"}. "to" may be earlier than "from" (wraps midnight)."""
    return isinstance(windows, list) and all(
        isinstance(w, dict)
        and type(w.get('day')) is int and 0 <= w['day'] <= 6
        and isinstance(w.get('from'), str) and HHMM.fullmatch(w['from'])
        and isinstance(w.get('to'), str) and HHMM.fullmatch(w['to'])
        and w['from'] != w['to']
        for w in windows
    )


def _minute_of_day(hhmm):
    hours, minutes = hhmm.split(':')
    return int(hours) * 60 + int(minutes)


def in_free_window(windows, now):
    """now: datetime. A window that wraps midnight also covers the early hours of the following weekday."""
    minute = now.hour * 60 + now.minute
    for window in windows:
        start, end = _minute_of_day(window['from']), _minute_of_day(window['to'])
        if start < end and window['day'] == now.weekday() and start <= minute < end:
            return True
        if start > end:
            if window['day'] == now.weekday() and minute >= start:
                return True
            if window['day'] == (now.weekday() - 1) % 7 and minute < end:
                return True
    return False


def _has_bit(bits, code):
    return bool(bits[code // 8] & (1 << (code % 8)))


def _is_input_device(fd):
    bits = bytearray(96)
    fcntl.ioctl(fd, (2 << 30) | (len(bits) << 16) | (ord('E') << 8) | (0x20 + EV_KEY), bits)
    return _has_bit(bits, KEY_A) or _has_bit(bits, BTN_LEFT)


class InputGrab:
    """Exclusive grab of all keyboards and pointers. The grab ends when the device fds are closed."""

    def __init__(self, on_key):
        self.on_key = on_key
        self.fds = []
        self.halt = threading.Event()

    def start(self):
        for path in sorted(glob.glob('/dev/input/event*')):
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                continue
            try:
                if _is_input_device(fd):
                    fcntl.ioctl(fd, EVIOCGRAB, 1)
                    self.fds.append(fd)
                else:
                    os.close(fd)
            except OSError:
                os.close(fd)
        if not self.fds:
            raise OSError('no input device could be grabbed (user in group input?)')
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self.halt.set()

    def _run(self):
        try:
            while not self.halt.is_set():
                ready, _, _ = select.select(self.fds, [], [], 0.05)
                for fd in ready:
                    try:
                        data = os.read(fd, EVENT.size * 64)
                    except BlockingIOError:
                        continue
                    for offset in range(0, len(data) - EVENT.size + 1, EVENT.size):
                        _, _, etype, code, value = EVENT.unpack_from(data, offset)
                        if etype == EV_KEY and value == 1:
                            self.on_key(code)
        finally:
            for fd in self.fds:
                os.close(fd)


class Lock:
    def __init__(self, host, cfg, grab, window, labels):
        self.started = time.monotonic()
        self.host = host
        self.lock_seconds = cfg['lock_seconds']
        self.max_seconds = cfg['max_lock_seconds']
        self.grab = grab
        self.window = window
        self.labels = labels
        self.typed = ''
        self.status = ''


class Companion:
    def __init__(self, root):
        self.root = root
        self.requests = queue.Queue()  # (request dict, reply queue)
        self.keys = queue.Queue()  # key codes from the input thread
        self.lock = None
        self.state = load_state()
        self.cfg = load_config()

    def run(self):
        self.root.after(TICK_MS, self.tick)

    def tick(self):
        while True:
            try:
                req, reply = self.requests.get_nowait()
            except queue.Empty:
                break
            self.handle(req, reply)
        if self.lock:
            self.drain_keys()
            if self.lock:
                self.update_lock()
        self.root.after(TICK_MS, self.tick)

    def free_now(self):
        if self.state.get('grant_until', 0) > time.time():
            return True
        return in_free_window(self.cfg['free_windows'], datetime.datetime.now())

    def handle(self, req, reply):
        self.cfg = load_config()
        try:
            answer = self.dispatch(req)
        except Exception as err:  # a bad config entry must not kill the tk loop
            print(f'gyst: request failed: {err!r}', file=sys.stderr)
            answer = {'free': False, 'error': 'request failed'}
        reply.put(answer)

    def start_lock(self, host):
        grab = InputGrab(self.keys.put)
        try:
            grab.start()
        except OSError as err:
            print(f'gyst: lock not started: {err}', file=sys.stderr)
            return
        window = tk.Toplevel(self.root)
        window.configure(bg='#0b0d12')
        window.attributes('-fullscreen', True)
        window.attributes('-topmost', True)
        window.protocol('WM_DELETE_WINDOW', lambda: None)
        # Hourglass-style ring that empties over lock_seconds, message below it. Nothing else.
        canvas = tk.Canvas(window, width=RING_SIZE, height=RING_SIZE, bg='#0b0d12', highlightthickness=0)
        margin = RING_WIDTH
        canvas.create_oval(margin, margin, RING_SIZE - margin, RING_SIZE - margin, outline='#262c3a', width=RING_WIDTH)
        arc = canvas.create_arc(margin, margin, RING_SIZE - margin, RING_SIZE - margin, start=90, extent=359.9,
                                outline='#3b82f6', width=RING_WIDTH, style='arc')
        message = tk.Label(window, text=self.cfg['message'], fg='#f2f4f8', bg='#0b0d12',
                           font=('Sans', 34, 'bold'), wraplength=1200)
        # Shown only while digits are typed, so a partner code can be checked.
        code = tk.Label(window, text='', fg='#8b93a7', bg='#0b0d12', font=('Monospace', 22))
        canvas.pack(pady=(0, 40))
        message.pack()
        code.pack(pady=24)
        labels = {'arc': canvas, 'arc_id': arc, 'message': message, 'code': code}
        self.lock = Lock(host, self.cfg, grab, window, labels)

    def update_lock(self):
        lock = self.lock
        elapsed = time.monotonic() - lock.started
        left = max(0.0, lock.lock_seconds - elapsed)
        if elapsed >= lock.max_seconds or (left == 0 and not lock.typed):
            self.end_lock()
            return
        lock.labels['arc'].itemconfigure(lock.labels['arc_id'], extent=max(0.1, 359.9 * left / lock.lock_seconds))
        code_text = f'{lock.typed}  {lock.status}' if lock.typed or lock.status else ''
        lock.labels['code'].config(text=code_text)

    def drain_keys(self):
        lock = self.lock
        while True:
            try:
                code = self.keys.get_nowait()
            except queue.Empty:
                return
            if code in DIGIT_KEYS:
                lock.typed = (lock.typed + DIGIT_KEYS[code])[:8]
            elif code == KEY_BACKSPACE:
                lock.typed = lock.typed[:-1]
            elif code in (KEY_ENTER, KEY_KPENTER) and lock.typed:
                if self.try_code(lock.typed):
                    self.end_lock()
                    return
                lock.typed = ''
                lock.status = 'Code ungültig'

    def consume_code(self, typed):
        """Mark a valid, unused code as used. Returns (tier, minutes) or None."""
        now = time.time()
        used = {code: until for code, until in self.state.get('used', {}).items() if until > now}
        match = None if typed in used else match_partner_code(self.cfg['partner_secrets'], typed, now)
        if match:
            tier, minutes, expires = match
            used[typed] = expires
            self.state = {**self.state, 'used': used}
            save_state(self.state)
            return tier, minutes
        return None

    def try_code(self, typed):
        match = self.consume_code(typed)
        if not match:
            return False
        tier, minutes = match
        self.state = {**self.state, 'grant_until': time.time() + minutes * 60}
        save_state(self.state)
        print(f'gyst: partner grant {tier}', file=sys.stderr)
        return True

    def set_free_windows(self, windows):
        if not valid_free_windows(windows):
            return {'ok': False, 'error': 'invalid windows'}
        CONFIG_PATH.write_text(json.dumps({**self.cfg, 'free_windows': windows}, indent=2) + '\n')
        return {'ok': True}

    def dispatch(self, req):
        kind = req.get('type')
        if kind == 'getConfig':
            return {'config': {'free_windows': self.cfg['free_windows']}}
        if kind == 'setFreeWindows':
            return self.set_free_windows(req.get('windows'))
        if kind == 'verifyCode':
            return {'ok': self.consume_code(str(req.get('code', ''))) is not None}
        free = self.free_now()
        if kind == 'blocked' and not free and self.lock is None:
            self.start_lock(str(req.get('host', '')))
        return {'free': free}

    def end_lock(self):
        self.lock.grab.stop()
        self.lock.window.destroy()
        self.lock = None
        while not self.keys.empty():
            self.keys.get_nowait()


def serve_socket(requests):
    SOCKET_PATH.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(SOCKET_PATH))
    server.listen(8)

    def loop():
        while True:
            conn, _ = server.accept()
            with conn:
                try:
                    req = json.loads(conn.makefile('rb').readline())
                except ValueError:
                    req = None
                if not isinstance(req, dict):
                    conn.sendall(b'{"free": false}\n')
                    continue
                reply = queue.Queue()
                requests.put((req, reply))
                try:
                    answer = reply.get(timeout=5)
                except queue.Empty:
                    answer = {'free': False}
                conn.sendall(json.dumps(answer).encode() + b'\n')

    threading.Thread(target=loop, daemon=True).start()


def main():
    root = tk.Tk()
    root.withdraw()
    companion = Companion(root)
    serve_socket(companion.requests)
    companion.run()
    root.mainloop()


if __name__ == '__main__':
    main()
