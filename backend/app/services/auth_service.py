import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type

from backend.app.services import store


LEGACY_PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ALGORITHM = "argon2id"
LEGACY_PASSWORD_ITERATIONS = 120_000
SALT_BYTES = 16
SESSION_TOKEN_BYTES = 32
REGISTERED_SESSION_DAYS = 7
DEMO_SESSION_HOURS = 24

_password_hasher = PasswordHasher(
    time_cost=int(os.getenv("ARGON2_TIME_COST", "3")),
    memory_cost=int(os.getenv("ARGON2_MEMORY_COST", "65536")),
    parallelism=int(os.getenv("ARGON2_PARALLELISM", "4")),
    type=Type.ID,
)


def create_user(name: str, email: str, password: str) -> dict | None:
    normalized_email = email.strip().lower()
    if store.get_user_by_email(normalized_email):
        return None

    now = store.now_iso()
    user = {
        "id": store.make_id("user"),
        "name": name.strip(),
        "email": normalized_email,
        "password_hash": _password_hasher.hash(password),
        "password_salt": "",
        "account_type": "registered",
        "password_algorithm": PASSWORD_ALGORITHM,
        "expires_at": None,
        "created_at": now,
        "updated_at": now,
    }
    store.create_user(user)
    return public_user(user)


def authenticate_user(email: str, password: str) -> dict | None:
    user = store.get_user_by_email(email.strip().lower())
    if not user or user["account_type"] != "registered":
        return None

    algorithm = user.get("password_algorithm") or LEGACY_PASSWORD_ALGORITHM
    if algorithm == LEGACY_PASSWORD_ALGORITHM:
        if not _verify_legacy_password(password, user["password_salt"], user["password_hash"]):
            return None
        updated = store.update_user_password(
            user["id"],
            _password_hasher.hash(password),
            "",
            PASSWORD_ALGORITHM,
            store.now_iso(),
        )
        return public_user(updated or user)

    if algorithm != PASSWORD_ALGORITHM:
        return None

    try:
        verified = _password_hasher.verify(user["password_hash"], password)
    except (InvalidHashError, VerifyMismatchError, VerificationError):
        return None
    if not verified:
        return None

    if _password_hasher.check_needs_rehash(user["password_hash"]):
        updated = store.update_user_password(
            user["id"],
            _password_hasher.hash(password),
            "",
            PASSWORD_ALGORITHM,
            store.now_iso(),
        )
        user = updated or user
    return public_user(user)


def create_demo_user() -> dict:
    now = _now()
    expires_at = now + timedelta(hours=DEMO_SESSION_HOURS)
    user = {
        "id": store.make_id("demo"),
        "name": "体验用户",
        "email": f"demo-{secrets.token_hex(8)}@example.invalid",
        "password_hash": "",
        "password_salt": "",
        "account_type": "demo",
        "password_algorithm": "none",
        "expires_at": _iso(expires_at),
        "created_at": _iso(now),
        "updated_at": _iso(now),
    }
    store.create_user(user)
    return user


def create_session(user_id: str, *, demo: bool = False) -> str:
    now = _now()
    expires_at = now + (
        timedelta(hours=DEMO_SESSION_HOURS) if demo else timedelta(days=REGISTERED_SESSION_DAYS)
    )
    token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
    store.create_auth_session(
        {
            "id": store.make_id("session"),
            "user_id": user_id,
            "token_hash": hash_session_token(token),
            "expires_at": _iso(expires_at),
            "revoked_at": None,
            "created_at": _iso(now),
        }
    )
    return token


def get_session_user(token: str | None) -> dict | None:
    user = get_session_user_record(token)
    return public_user(user) if user else None


def get_session_user_record(token: str | None) -> dict | None:
    if not token:
        return None
    return store.get_active_user_by_session_hash(hash_session_token(token), store.now_iso())


def revoke_session(token: str | None) -> bool:
    if not token:
        return False
    return store.revoke_auth_session(hash_session_token(token), store.now_iso())


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def public_user(user: dict | None) -> dict | None:
    if not user:
        return None
    return {
        "name": user["name"],
        "email": user["email"],
        "accountType": user.get("account_type", "registered"),
        "expiresAt": user.get("expires_at"),
        "createdAt": user["created_at"],
    }


def _verify_legacy_password(password: str, salt: str, expected_hash: str) -> bool:
    actual_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        LEGACY_PASSWORD_ITERATIONS,
    ).hex()
    return hmac.compare_digest(actual_hash, expected_hash)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()
