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
ALLOWED_EMAILS_ENV = "DTA_ALLOWED_EMAILS"
# Cloud Scheduler service account for automated sync
SCHEDULER_SERVICE_ACCOUNT_ENV = "CLOUD_SCHEDULER_SA"
DEFAULT_SCHEDULER_SA = "cloud-scheduler-invoker@daily-task-assistant-church.iam.gserviceaccount.com"
# Default user for scheduled operations
SCHEDULER_DEFAULT_USER = "davidroyes@southpointsda.org"

# Default allowed emails (can be overridden via DTA_ALLOWED_EMAILS env var)
DEFAULT_ALLOWED_EMAILS = {
    "davidroyes@southpointsda.org",
    "david.a.royes@gmail.com",
}


class AuthError(HTTPException):
    def __init__(self, detail: str, code: int = status.HTTP_401_UNAUTHORIZED) -> None:
        super().__init__(status_code=code, detail=detail)


@lru_cache
def _audiences() -> list[str]:
    audience = os.getenv(ALLOWED_AUDIENCE_ENV) or os.getenv(CLIENT_ID_ENV)
    if not audience:
        return []
    return [aud.strip() for aud in audience.split(",") if aud.strip()]


@lru_cache
def _allowed_emails() -> set[str]:
    """Get the set of allowed email addresses."""
    env_emails = os.getenv(ALLOWED_EMAILS_ENV)
    if env_emails:
        return {email.strip().lower() for email in env_emails.split(",") if email.strip()}
    return {email.lower() for email in DEFAULT_ALLOWED_EMAILS}


def _verify_cloud_scheduler_token(token: str) -> str | None:
    """Verify if token is from Cloud Scheduler service account.
    
    Returns the default user email if valid, None otherwise.
    """
    try:
        # Cloud Scheduler OIDC tokens have the Cloud Run URL as audience
        # We verify the token without audience check first, then validate the email
        request = google_requests.Request()
        # Decode without audience verification to check issuer
        idinfo = id_token.verify_oauth2_token(
            token, request, audience=None,
            clock_skew_in_seconds=10
        )
        
        email = idinfo.get("email", "")
        scheduler_sa = os.getenv(SCHEDULER_SERVICE_ACCOUNT_ENV, DEFAULT_SCHEDULER_SA)
        
        if email == scheduler_sa:
            # Valid Cloud Scheduler request - return default user
            return SCHEDULER_DEFAULT_USER
        return None
    except Exception:
        return None


def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    dev_user: str | None = Header(default=None, alias="X-User-Email"),
) -> str:
    """Return the authenticated user's email.

    During development/testing set DTA_DEV_AUTH_BYPASS=1 and supply X-User-Email.
    Also accepts Cloud Scheduler OIDC tokens for automated sync.
    """

    if os.getenv(DEV_BYPASS_ENV) == "1":
        if dev_user:
            # Still check allowlist in dev mode
            allowed = _allowed_emails()
            if allowed and dev_user.lower() not in allowed:
                raise AuthError(
                    f"Access denied. Email '{dev_user}' is not authorized.",
                    code=status.HTTP_403_FORBIDDEN,
                )
            return dev_user
        raise AuthError(
            "Auth bypass enabled but X-User-Email header missing (dev only)."
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise AuthError("Missing Bearer token.")

    token = authorization.split(" ", 1)[1].strip()
    
    # First, check if this is a Cloud Scheduler request
    scheduler_user = _verify_cloud_scheduler_token(token)
    if scheduler_user:
        return scheduler_user
    
    # Otherwise, verify as normal OAuth token
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
    
    # Check if email is in the allowlist
    allowed = _allowed_emails()
    if allowed and email.lower() not in allowed:
        raise AuthError(
            f"Access denied. Email '{email}' is not authorized to use this application.",
            code=status.HTTP_403_FORBIDDEN,
        )
    
    return email

