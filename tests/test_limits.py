"""Limits that spec.md §6 promises but the code does not enforce yet. Each is skipped until its ticket lands;
removing the skip is the first step of that ticket (practice.md)."""
import pytest


@pytest.mark.skip(reason="ticket #11: daily spend cap and per-job token ceiling")
def test_daily_cap():
    """spec.md check 12: after $3 in a day a new job is refused with 'back tomorrow'; one job stops at 150,000 input tokens."""


@pytest.mark.skip(reason="ticket #12: 30 messages per hour per chat id")
def test_message_rate_limit():
    """The 31st message within an hour from one chat gets a polite refusal that says when to retry."""


@pytest.mark.skip(reason="ticket #13: retry the model on 429 and 5xx with 2 s, 8 s, 30 s waits")
def test_retry_backoff():
    """A rate-limited model call is retried three times; the teacher never sees a raw 429."""
