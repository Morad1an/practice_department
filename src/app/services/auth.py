from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Literal

from fastapi import Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.config import settings
from src.app.database import async_session_maker
from src.app.models.app_user import AppUserOrm

AuthRole = Literal["viewer", "editor"]
_PASSWORD_ITERATIONS = 310_000
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SESSION_SALT = "diplom-auth-session"
_VALID_ROLES: set[str] = {"viewer", "editor"}
_DUMMY_PASSWORD_HASH = (
    "pbkdf2_sha256$310000$ZHVtbXlfc2FsdF8xMjM0NTY3OA==$"
    "$"
    "I5q3N6K8Q1Q4m8JUzvPjM6b7N8R8_-zEr6WzL4sY5dU="
)


@dataclass(slots=True)
class AuthenticatedUser:
    id: int
    username: str
    role: AuthRole
    is_active: bool

    @property
    def can_edit(self) -> bool:
        return self.role == "editor"


def normalize_username(username: str) -> str:
    prepared = (username or "").strip().lower()
    if not prepared:
        raise ValueError("Логин не может быть пустым.")
    if len(prepared) > 128:
        raise ValueError("Логин превышает допустимую длину 128 символов.")
    return prepared


def normalize_role(role: str) -> AuthRole:
    prepared = (role or "").strip().lower()
    if prepared not in _VALID_ROLES:
        raise ValueError("Допустимые роли: viewer, editor.")
    return prepared  # type: ignore[return-value]


def validate_password(password: str) -> str:
    prepared = password or ""
    if len(prepared) < 8:
        raise ValueError("Пароль должен содержать минимум 8 символов.")
    return prepared


def hash_password(password: str) -> str:
    prepared = validate_password(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        prepared.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=32,
    )
    encoded_salt = base64.urlsafe_b64encode(salt).decode("ascii")
    encoded_digest = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${encoded_salt}${encoded_digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, *parts = stored_hash.split("$")
    except (TypeError, ValueError):
        return False

    try:
        if algorithm == "scrypt":
            n_raw, r_raw, p_raw, encoded_salt, encoded_digest = parts
            salt = base64.urlsafe_b64decode(encoded_salt.encode("ascii"))
            expected_digest = base64.urlsafe_b64decode(encoded_digest.encode("ascii"))
            actual_digest = hashlib.scrypt(
                (password or "").encode("utf-8"),
                salt=salt,
                n=int(n_raw),
                r=int(r_raw),
                p=int(p_raw),
                dklen=len(expected_digest),
            )
        elif algorithm == "pbkdf2_sha256":
            iterations_raw, encoded_salt, encoded_digest = parts
            salt = base64.urlsafe_b64decode(encoded_salt.encode("ascii"))
            expected_digest = base64.urlsafe_b64decode(encoded_digest.encode("ascii"))
            actual_digest = hashlib.pbkdf2_hmac(
                "sha256",
                (password or "").encode("utf-8"),
                salt,
                int(iterations_raw),
            )
        else:
            return False
    except (TypeError, ValueError):
        return False

    return hmac.compare_digest(actual_digest, expected_digest)


def build_session_cookie_value(user_id: int) -> str:
    serializer = URLSafeTimedSerializer(
        settings.AUTH_SECRET_KEY,
        signer_kwargs={"digest_method": hashlib.sha256},
    )
    return serializer.dumps({"user_id": user_id}, salt=_SESSION_SALT)


def parse_session_cookie_value(cookie_value: str | None) -> int | None:
    if not cookie_value:
        return None
    serializer = URLSafeTimedSerializer(
        settings.AUTH_SECRET_KEY,
        signer_kwargs={"digest_method": hashlib.sha256},
    )
    try:
        payload = serializer.loads(
            cookie_value,
            salt=_SESSION_SALT,
            max_age=settings.AUTH_SESSION_MAX_AGE_SECONDS,
        )
    except (BadSignature, SignatureExpired):
        return None
    user_id = payload.get("user_id")
    if not isinstance(user_id, int) or user_id <= 0:
        return None
    return user_id


def build_authenticated_user(user: AppUserOrm) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=user.id,
        username=user.username,
        role=normalize_role(user.role),
        is_active=bool(user.is_active),
    )


async def fetch_auth_user_by_id(
    session: AsyncSession,
    *,
    user_id: int,
) -> AuthenticatedUser | None:
    user = await session.get(AppUserOrm, user_id)
    if user is None or not user.is_active:
        return None
    return build_authenticated_user(user)


async def authenticate_user(
    session: AsyncSession,
    *,
    username: str,
    password: str,
) -> AuthenticatedUser | None:
    normalized_username = normalize_username(username)
    user = await session.scalar(
        select(AppUserOrm).where(func.lower(AppUserOrm.username) == normalized_username)
    )
    if user is None or not user.is_active:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        return None
    if not verify_password(password, user.password_hash):
        return None
    return build_authenticated_user(user)


async def upsert_auth_user(
    session: AsyncSession,
    *,
    username: str,
    password: str,
    role: str,
    is_active: bool = True,
) -> AuthenticatedUser:
    normalized_username = normalize_username(username)
    normalized_role = normalize_role(role)
    password_hash = hash_password(password)

    user = await session.scalar(
        select(AppUserOrm).where(func.lower(AppUserOrm.username) == normalized_username)
    )
    if user is None:
        user = AppUserOrm(
            username=normalized_username,
            password_hash=password_hash,
            role=normalized_role,
            is_active=is_active,
        )
        session.add(user)
        await session.flush()
    else:
        user.username = normalized_username
        user.password_hash = password_hash
        user.role = normalized_role
        user.is_active = is_active

    await session.commit()
    return build_authenticated_user(user)


async def resolve_auth_user_from_session_cookie(
    request: Request,
) -> AuthenticatedUser | None:
    user_id = parse_session_cookie_value(request.cookies.get(settings.AUTH_COOKIE_NAME))
    if user_id is None:
        return None

    async with async_session_maker() as session:
        return await fetch_auth_user_by_id(session, user_id=user_id)


def resolve_safe_next_path(next_path: str | None) -> str:
    prepared = (next_path or "").strip()
    if not prepared.startswith("/") or prepared.startswith("//"):
        return "/organizations/active"
    return prepared
