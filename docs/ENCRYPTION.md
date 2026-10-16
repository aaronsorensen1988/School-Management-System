# Encrypting sensitive fields

UMA-003 / T1-012. Nick.

## Setup

You need a key or the app won't start. Make one:

```
python -c "from security.keys import generate_key; print(generate_key())"
```

Then:

```
export SMS_ENCRYPTION_KEYS="k1:<your key>"
export SMS_ENCRYPTION_ACTIVE_KEY="k1"
```

Windows PowerShell it's `$env:SMS_ENCRYPTION_KEYS="k1:<your key>"`.

Generate your own, don't paste one in Discord, don't commit one. `.env` is
gitignored for that reason.

## Encrypting a column

```python
from database.database import Base
from database.types import EncryptedString

class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    ssn = Column(EncryptedString(context="students.ssn"), nullable=False)
```

That's it, reads and writes handle themselves.

`context` is the table and column name. It gets checked on decrypt so a
value moved to another column won't open. Don't change it once there are
rows or you can't read them.

Don't encrypt everything, you lose search and sort on whatever you do.
SSNs, addresses, guardian contacts, health notes yes. Names no.

## You can't search an encrypted column

Same input encrypts differently every time so `WHERE email = 'x'` matches
nothing. That's on purpose, otherwise you could tell which students share
an address.

For something you need to look up, like login email, add a BlindIndex
column next to it:

```python
email = Column(EncryptedString(context="users.email"), nullable=False)
email_lookup = Column(BlindIndex(context="users.email"), unique=True, index=True)
```

Assign the plaintext to both, query against `email_lookup`. Case and
spaces don't matter. Same `context` on both is what ties them together.

Catch: same value gives the same token, so you can tell which rows match
without reading them. Fine for email. Not fine if the match is the secret.

## Rotating a key

Each value records which key wrote it. Load both, make the new one active:

```
export SMS_ENCRYPTION_KEYS="k1:<old>,k2:<new>"
export SMS_ENCRYPTION_ACTIVE_KEY="k2"
```

New writes use k2, old rows still read. Rewrite the old rows then drop k1.
Drop it early and those rows are gone.

## Errors

`Not encrypted` means the row has plaintext from before the column was
encrypted.

`Auth check failed` means wrong key, wrong context, or someone changed the
value.

`no key ... loaded` means a key got dropped while rows written under it
still exist. Put it back.

Don't wrap a decrypt in try/except and return a blank. Both of those need
someone to actually look.

## Tests

```
python -m pytest tests/test_encryption.py -v
```

`test_db_holds_ciphertext` is the one that matters. It reads the table
with raw SQL so the ORM can't decrypt first, which is what someone with a
stolen db file would see.
