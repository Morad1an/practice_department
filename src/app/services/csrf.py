from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import cast

from fastapi import Request
from itsdangerous import BadSignature, URLSafeSerializer

from src.app.config import settings

_CSRF_SALT = "diplom-csrf-token"
_HEADER_NAME = "X-CSRF-Token"


def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(
        settings.AUTH_SECRET_KEY,
        salt=_CSRF_SALT,
        signer_kwargs={"digest_method": hashlib.sha256},
    )


def build_csrf_token() -> str:
    return _serializer().dumps({"nonce": secrets.token_urlsafe(32)})


def is_valid_csrf_token(token: str | None) -> bool:
    if not token:
        return False
    try:
        payload = _serializer().loads(token)
    except BadSignature:
        return False
    nonce = payload.get("nonce")
    return isinstance(nonce, str) and len(nonce) >= 32


def ensure_request_csrf_token(request: Request) -> tuple[str, bool]:
    cookie_token = request.cookies.get(settings.CSRF_COOKIE_NAME)
    if is_valid_csrf_token(cookie_token):
        return cast(str, cookie_token), False
    return build_csrf_token(), True


def validate_request_csrf(request: Request, *, cookie_token: str) -> bool:
    submitted_token = request.headers.get(_HEADER_NAME)
    return validate_submitted_csrf_token(
        submitted_token if isinstance(submitted_token, str) else None,
        cookie_token=cookie_token,
    )


def validate_submitted_csrf_token(
    submitted_token: str | None,
    *,
    cookie_token: str | None,
) -> bool:
    if not isinstance(submitted_token, str):
        return False
    if not isinstance(cookie_token, str):
        return False
    if not hmac.compare_digest(submitted_token, cookie_token):
        return False
    return is_valid_csrf_token(submitted_token)
