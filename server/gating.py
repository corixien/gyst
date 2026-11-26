"""Pure rules: which settings changes need a partner grant, and what a grant token means."""
import base64
import struct

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

GRANT_DOMAIN = b'gyst-grant-v2'
TIERS = [('30m', 30 * 60), ('1h', 60 * 60), ('day', 24 * 60 * 60), ('settings', 15 * 60)]
MAX_STAMP_AGE = 300  # seconds a signed request may be old when it arrives


def gated_changes(old: dict, new: dict) -> list[str]:
    """Changes that loosen the block. Adding sites and turning the block on are always free."""
    gated = []
    old_sites, new_sites = set(old.get('sites', [])), set(new.get('sites', []))
    if old_sites - new_sites:
        gated.append('remove_site')
    if old.get('enabled') and not new.get('enabled'):
        gated.append('disable')
    if old.get('unlock') != new.get('unlock'):
        gated.append('unlock')
    for key in ('popupMessage', 'blockMessage', 'language'):
        if old.get(key) != new.get(key):
            gated.append(key)
    old_windows = {(w['day'], w['from'], w['to']) for w in old.get('free_windows', [])}
    new_windows = {(w['day'], w['from'], w['to']) for w in new.get('free_windows', [])}
    if new_windows - old_windows:
        gated.append('add_free_window')
    return gated


def grant_message(account_id: str, tier_id: int, stamp: int) -> bytes:
    return GRANT_DOMAIN + base64.b16decode(account_id.replace('-', '').upper()) + struct.pack('>BI', tier_id, stamp)


def verify_grant(pubkey_hex: str, account_id: str, tier_id: int, stamp: int, signature_b64: str, now: int) -> bool:
    if not 0 <= tier_id < len(TIERS) or abs(now - stamp) > MAX_STAMP_AGE:
        return False
    try:
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pubkey_hex))
        key.verify(base64.b64decode(signature_b64), grant_message(account_id, tier_id, stamp))
    except (ValueError, InvalidSignature, TypeError):
        return False
    return True
