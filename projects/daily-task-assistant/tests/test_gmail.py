import base64
import os

import pytest

from daily_task_assistant.mailer.gmail import (
    GmailError,
    _build_raw_message,
    load_account_from_env,
)


def test_build_raw_message_encodes_email_headers():
    raw = _build_raw_message(
        from_address="from@example.com",
        to_address="to@example.com",
        subject="Test Subject",
        body="Hello world",
    )
    decoded = base64.urlsafe_b64decode(raw.encode("utf-8"))
    text = decoded.decode("utf-8")
    assert "Subject: Test Subject" in text
    assert "Hello world" in text


def test_build_raw_message_includes_cc_header():
    raw = _build_raw_message(
        from_address="from@example.com",
        to_address="to@example.com",
        subject="Test with CC",
        body="Hello world",
        cc_address="cc1@example.com, cc2@example.com",
    )
    decoded = base64.urlsafe_b64decode(raw.encode("utf-8"))
    text = decoded.decode("utf-8")
    assert "Cc: cc1@example.com, cc2@example.com" in text
    assert "To: to@example.com" in text


def test_build_raw_message_without_cc():
    raw = _build_raw_message(
        from_address="from@example.com",
        to_address="to@example.com",
        subject="No CC",
        body="Hello world",
        cc_address=None,
    )
    decoded = base64.urlsafe_b64decode(raw.encode("utf-8"))
    text = decoded.decode("utf-8")
    assert "Cc:" not in text


def test_load_account_from_env_happy_path(monkeypatch):
    monkeypatch.setenv("CHURCH_GMAIL_CLIENT_ID", "abc")
    monkeypatch.setenv("CHURCH_GMAIL_CLIENT_SECRET", "def")
    monkeypatch.setenv("CHURCH_GMAIL_REFRESH_TOKEN", "ghi")
    monkeypatch.setenv("CHURCH_GMAIL_ADDRESS", "from@example.com")
    config = load_account_from_env("church")
    assert config.client_id == "abc"
    assert config.from_address == "from@example.com"


def test_load_account_missing_fields(monkeypatch):
    for key in list(os.environ.keys()):
        if key.startswith("CHURCH_GMAIL_"):
            monkeypatch.delenv(key, raising=False)
    with pytest.raises(GmailError):
        load_account_from_env("church")

