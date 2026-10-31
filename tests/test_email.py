"""spec.md check 9: email is sent only after a yes, only to the chosen address, and an error never shows the password."""
import pathlib

import pytest

import agent.__main__ as app
from agent import emailer
from agent.tools import TOOLS
from tests.helpers import ScriptedChannel


@pytest.fixture
def files(tmp_path):
    a, b = tmp_path / "lesson-plan.docx", tmp_path / "quiz.xlsx"
    a.write_bytes(b"docx-bytes"); b.write_bytes(b"xlsx-bytes")
    return [a, b]


def offer(files, answers):
    ch = ScriptedChannel(answers)
    app.offer_email(ch, files, "data types")
    return ch


def test_nothing_is_asked_when_email_is_not_set_up(monkeypatch, files):
    for k in ("SMTP_USER", "SMTP_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    ch = offer(files, [])                       # any question would fail the test
    assert ch.titles == []


def test_declining_sends_nothing(smtp, files):
    offer(files, ["back"])
    assert smtp.sent == []


def test_yes_sends_to_the_chosen_saved_address_with_the_files_attached(smtp, files):
    offer(files, [0])
    (msg,) = smtp.sent
    assert msg["To"] == "teacher@example.com" and msg["From"] == "me@example.com"
    assert sorted(p.get_filename() for p in msg.iter_attachments()) == ["lesson-plan.docx", "quiz.xlsx"]
    assert "data types" in msg["Subject"]


def test_a_typed_address_is_used_only_as_typed(smtp, files):
    offer(files, [("other", "colleague@example.org")])
    assert [m["To"] for m in smtp.sent] == ["colleague@example.org"]


@pytest.mark.parametrize("bad", ["not-an-address", "a@b", "a b@c.com", "x@y.com, z@y.com", "x@y.com;z@y.com"])
def test_an_invalid_or_multiple_address_sends_nothing(smtp, files, bad):
    ch = offer(files, [("other", bad)])
    assert smtp.sent == [] and any("nothing was sent" in t for t in ch.said)


def test_a_login_failure_is_explained_without_showing_the_password(smtp, files):
    smtp.login_fails = True
    ch = offer(files, [0])
    said = " ".join(ch.said)
    assert "Email not sent" in said and "app password" in said and "s3cret-pass" not in said and smtp.sent == []


def test_a_server_outage_is_reported_without_details(monkeypatch, smtp, files):
    import smtplib

    class Down(smtp):
        def __init__(self, *a, **k):
            raise OSError("connection refused to smtp.example.com with s3cret-pass")

    monkeypatch.setattr(smtplib, "SMTP_SSL", Down)
    ch = offer(files, [0])
    assert "Email not sent" in " ".join(ch.said) and "s3cret-pass" not in " ".join(ch.said)


def test_total_attachment_size_is_capped_and_skipped_files_are_reported(smtp, tmp_path):
    big = tmp_path / "big.pdf"; big.write_bytes(b"0" * (emailer.max_total_bytes() + 1))
    small = tmp_path / "small.docx"; small.write_bytes(b"ok")
    result = emailer.send_files("t@example.com", "s", "b", [small, big])
    assert "Sent 1 file" in result and "big.pdf" in result
    assert [p.get_filename() for p in smtp.sent[0].iter_attachments()] == ["small.docx"]


def test_sending_with_no_files_is_an_error(smtp):
    with pytest.raises(RuntimeError, match="No files"):
        emailer.send_files("t@example.com", "s", "b", [])


def test_other_ports_use_starttls(monkeypatch, smtp, files):
    monkeypatch.setenv("SMTP_PORT", "587")
    started = []
    monkeypatch.setattr(smtp, "starttls", lambda self, **kw: started.append(1))
    emailer.send_files("t@example.com", "s", "b", files)
    assert started == [1]


def test_the_model_has_no_way_to_send_email():
    assert not [t["name"] for t in TOOLS if "mail" in t["name"].lower() or "smtp" in t["name"].lower()]
