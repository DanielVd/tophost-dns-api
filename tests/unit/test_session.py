import pytest
import requests

from tophost_api.client.session import TophostHTTPSession
from tophost_api.errors import UpstreamUnavailableError


def test_cookie_roundtrip():
    source = TophostHTTPSession()

    source.session.cookies.set(
        "example",
        "secret",
        domain=".tophost.it",
        path="/",
    )

    exported = source.export_cookies()

    target = TophostHTTPSession()
    target.import_cookies(exported)

    assert target.session.cookies.get(
        "example",
        domain=".tophost.it",
        path="/",
    ) == "secret"


def test_request_classifies_timeout(monkeypatch):
    client = TophostHTTPSession()

    def fail(*args, **kwargs):
        raise requests.Timeout("details must not leak")

    monkeypatch.setattr(
        client.session,
        "request",
        fail,
    )

    with pytest.raises(UpstreamUnavailableError) as exc_info:
        client.get("https://www.tophost.it/")

    assert exc_info.value.reason == "timeout"
    assert "details must not leak" not in str(exc_info.value)


def test_request_classifies_connection_error(monkeypatch):
    client = TophostHTTPSession()

    def fail(*args, **kwargs):
        raise requests.ConnectionError("details must not leak")

    monkeypatch.setattr(
        client.session,
        "request",
        fail,
    )

    with pytest.raises(UpstreamUnavailableError) as exc_info:
        client.get("https://www.tophost.it/")

    assert exc_info.value.reason == "connection_error"
    assert "details must not leak" not in str(exc_info.value)
