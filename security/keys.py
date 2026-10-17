"""Key loading + rotation. UMA-003 / T1-012.

Keys come from the env, never from the repo:

    SMS_ENCRYPTION_KEYS         "id:base64key" pairs, comma separated
    SMS_ENCRYPTION_ACTIVE_KEY   which id new writes use

Loading more than one is what lets you rotate. Every value records which
key wrote it so the old one can hang around to read old rows.

No key means the app won't start. On purpose, beats quietly saving student
records in the clear.
"""

from __future__ import annotations

import base64
import binascii
import os
import secrets
from dataclasses import dataclass

KEY_BYTES = 32  # AES-256
ENV_KEYS = "SMS_ENCRYPTION_KEYS"
ENV_ACTIVE = "SMS_ENCRYPTION_ACTIVE_KEY"
ENV_INDEX_KEY = "SMS_BLIND_INDEX_KEY"


class KeyRingError(RuntimeError):
    pass


def generate_key() -> str:
    """New 256 bit key, base64. Generate your own, don't reuse someone else's.

        python -c "from security.keys import generate_key; print(generate_key())"
    """
    return base64.b64encode(secrets.token_bytes(KEY_BYTES)).decode("ascii")


def _decode(raw: str, label: str) -> bytes:
    try:
        key = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise KeyRingError(f"{label} is not valid base64") from exc
    if len(key) != KEY_BYTES:
        raise KeyRingError(
            f"{label} decodes to {len(key)} bytes, expected {KEY_BYTES} for AES-256"
        )
    return key


@dataclass(frozen=True)
class KeyRing:
    """Keys this process can read, plus which one it writes with."""

    keys: dict[str, bytes]
    active_id: str
    index_key: bytes

    def active(self) -> tuple[str, bytes]:
        return self.active_id, self.keys[self.active_id]

    def get(self, key_id: str) -> bytes:
        try:
            return self.keys[key_id]
        except KeyError:
            raise KeyRingError(
                f"no key {key_id!r} loaded, can't read this value. have: "
                f"{sorted(self.keys)}. if this row is from before a rotation, "
                f"put the old key back in {ENV_KEYS}"
            ) from None

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "KeyRing":
        env = os.environ if env is None else env

        raw = (env.get(ENV_KEYS) or "").strip()
        if not raw:
            raise KeyRingError(
                f"{ENV_KEYS} isn't set so nothing can be encrypted. make one with "
                f'python -c "from security.keys import generate_key; print(generate_key())" '
                f"and set {ENV_KEYS}. see docs/ENCRYPTION.md"
            )

        keys: dict[str, bytes] = {}
        for entry in (part.strip() for part in raw.split(",")):
            if not entry:
                continue
            key_id, sep, material = entry.partition(":")
            if not sep:
                key_id, material = "1", entry
            key_id = key_id.strip()
            if not key_id:
                raise KeyRingError(f"{ENV_KEYS} contains an entry with an empty key id")
            # Key ids end up in the colon separated ciphertext header.
            if not all(ch.isalnum() or ch in "-_" for ch in key_id):
                raise KeyRingError(
                    f"key id {key_id!r} can only be letters, digits, dash, underscore"
                )
            if key_id in keys:
                raise KeyRingError(f"{ENV_KEYS} lists key id {key_id!r} more than once")
            keys[key_id] = _decode(material.strip(), f"key {key_id!r} in {ENV_KEYS}")

        if not keys:
            raise KeyRingError(f"{ENV_KEYS} is set but contains no usable keys")

        active_id = (env.get(ENV_ACTIVE) or "").strip()
        if not active_id:
            if len(keys) > 1:
                raise KeyRingError(
                    f"multiple keys loaded ({sorted(keys)}), set {ENV_ACTIVE} to "
                    f"whichever one should get new writes"
                )
            active_id = next(iter(keys))
        elif active_id not in keys:
            raise KeyRingError(
                f"{ENV_ACTIVE} is {active_id!r} but that id is not in {ENV_KEYS} "
                f"(loaded: {sorted(keys)})"
            )

        index_raw = (env.get(ENV_INDEX_KEY) or "").strip()
        if index_raw:
            index_key = _decode(index_raw, ENV_INDEX_KEY)
        else:
            # Derive one so local setup only needs one variable. Set
            # SMS_BLIND_INDEX_KEY separately in anything deployed.
            import hashlib

            index_key = hashlib.sha256(b"sms-blind-index\x00" + keys[active_id]).digest()

        return cls(keys=keys, active_id=active_id, index_key=index_key)


_cached: KeyRing | None = None


def active_keyring(refresh: bool = False) -> KeyRing:
    """Load the key ring once and reuse it. refresh=True is for tests."""
    global _cached
    if _cached is None or refresh:
        _cached = KeyRing.from_env()
    return _cached
