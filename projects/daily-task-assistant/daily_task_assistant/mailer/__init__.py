"""Mail helper package."""

from .gmail import (
    GmailAccountConfig,
    GmailError,
    load_account_from_env,
    send_email,
)

__all__ = ["GmailAccountConfig", "GmailError", "load_account_from_env", "send_email"]

