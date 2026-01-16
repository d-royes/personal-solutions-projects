"""Global settings module for DATA application."""
from .global_settings import (
    get_settings,
    update_settings,
    record_sync_result,
    DEFAULT_SETTINGS,
    SyncSettings,
    GlobalSettings,
)

__all__ = [
    "get_settings",
    "update_settings",
    "record_sync_result",
    "DEFAULT_SETTINGS",
    "SyncSettings",
    "GlobalSettings",
]
