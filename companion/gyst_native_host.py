#!/usr/bin/env python3
"""Native messaging bridge: browser (length-prefixed JSON on stdin/stdout) to the companion socket."""

import json
import os
import socket
import struct
import sys
from pathlib import Path

SOCKET_PATH = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'gyst-companion.sock'


def read_message():
    head = sys.stdin.buffer.read(4)
    if len(head) < 4:
        return None
    (length,) = struct.unpack('<I', head)
    return json.loads(sys.stdin.buffer.read(length))


def write_message(obj):
    data = json.dumps(obj).encode()
    sys.stdout.buffer.write(struct.pack('<I', len(data)) + data)
    sys.stdout.buffer.flush()


def forward(msg):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.connect(str(SOCKET_PATH))
            sock.sendall(json.dumps(msg).encode() + b'\n')
            return json.loads(sock.makefile('rb').readline() or b'{}')
    except OSError:
        return {'free': False, 'error': 'companion not running'}


if __name__ == '__main__':
    message = read_message()
    if message is not None:
        write_message(forward(message))
