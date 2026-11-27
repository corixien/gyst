"""Pure rules: what a partner grant does to an owner's free time, and what a partner login may contain."""
import hashlib
import hmac
import os
import re

# Grant tiers: 30 min, 1 h, a whole day (extend the time grant), settings (15 min, one save), end (stop everything).
TIERS = {'30m': 30 * 60, '1h': 60 * 60, 'day': 24 * 60 * 60, 'settings': 15 * 60, 'end': 0}
USERNAME = re.compile(r'^[a-z0-9_.-]{3,20}$')


def apply_grant(tier: str, now: int, grant_until: int, settings_until: int) -> tuple[int, int]:
    """Returns the new (grant_until, settings_until) after a partner grant."""
    if tier == 'end':
        return 0, 0
    if tier == 'settings':
        return grant_until, now + TIERS['settings']
    return max(grant_until, now) + TIERS[tier], settings_until


def valid_username(name: str) -> bool:
    return USERNAME.fullmatch(name) is not None


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f'scrypt${salt.hex()}${digest.hex()}'


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split('$')
    except ValueError:
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2 ** 14, r=8, p=1, dklen=32)
    return hmac.compare_digest(digest.hex(), digest_hex)
