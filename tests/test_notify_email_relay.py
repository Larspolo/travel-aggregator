"""The self-hosted mail relay of the preview (#525): SMTP_STARTTLS=false sends with no STARTTLS."""

from pathlib import Path

import yaml

from app import notify

ROOT = Path(__file__).resolve().parent.parent


class Fake:
    calls: list = []

    def __init__(self, host, port, timeout=None):
        Fake.calls.append(("open", host, port))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        Fake.calls.append(("starttls",))

    def login(self, user, password):
        Fake.calls.append(("login",))

    def send_message(self, mail):
        Fake.calls.append(("send", mail["To"]))


def _send(monkeypatch, starttls):
    Fake.calls = []
    monkeypatch.setattr(notify.smtplib, "SMTP", Fake)
    monkeypatch.setenv("SMTP_HOST", "mail")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "")
    monkeypatch.setenv("SMTP_FROM", "notify@example.org")
    if starttls is None:
        monkeypatch.delenv("SMTP_STARTTLS", raising=False)
    else:
        monkeypatch.setenv("SMTP_STARTTLS", starttls)
    m = notify.Message(channel="email", title="Price drop: x", text="t", click="https://x/trips/1", url="owner@example.org")
    notify.send_email(m)
    return [c[0] for c in Fake.calls]


def test_starttls_is_the_default(monkeypatch):
    assert _send(monkeypatch, None) == ["open", "starttls", "send"]


def test_starttls_false_sends_with_no_tls(monkeypatch):
    assert _send(monkeypatch, "false") == ["open", "send"]


def test_the_preview_has_an_internal_mail_relay():
    compose = yaml.safe_load((ROOT / "deploy/preview/docker-compose.yml").read_text(encoding="utf-8"))
    mail = compose["services"]["mail"]
    assert "ports" not in mail and "networks" not in mail
    assert "com.centurylinklabs.watchtower.scope=travel-preview" in mail["labels"]
    env = (ROOT / "deploy/preview/.env.example").read_text(encoding="utf-8")
    assert "SMTP_STARTTLS=" in env
