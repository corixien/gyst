"""Pure rules: which settings changes need a partner grant, and what a grant token means."""
import base64
import struct

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

GRANT_DOMAIN = b'gyst-grant-v2'
# Tier ids are part of the signed message. 'end' stops a running grant and the settings grant.
TIERS = [('30m', 30 * 60), ('1h', 60 * 60), ('day', 24 * 60 * 60), ('settings', 15 * 60), ('end', 0)]
MAX_STAMP_AGE = 300  # seconds a signed request may be old when it arrives


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
