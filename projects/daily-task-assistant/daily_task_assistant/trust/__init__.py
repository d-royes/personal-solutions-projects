"""Trust gradient tracking for DATA's earned autonomy.

This module tracks user responses to DATA's suggestions to inform
future confidence levels and autonomy expansion.
"""
from __future__ import annotations

from .events import TrustEvent, log_trust_event, get_trust_summary

__all__ = ["TrustEvent", "log_trust_event", "get_trust_summary"]
