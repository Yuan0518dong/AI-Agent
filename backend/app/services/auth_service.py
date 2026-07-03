import hashlib
import hmac
import secrets

from backend.app.services import store


PASSWORD_ITERATIONS = 120_000
SALT_BYTES = 16


def create_user(name: str, email: str, password: str) -> dict | None:
    normalized_email = email.strip().lower()
    if store.get_user_by_email(normalized_email):
        return None

    now = store.now_iso()
    salt = secrets.token_hex(SALT_BYTES)
    user = {
        "id": store.make_id("user"),
        "name": name.strip(),
        "email": normalized_email,
        "password_hash": _hash_password(password, salt),
        "password_salt": salt,
        "created_at": now,
        "updated_at": now,
    }
    store.create_user(user)
    return public_user(user)


def authenticate_user(email: str, password: str) -> dict | None:
    user = store.get_user_by_email(email.strip().lower())
    if not user:
        return None

    expected_hash = _hash_password(password, user["password_salt"])
    if not hmac.compare_digest(expected_hash, user["password_hash"]):
        return None
    return public_user(user)


def public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "created_at": user["created_at"],
    }


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_ITERATIONS,
    ).hex()
