"""Tests for session cookie management."""

import json
import pytest
from pathlib import Path

from naver_blog.session import load_session, SessionError


@pytest.fixture
def valid_cookies(tmp_path):
    """Create a valid session file with required cookies."""
    cookies = [
        {"name": "NID_AUT", "value": "test_aut_value", "domain": ".naver.com", "path": "/"},
        {"name": "NID_SES", "value": "test_ses_value", "domain": ".naver.com", "path": "/"},
        {"name": "OTHER", "value": "other_value", "domain": ".naver.com", "path": "/"},
    ]
    session_file = tmp_path / "session.json"
    session_file.write_text(json.dumps(cookies))
    return str(session_file)


@pytest.fixture
def missing_cookies(tmp_path):
    """Create a session file missing required cookies."""
    cookies = [
        {"name": "OTHER", "value": "value", "domain": ".naver.com", "path": "/"},
    ]
    session_file = tmp_path / "session.json"
    session_file.write_text(json.dumps(cookies))
    return str(session_file)


def test_load_session_success(valid_cookies):
    session = load_session(valid_cookies)
    assert session.cookies.get("NID_AUT") == "test_aut_value"
    assert session.cookies.get("NID_SES") == "test_ses_value"
    assert "User-Agent" in session.headers


def test_load_session_missing_file():
    with pytest.raises(SessionError, match="not found"):
        load_session("/nonexistent/path/session.json")


def test_load_session_missing_cookies(missing_cookies):
    with pytest.raises(SessionError, match="Required cookies missing"):
        load_session(missing_cookies)


def test_load_session_user_agent(valid_cookies):
    session = load_session(valid_cookies)
    assert "Chrome/131" in session.headers["User-Agent"]
