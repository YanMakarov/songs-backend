"""Password hashing.

Argon2id with the library's defaults. The parameters are deliberately not
tuned here: argon2-cffi tracks the current recommendation, and a number
hand-picked today would quietly rot. `needs_rehash` lets a stored hash be
upgraded when those defaults move.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError, VerificationError

_hasher = PasswordHasher()

#: Verified against when the username does not exist. Hashing anyway keeps a
#: failed login the same cost whether or not the account is real — otherwise
#: response time answers "does this user exist?" for anyone who asks.
_DUMMY_HASH = _hasher.hash("not-a-real-password")

MIN_PASSWORD_LENGTH = 10


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Check a password, in the same time whether or not the user exists."""

    try:
        _hasher.verify(password_hash or _DUMMY_HASH, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return password_hash is not None


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True
