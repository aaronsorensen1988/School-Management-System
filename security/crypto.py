"""Encrypt/decrypt sensitive field values. UMA-003 / T1-012.

AES-256-GCM. Went with GCM because it authenticates too, so a tampered
value blows up instead of quietly coming back wrong.

Stored as: enc:<version>:<key id>:<base64 nonce + ciphertext>

New nonce every write, so the same input never encrypts the same way
twice. That's why you can't search an encrypted column. Use blind_index.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from security.keys import KeyRing, active_keyring

PREFIX = "enc"
SCHEME_VERSION = "1"
NONCE_BYTES = 12  # what GCM wants


class CryptoError(RuntimeError):
    pass


class DecryptionError(CryptoError):
    pass


def _aad(context: str | None) -> bytes | None:
    # ties the value to its column so you can't move it somewhere else.
    # GCM checks it without storing it, so it's free.
    return None if context is None else context.encode("utf-8")


def is_encrypted(value: object) -> bool:
    """Did this come out of encrypt()? Stops us double-wrapping."""
    return isinstance(value, str) and value.startswith(f"{PREFIX}:{SCHEME_VERSION}:")


def encrypt(
    plaintext: str,
    context: str | None = None,
    keyring: KeyRing | None = None,
) -> str:
    """Encrypt with the active key. context is "table.column", pass the
    same one to decrypt or it won't open."""
    if not isinstance(plaintext, str):
        raise CryptoError(f"encrypt needs a str, got {type(plaintext).__name__}")

    ring = keyring or active_keyring()
    key_id, key = ring.active()
    nonce = secrets.token_bytes(NONCE_BYTES)
    sealed = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), _aad(context))
    # nonce goes on the front. it isn't secret, it just has to be unique
    payload = base64.b64encode(nonce + sealed).decode("ascii")
    return f"{PREFIX}:{SCHEME_VERSION}:{key_id}:{payload}"


def decrypt(
    stored: str,
    context: str | None = None,
    keyring: KeyRing | None = None,
) -> str:
    """Other direction. Raises on anything it doesn't like.

    Don't catch this and return a blank. It means a key problem or
    tampering and both need someone to look.
    """
    if not isinstance(stored, str):
        raise DecryptionError(f"expected a str, got {type(stored).__name__}")

    parts = stored.split(":", 3)
    if len(parts) != 4 or parts[0] != PREFIX:
        raise DecryptionError(
            "Not encrypted. If this column predates encryption it's still "
            "plaintext and needs a backfill, see docs/ENCRYPTION.md"
        )

    _, version, key_id, payload = parts
    if version != SCHEME_VERSION:
        raise DecryptionError(f"scheme version {version!r}, we only do {SCHEME_VERSION!r}")

    key = ring_get(keyring, key_id)

    try:
        blob = base64.b64decode(payload, validate=True)
    except (ValueError, TypeError) as exc:
        raise DecryptionError("payload isn't valid base64") from exc

    if len(blob) <= NONCE_BYTES:
        raise DecryptionError("payload is truncated")

    nonce, sealed = blob[:NONCE_BYTES], blob[NONCE_BYTES:]
    try:
        return AESGCM(key).decrypt(nonce, sealed, _aad(context)).decode("utf-8")
    except InvalidTag as exc:
        # wrong key, wrong context, or someone messed with the row
        raise DecryptionError(
            "Auth check failed. Wrong key, wrong context, or the value was changed."
        ) from exc
    except UnicodeDecodeError as exc:
        raise DecryptionError("decrypted bytes aren't valid UTF-8") from exc


def ring_get(keyring: KeyRing | None, key_id: str) -> bytes:
    ring = keyring or active_keyring()
    return ring.get(key_id)


def blind_index(
    plaintext: str,
    context: str,
    keyring: KeyRing | None = None,
    normalize: bool = True,
) -> str:
    """Stable token so an encrypted field can still be looked up.

    HMAC instead of a plain hash, otherwise anyone with the db could hash a
    list of likely emails and match them up.

    Catch: the token is stable, so you can tell which rows share a value
    even without reading it. Fine for email. Don't use it where two
    students matching is itself the sensitive bit.
    """
    if not context:
        raise CryptoError("blind_index needs a context or tokens collide across columns")
    ring = keyring or active_keyring()
    material = plaintext.strip().casefold() if normalize else plaintext
    digest = hmac.new(
        ring.index_key,
        context.encode("utf-8") + b"\x00" + material.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("ascii")
