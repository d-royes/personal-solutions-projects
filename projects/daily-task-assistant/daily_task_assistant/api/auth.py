"""Google ID token verification helpers."""
from __future__ import annotations

import os
from functools import lru_cache

from fastapi import Header, HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

DEV_BYPASS_ENV = "DTA_DEV_AUTH_BYPASS"
CLIENT_ID_ENV = "GOOGLE_OAUTH_CLIENT_ID"
ALLOWED_AUDIENCE_ENV = "GOOGLE_OAUTH_AUDIENCE"


class AuthError(HTTPException):
    def __init__(self, detail: str, code: int = status.HTTP_401_UNAUTHORIZED) -> None:
        super().__init__(status_code=code, detail=detail)


@lru_cache
def _audiences() -> list[str]:
    audience = os.getenv(ALLOWED_AUDIENCE_ENV) or os.getenv(CLIENT_ID_ENV)
    if not audience:
        return []
    return [aud.strip() for aud in audience.split(",") if aud.strip()]


def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    dev_user: str | None = Header(default=None, alias="X-User-Email"),
) -> str:
    """Return the authenticated user's email.

    During development/testing set DTA_DEV_AUTH_BYPASS=1 and supply X-User-Email.
    """

    if os.getenv(DEV_BYPASS_ENV) == "1":
        if dev_user:
            return dev_user
        raise AuthError(
            "Auth bypass enabled but X-User-Email header missing (dev only)."
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise AuthError("Missing Bearer token.")

    token = authorization.split(" ", 1)[1].strip()
    request = google_requests.Request()
    audiences = _audiences()
    if not audiences:
        raise AuthError("Server missing GOOGLE_OAUTH_CLIENT_ID or audience config.")

    validation_error: ValueError | None = None
    for audience in audiences:
        try:
            idinfo = id_token.verify_oauth2_token(token, request, audience)
            break
        except ValueError as exc:
            validation_error = exc
    else:
        raise AuthError(f"Invalid token: {validation_error}")

    email = idinfo.get("email")
    if not email:
        raise AuthError("Token missing email claim.")
    return email

