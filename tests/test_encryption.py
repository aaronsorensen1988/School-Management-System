"""Tests for the encrypted columns. UMA-003 / T1-012.

The one that actually matters is test_db_holds_ciphertext. The rest check
the pieces work, that one checks what someone with a stolen db would see.
"""

import base64

import pytest
from sqlalchemy import Column, Integer, String, create_engine, text
from sqlalchemy.orm import Session

from database.database import Base
from database.types import BlindIndex, EncryptedString
from security.crypto import DecryptionError, blind_index, decrypt, encrypt, is_encrypted
from security.keys import KeyRing, KeyRingError, generate_key

KEY_A = generate_key()
KEY_B = generate_key()


@pytest.fixture
def ring():
    return KeyRing.from_env({"SMS_ENCRYPTION_KEYS": f"k1:{KEY_A}"})


def test_round_trip(ring):
    sealed = encrypt("123-45-6789", context="students.ssn", keyring=ring)
    assert decrypt(sealed, context="students.ssn", keyring=ring) == "123-45-6789"
    assert "123-45-6789" not in sealed


def test_no_key_means_no_start():
    # better to fail loudly than quietly save student records in the clear
    with pytest.raises(KeyRingError):
        KeyRing.from_env({})


def test_same_input_encrypts_differently(ring):
    # if these matched you could spot which students share an address
    a = encrypt("same", context="t.c", keyring=ring)
    b = encrypt("same", context="t.c", keyring=ring)
    assert a != b
    assert decrypt(a, context="t.c", keyring=ring) == decrypt(b, context="t.c", keyring=ring)


def test_wrong_key_fails(ring):
    other = KeyRing.from_env({"SMS_ENCRYPTION_KEYS": f"k1:{KEY_B}"})
    sealed = encrypt("secret", context="t.c", keyring=ring)
    with pytest.raises(DecryptionError):
        decrypt(sealed, context="t.c", keyring=other)


def test_tampering_gets_caught(ring):
    sealed = encrypt("B+", context="grades.letter", keyring=ring)
    prefix, payload = sealed.rsplit(":", 1)
    blob = bytearray(base64.b64decode(payload))
    blob[-1] ^= 0x01  # flip a bit
    with pytest.raises(DecryptionError):
        decrypt(f"{prefix}:{base64.b64encode(bytes(blob)).decode()}",
                context="grades.letter", keyring=ring)


def test_cant_move_a_value_to_another_column(ring):
    # someone with db write access shouldn't be able to promote a value
    sealed = encrypt("student", context="users.role", keyring=ring)
    with pytest.raises(DecryptionError):
        decrypt(sealed, context="users.display_name", keyring=ring)


def test_rotation(ring):
    old = encrypt("written before", context="t.c", keyring=ring)
    rotated = KeyRing.from_env({
        "SMS_ENCRYPTION_KEYS": f"k1:{KEY_A},k2:{KEY_B}",
        "SMS_ENCRYPTION_ACTIVE_KEY": "k2",
    })
    # old rows still read, new writes use the new key
    assert decrypt(old, context="t.c", keyring=rotated) == "written before"
    assert encrypt("after", context="t.c", keyring=rotated).split(":")[2] == "k2"


def test_blind_index_is_stable_and_ignores_case(ring):
    a = blind_index("  Ada@School.edu ", "users.email", keyring=ring)
    b = blind_index("ada@school.edu", "users.email", keyring=ring)
    assert a == b
    # the whole address, not a fragment. "ada" on its own is three valid
    # base64 characters and turns up in a random token about once in 800
    # runs, which is a test that fails for no reason.
    assert "ada@school.edu" not in a.lower()


def test_blind_index_needs_the_key(ring):
    """Why this is an HMAC and not a plain hash. Without the key anyone with
    a copy of the database could hash a list of likely addresses and match
    the rows up."""
    other = KeyRing.from_env({"SMS_ENCRYPTION_KEYS": f"k1:{KEY_B}"})
    assert blind_index("ada@school.edu", "users.email", keyring=ring) != blind_index(
        "ada@school.edu", "users.email", keyring=other
    )


# --- through the ORM, which is how everyone else will hit this ---

class Enrollee(Base):
    """Stand-in table. Real ones are users (T1-002) and students (T1-017)."""

    __tablename__ = "test_enrollees"

    id = Column(Integer, primary_key=True, index=True)
    display_name = Column(String, nullable=False)
    ssn = Column(EncryptedString(context="test_enrollees.ssn"), nullable=False)
    email = Column(EncryptedString(context="test_enrollees.email"), nullable=False)
    email_lookup = Column(BlindIndex(context="test_enrollees.email"), unique=True)
    note = Column(EncryptedString(context="test_enrollees.note"), nullable=True)


@pytest.fixture
def session(monkeypatch):
    monkeypatch.setenv("SMS_ENCRYPTION_KEYS", f"k1:{KEY_A}")
    from security import keys as keys_module
    keys_module.active_keyring(refresh=True)

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine, tables=[Enrollee.__table__])
    with Session(engine) as s:
        s.add(Enrollee(
            display_name="Jane Smith",
            ssn="123-45-6789",
            email="jane@school.edu",
            email_lookup="jane@school.edu",
            note="Lives with her grandmother during the week.",
        ))
        s.commit()
        yield s
    keys_module._cached = None


def test_orm_reads_back_plaintext(session):
    row = session.query(Enrollee).one()
    assert row.ssn == "123-45-6789"
    assert row.email == "jane@school.edu"


def test_db_holds_ciphertext(session):
    """The thing UMA-003 actually promised.

    Raw SQL so the ORM never gets a chance to decrypt. This is what someone
    holding a copy of the db file sees.
    """
    name, ssn, email, note = session.execute(
        text("SELECT display_name, ssn, email, note FROM test_enrollees")
    ).one()

    assert name == "Jane Smith"  # not encrypted on purpose, it's a directory
    for value in (ssn, email, note):
        assert is_encrypted(value)
    blob = " ".join([ssn, email, note])
    for leaked in ("123-45-6789", "jane@school.edu", "grandmother"):
        assert leaked not in blob


def test_lookup_by_blind_index(session):
    row = session.query(Enrollee).filter(
        Enrollee.email_lookup == "JANE@School.edu"
    ).one()
    assert row.display_name == "Jane Smith"


def test_null_stays_null(session):
    session.add(Enrollee(display_name="No Note", ssn="000-00-0000",
                         email="none@school.edu", email_lookup="none@school.edu",
                         note=None))
    session.commit()
    row = session.query(Enrollee).filter(Enrollee.display_name == "No Note").one()
    assert row.note is None


def test_resaving_a_row_doesnt_double_encrypt(session):
    row = session.query(Enrollee).one()
    row.display_name = "Jane S."  # touch a different column
    session.commit()
    session.expire_all()
    assert session.query(Enrollee).one().ssn == "123-45-6789"
