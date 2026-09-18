import errno
import socket

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


@pytest.mark.parametrize(
    ("upstream_exception", "reason"),
    [
        (
            requests.ConnectTimeout("details must not leak"),
            "connect_timeout",
        ),
        (
            requests.ReadTimeout("details must not leak"),
            "read_timeout",
        ),
        (
            requests.Timeout("details must not leak"),
            "timeout",
        ),
        (
            requests.SSLError("details must not leak"),
            "tls_error",
        ),
        (
            requests.ConnectionError(
                socket.gaierror(
                    socket.EAI_NONAME,
                    "details must not leak",
                )
            ),
            "dns_resolution_error",
        ),
        (
            requests.ConnectionError(
                ConnectionRefusedError(
                    errno.ECONNREFUSED,
                    "details must not leak",
                )
            ),
            "connection_refused",
        ),
        (
            requests.ConnectionError(
                ConnectionResetError(
                    errno.ECONNRESET,
                    "details must not leak",
                )
            ),
            "connection_reset",
        ),
        (
            requests.ConnectionError("details must not leak"),
            "connection_error",
        ),
    ],
)
def test_request_classifies_transport_error(
    monkeypatch,
    upstream_exception,
    reason,
):
    client = TophostHTTPSession()

    def fail(*args, **kwargs):
        raise upstream_exception

    monkeypatch.setattr(
        client.session,
        "request",
        fail,
    )

    with pytest.raises(UpstreamUnavailableError) as exc_info:
        client.get("https://www.tophost.it/")

    assert exc_info.value.reason == reason
    assert "details must not leak" not in str(exc_info.value)
