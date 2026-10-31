import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def fresh_settings(monkeypatch):
    """Every test starts from the real config/agent.toml, and one test's settings never leak into another."""
    from agent import settings

    monkeypatch.setattr(settings, "_current", None)


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """A private data folder, so a test can never touch the teacher's real files."""
    import agent.__main__ as app
    import agent.tools as tools

    monkeypatch.setattr(app, "DATA", tmp_path)
    monkeypatch.setattr(tools, "MEMORY_DIR", tmp_path / "memory")
    monkeypatch.setenv("AGENT_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def smtp(monkeypatch):
    """A fake mail server and a configured mailbox."""
    import smtplib

    from tests.helpers import FakeSMTP

    FakeSMTP.sent, FakeSMTP.login_fails, FakeSMTP.last_login = [], False, None
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    for k, v in {"SMTP_USER": "me@example.com", "SMTP_PASSWORD": "s3cret-pass", "EMAIL_TO": "teacher@example.com"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("SMTP_PORT", raising=False)
    return FakeSMTP
