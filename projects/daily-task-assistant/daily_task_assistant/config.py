"""Configuration helpers for the Daily Task Assistant CLI."""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Optional


class ConfigError(RuntimeError):
    """Raised when required configuration is missing."""


@dataclass(slots=True)
class Settings:
    """Runtime configuration for the CLI."""

    smartsheet_token: str
    environment: str = "local"


def load_settings(
    *,
    token_var: str = "SMARTSHEET_API_TOKEN",
    fallback_secret_var: Optional[str] = "Smartsheet",
) -> Settings:
    """Load settings from environment variables.

    Args:
        token_var: Primary env var name for the Smartsheet token.
        fallback_secret_var: Optional alternate env var populated by Cursor secrets.

    Returns:
        Settings with the resolved token.

    Raises:
        ConfigError: if no token is available.
    """

    token = os.getenv(token_var)
    if not token and fallback_secret_var:
        token = os.getenv(fallback_secret_var)

    if not token:
        raise ConfigError(
            "Missing Smartsheet API token. Export SMARTSHEET_API_TOKEN or "
            "map the Cursor secret named 'Smartsheet'."
        )

    environment = os.getenv("DTA_ENV", "local")

    return Settings(smartsheet_token=token.strip(), environment=environment)
