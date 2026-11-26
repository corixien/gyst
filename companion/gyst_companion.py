#!/usr/bin/env python3
"""GYST companion (Linux, Fedora): full-screen lock with a system-wide keyboard/mouse grab.

Free time comes from the GYST sync server (partner grants and free windows). The server is polled; the last
known state is kept on disk so a restart while offline does not unblock anything."""

import datetime
import fcntl
import glob
import json
import os
import queue
import select
import socket
import struct
import sys
import threading
import time
import tkinter as tk
import urllib.request
from pathlib import Path

CONFIG_PATH = Path.home() / '.config/gyst-companion/config.json'
STATE_PATH = Path.home() / '.local/state/gyst-companion/state.json'
SOCKET_PATH = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'gyst-companion.sock'

DEFAULT_CONFIG = {
    'server': 'https://gyst-sync-y5x4.onrender.com',  # empty = no sync, nothing is free
    'token': '',  # account token, from the add-on popup (Konto erstellen)
    'lock_seconds': 10,
    'max_lock_seconds': 120,
    'message': 'Get your shit together. Diese Seite ist gesperrt.',
}
SYNC_SECONDS = 10
TICK_MS = 16  # smooth ring animation; the loop only drains queues, so this is cheap
DISC_RATIO = 0.6  # ring diameter as share of screen height
LOCK_DROP = 0.04  # content moved down from screen centre, share of screen height
RING_RATIO = 0.06  # ring stroke width as share of ring diameter

# GYST colours (popup dark theme)
BG = '#0b0d12'
TRACK = '#262c3a'
ACCENT = '#3b82f6'
TEXT = '#f2f4f8'
ACCENT_SOFT = '#121d32'  # popup .mark background: accent at 14 % over BG


def draw_logo(canvas, size):
    # Same wordmark as the popup header (.mark): accent text on a rounded accent-tinted box, centred in the ring.
    cx, cy = size / 2, size / 2
    text = canvas.create_text(cx, cy, text='GYST', fill=ACCENT, font=('Sans', int(size * 0.07), 'bold'))
    x1, y1, x2, y2 = canvas.bbox(text)
    px, py = size * 0.02, size * 0.01
    x1, y1, x2, y2 = x1 - px, y1 - py, x2 + px, y2 + py
    r = (y2 - y1) * 0.25
    # Corner points repeated with smooth=True give rounded corners.
    box = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    canvas.create_polygon(box, fill=ACCENT_SOFT, outline='', smooth=True)
    canvas.tag_raise(text)

EV_KEY = 0x01
EVENT = struct.Struct('llHHi')  # struct input_event, 64-bit Linux
EVIOCGRAB = 0x40044590  # _IOW('E', 0x90, int)
KEY_A = 30
BTN_LEFT = 0x110


def load_config():
    try:
        return {**DEFAULT_CONFIG, **json.loads(CONFIG_PATH.read_text())}
    except FileNotFoundError:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + '\n')
        return dict(DEFAULT_CONFIG)


def load_remote_cache():
    try:
        return json.loads(STATE_PATH.read_text())
    except (FileNotFoundError, ValueError):
        return {}


def save_remote_cache(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state))


def fetch_state(server, token):
    request = urllib.request.Request(f"{server.rstrip('/')}/api/state", headers={'Authorization': f'Bearer {token}'})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def in_free_window(windows, now):
    """now: datetime. Windows are {"day": 0-6 (0 = Monday), "from": "HH:MM", "to": "HH:MM"}; a window that wraps
    midnight also covers the early hours of the following weekday."""
    minute = now.hour * 60 + now.minute

    def minutes(hhmm):
        hours, mins = hhmm.split(':')
        return int(hours) * 60 + int(mins)

    for window in windows:
        start, end = minutes(window['from']), minutes(window['to'])
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

    def __init__(self):
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
                        os.read(fd, EVENT.size * 64)  # swallowed: the lock blocks all input
                    except BlockingIOError:
                        continue
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


class Companion:
    def __init__(self, root):
        self.root = root
        self.requests = queue.Queue()  # (request dict, reply queue)
        self.lock = None
        self.cfg = load_config()
        self.remote = load_remote_cache()  # {grant_until, free_windows}, from the server

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
            self.update_lock()
        self.root.after(TICK_MS, self.tick)

    def free_now(self):
        if self.remote.get('grant_until', 0) > time.time():
            return True
        return in_free_window(self.remote.get('free_windows', []), datetime.datetime.now())

    def sync_once(self):
        if not self.cfg['server'] or not self.cfg['token']:
            return
        try:
            state = fetch_state(self.cfg['server'], self.cfg['token'])
        except (OSError, ValueError) as err:
            print(f'gyst: sync failed: {err!r}', file=sys.stderr)
            return
        self.remote = {'grant_until': state['grant_until'], 'free_windows': state['free_windows']}
        save_remote_cache(self.remote)

    def handle(self, req, reply):
        try:
            answer = self.dispatch(req)
        except Exception as err:  # a bad request must not kill the tk loop
            print(f'gyst: request failed: {err!r}', file=sys.stderr)
            answer = {'free': False, 'error': 'request failed'}
        reply.put(answer)

    def start_lock(self, host):
        grab = InputGrab()
        try:
            grab.start()
        except OSError as err:
            print(f'gyst: lock not started: {err}', file=sys.stderr)
            return
        window = tk.Toplevel(self.root)
        window.configure(bg=BG)
        window.attributes('-fullscreen', True)
        window.attributes('-topmost', True)
        window.protocol('WM_DELETE_WINDOW', lambda: None)
        # Ring that empties clockwise over lock_seconds (accent = time left), GYST logo in the centre, message below.
        # Everything sits in one frame, pushed slightly below the screen centre.
        size = int(self.root.winfo_screenheight() * DISC_RATIO)
        ring = int(size * RING_RATIO)
        stack = tk.Frame(window, bg=BG)
        stack.place(relx=0.5, rely=0.5, anchor='center', y=int(self.root.winfo_screenheight() * LOCK_DROP))
        canvas = tk.Canvas(stack, width=size, height=size, bg=BG, highlightthickness=0)
        canvas.create_oval(ring / 2, ring / 2, size - ring / 2, size - ring / 2, outline=TRACK, width=ring)
        arc = canvas.create_arc(ring / 2, ring / 2, size - ring / 2, size - ring / 2, start=90, extent=359.9,
                                outline=ACCENT, width=ring, style='arc')
        draw_logo(canvas, size)
        canvas.pack(pady=(0, 40))
        message = tk.Label(stack, text=self.cfg['message'], fg=TEXT, bg=BG,
                           font=('Sans', 34, 'bold'), wraplength=1200)
        message.pack()
        labels = {'arc': canvas, 'arc_id': arc}
        self.lock = Lock(host, self.cfg, grab, window, labels)

    def update_lock(self):
        lock = self.lock
        elapsed = time.monotonic() - lock.started
        left = max(0.0, lock.lock_seconds - elapsed)
        # A grant that arrives during the lock releases it at once.
        if elapsed >= lock.max_seconds or left == 0 or self.free_now():
            self.end_lock()
            return
        lock.labels['arc'].itemconfigure(lock.labels['arc_id'], extent=max(0.1, 359.9 * left / lock.lock_seconds))

    def dispatch(self, req):
        kind = req.get('type')
        free = self.free_now()
        if kind == 'blocked' and not free and self.lock is None:
            self.start_lock(str(req.get('host', '')))
        return {'free': free}

    def end_lock(self):
        self.lock.grab.stop()
        self.lock.window.destroy()
        self.lock = None


def sync_loop(companion):
    # Own thread: a slow or offline server must never stall the lock screen.
    while True:
        companion.sync_once()
        time.sleep(SYNC_SECONDS)


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
    threading.Thread(target=sync_loop, args=(companion,), daemon=True).start()
    companion.run()
    root.mainloop()


if __name__ == '__main__':
    main()
