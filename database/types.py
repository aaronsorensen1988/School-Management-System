"""Column types that encrypt themselves. UMA-003 / T1-012.

Mark the column once and reads/writes handle themselves, so nobody has to
remember to call anything:

    ssn = Column(EncryptedString(context="students.ssn"), nullable=False)

Don't encrypt everything. You lose search, sort, join and constraints on
whatever you do. docs/ENCRYPTION.md.
"""

from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.types import TypeDecorator

from security.crypto import blind_index, decrypt, encrypt, is_encrypted

# nonce + tag + base64 makes the stored value a fair bit longer than the
# plaintext, so a column with a declared width needs headroom
CIPHERTEXT_OVERHEAD = 64


def ciphertext_length(plaintext_length: int) -> int:
    """Column width needed to store plaintext_length characters encrypted."""
    return ((plaintext_length * 4 + 2) // 3) + CIPHERTEXT_OVERHEAD


class EncryptedString(TypeDecorator):
    """Text column that encrypts on write and decrypts on read.

    context is "table.column". It gets checked on decrypt, so a value moved
    to another column won't open. Don't change it once rows exist.

    max_plaintext only matters on databases that need a declared width.
    """

    impl = Text
    cache_ok = True

    def __init__(self, context: str, max_plaintext: int | None = None, **kwargs):
        if not context or "." not in context:
            raise ValueError(
                "EncryptedString needs context='table.column', eg "
                "EncryptedString(context='students.ssn'). it's what stops a value "
                "being moved to a different column"
            )
        self.context = context
        self.max_plaintext = max_plaintext
        if max_plaintext is not None:
            kwargs.setdefault("length", ciphertext_length(max_plaintext))
            self.impl = String
        super().__init__(**kwargs)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if is_encrypted(value):
            # already encrypted. saving a row back without touching this
            # field would otherwise wrap it twice, and it'd still read fine,
            # which is why it needs catching
            return value
        if not isinstance(value, str):
            raise TypeError(
                f"{self.context} is encrypted and takes str, got "
                f"{type(value).__name__}. convert it yourself so the encoding "
                f"is something you picked"
            )
        if self.max_plaintext is not None and len(value) > self.max_plaintext:
            raise ValueError(
                f"{self.context} accepts at most {self.max_plaintext} characters, got {len(value)}"
            )
        return encrypt(value, context=self.context)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return decrypt(value, context=self.context)

    def __repr__(self) -> str:
        return f"EncryptedString(context={self.context!r})"


class BlindIndex(TypeDecorator):
    """Searchable lookup token for a neighbouring encrypted column.

        email = Column(EncryptedString(context="users.email"))
        email_lookup = Column(BlindIndex(context="users.email"), unique=True)

    Assign the plaintext to both, query against the lookup one. Same
    context on both is what ties them together.

    See blind_index in security/crypto.py for the tradeoff.
    """

    impl = String(44)  # base64 of a SHA-256 digest
    cache_ok = True

    def __init__(self, context: str, **kwargs):
        if not context or "." not in context:
            raise ValueError("BlindIndex needs a context of the form 'table.column'")
        self.context = context
        super().__init__(**kwargs)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError(
                f"{self.context} blind index takes str, got {type(value).__name__}"
            )
        return blind_index(value, context=self.context)

    def process_result_value(self, value, dialect):
        # one way on purpose, the real value lives in the encrypted column
        return value

    def __repr__(self) -> str:
        return f"BlindIndex(context={self.context!r})"


__all__ = ["BlindIndex", "EncryptedString", "ciphertext_length"]
