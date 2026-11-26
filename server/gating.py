"""Pure rules: what a partner-signed request means. Every owner-side credential is derived from a partner key."""
import base64
import struct

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

GRANT_DOMAIN = b'gyst-grant-v2'
LEAVE_DOMAIN = b'gyst-leave-v1'
DEVICE_DOMAIN = b'gyst-device-v1'  # partner issues a device code for an account
INVITE_DOMAIN = b'gyst-invite-v1'  # partner issues an invite for another partner
SETUP_DOMAIN = b'gyst-setup-v1'  # partner creates a new account (becomes its first partner)
# Tier ids are part of the signed message. 'end' stops a running grant and the settings grant.
TIERS = [('30m', 30 * 60), ('1h', 60 * 60), ('day', 24 * 60 * 60), ('settings', 15 * 60), ('end', 0)]
MAX_STAMP_AGE = 300  # seconds a signed request may be old when it arrives


def _uuid_bytes(account_id: str) -> bytes:
    return base64.b16decode(account_id.replace('-', '').upper())


def grant_message(account_id: str, tier_id: int, stamp: int) -> bytes:
    return GRANT_DOMAIN + _uuid_bytes(account_id) + struct.pack('>BI', tier_id, stamp)


def account_message(domain: bytes, account_id: str, stamp: int) -> bytes:
    return domain + _uuid_bytes(account_id) + struct.pack('>I', stamp)


def setup_message(pubkey_hex: str, stamp: int) -> bytes:
    return SETUP_DOMAIN + bytes.fromhex(pubkey_hex) + struct.pack('>I', stamp)


def verify_signed(pubkey_hex: str, message: bytes, signature_b64: str, stamp: int, now: int) -> bool:
    if abs(now - stamp) > MAX_STAMP_AGE:
        return False
    try:
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pubkey_hex))
        key.verify(base64.b64decode(signature_b64), message)
    except (ValueError, InvalidSignature, TypeError):
        return False
    return True


def verify_grant(pubkey_hex: str, account_id: str, tier_id: int, stamp: int, signature_b64: str, now: int) -> bool:
    if not 0 <= tier_id < len(TIERS):
        return False
    return verify_signed(pubkey_hex, grant_message(account_id, tier_id, stamp), signature_b64, stamp, now)
