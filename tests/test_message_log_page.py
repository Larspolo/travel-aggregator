"""The last messages on the messages settings page (#1813): the newest 50 rows, the failed ones with a text mark."""

from datetime import UTC, datetime, timedelta

from app.models import SentMessage
from tests.test_settings_page import client as login_client  # noqa: F401  (a fixture)

BASE = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)


def _row(sessions, title, minutes, ok=True, reason=None, click=""):
    with sessions() as s:
        s.add(SentMessage(title=title, click=click, channel="ntfy", ok=ok, reason=reason,
                          sent_at=BASE + timedelta(minutes=minutes)))
        s.commit()


def test_a_sent_and_a_failed_row_show_their_result_and_the_failed_one_is_first(login_client, sessions):  # noqa: F811
    _row(sessions, "Price drop Amsterdam", 0, click="https://travel.example/trips/1")
    _row(sessions, "Price drop Wien", 5, ok=False, reason="ntfy HTTP 404")
    page = login_client.get("/settings/messages").text
    assert "Price drop Amsterdam" in page and "Price drop Wien" in page
    assert "failed: ntfy HTTP 404" in page
    assert page.count(">sent<") == 1
    assert page.index("Price drop Wien") < page.index("Price drop Amsterdam")


def test_a_failed_row_has_a_text_mark_and_a_title_link_only_for_the_app(login_client, sessions):  # noqa: F811
    _row(sessions, "Own link", 0, click="http://testserver/settings/messages")
    _row(sessions, "Foreign link", 1, click="https://evil.example/x")
    page = login_client.get("/settings/messages").text
    assert 'href="http://testserver/settings/messages"' in page
    assert 'href="https://evil.example/x"' not in page


def test_no_row_shows_no_messages_sent_yet(login_client):  # noqa: F811
    assert "No messages sent yet" in login_client.get("/settings/messages").text


def test_the_page_shows_at_most_50_rows(login_client, sessions):  # noqa: F811
    for i in range(55):
        _row(sessions, f"Row-{i:02d}", i)
    page = login_client.get("/settings/messages").text
    assert page.count("Row-") == 50
    assert "Row-54" in page and "Row-04" not in page
