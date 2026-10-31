"""Send generated files by email (SMTP).

Sending is never done by the model: the session code offers it to the teacher
and only sends after the teacher says yes and picks the recipient.

Settings (.env):
  SMTP_HOST      default smtp.gmail.com
  SMTP_PORT      default 465 (SSL); any other port uses STARTTLS
  SMTP_USER      login, usually your email address
  SMTP_PASSWORD  an app password (Gmail: needs 2-step verification)
  EMAIL_FROM     optional, defaults to SMTP_USER
  EMAIL_TO       optional default recipients, comma separated
"""
import mimetypes
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from . import settings

ADDRESS = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")


def max_total_bytes() -> int:
    """Total attachment size allowed (email_max_mb in config/agent.toml)."""
    return settings.get().email_max_mb * 1024 * 1024


def is_address(text: str) -> bool:
    return bool(ADDRESS.match(text.strip()))


def configured() -> bool:
    return bool(os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD"))


def default_recipients() -> list:
    raw = os.environ.get("EMAIL_TO", "")
    return [a.strip() for a in raw.split(",") if is_address(a)]


def send_files(to: str, subject: str, body: str, paths) -> str:
    """Email the files to one address. Returns a short result message."""
    if not configured():
        raise RuntimeError("Email is not set up: add SMTP_USER and SMTP_PASSWORD to .env.")
    if not is_address(to):
        raise ValueError("That does not look like an email address.")

    user = os.environ["SMTP_USER"]
    msg = EmailMessage()
    msg["From"] = os.environ.get("EMAIL_FROM") or user
    msg["To"] = to.strip()
    msg["Subject"] = subject
    msg.set_content(body)

    attached, skipped, total = [], [], 0
    for path in map(Path, paths):
        size = path.stat().st_size
        if total + size > max_total_bytes():
            skipped.append(path.name)
            continue
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        msg.add_attachment(path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name)
        attached.append(path.name)
        total += size
    if not attached:
        raise RuntimeError("No files to send.")

    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=settings.get().smtp_timeout_s)
        else:
            server = smtplib.SMTP(host, port, timeout=settings.get().smtp_timeout_s)
        with server:
            if port != 465:
                server.starttls(context=ssl.create_default_context())
            server.login(user, os.environ["SMTP_PASSWORD"])
            server.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise RuntimeError("The email server rejected the login. Check SMTP_USER and SMTP_PASSWORD (Gmail needs an app password).") from None
    except (smtplib.SMTPException, OSError) as exc:
        raise RuntimeError(f"Could not send the email ({type(exc).__name__}).") from None

    result = f"Sent {len(attached)} file(s) to {to.strip()}."
    if skipped:
        result += f" Not attached because of the size limit: {', '.join(skipped)}."
    return result
