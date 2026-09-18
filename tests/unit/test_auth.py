import time
from pathlib import Path

import pytest
import responses

from tophost_api.client.auth import (
    LOGIN_AJAX_URL,
    LOGIN_URL,
    MYTH_URL,
    OTP_URL,
    PRODUCTS_URL,
    TophostAccountClient,
)
from tophost_api.client.state import SecureStateStore
from tophost_api.errors import OTPRequiredError, UpstreamUnavailableError


def make_client(tmp_path: Path) -> TophostAccountClient:
    return TophostAccountClient(
        username="user@example.com",
        password="secret",
        trust_file=tmp_path / "2fa.json",
        otp_session_file=tmp_path / "otp-session.json",
    )


def mock_primary_login():
    responses.get(
        LOGIN_URL,
        body=(
            '<html><head>'
            '<meta name="csrf_token" content="csrf123">'
            '</head></html>'
        ),
        status=200,
    )

    responses.post(
        LOGIN_AJAX_URL,
        json={
            "uid": "123",
            "nome": "Test User",
            "url": "/myth/",
        },
        status=200,
    )


@responses.activate
def test_authenticate_with_trusted_cookie(tmp_path: Path):
    client = make_client(tmp_path)

    SecureStateStore.write(
        client.trust_file,
        {
            "name": "th_2auth123",
            "value": "trusted",
            "domain": ".tophost.it",
            "path": "/",
            "secure": True,
            "expires": int(time.time()) + 3600,
        },
    )

    mock_primary_login()

    responses.get(
        MYTH_URL,
        status=302,
        headers={
            "Location": "/myth/rinnova"
        },
    )

    client.authenticate()

    assert client.auth_status().trusted_2fa_valid is True


@responses.activate
def test_authenticate_requires_otp_without_trust(
    tmp_path: Path,
):
    client = make_client(tmp_path)

    mock_primary_login()

    responses.get(
        MYTH_URL,
        status=302,
        headers={
            "Location": "/myth/2fa"
        },
    )

    with pytest.raises(OTPRequiredError):
        client.authenticate()


@responses.activate
def test_request_otp_persists_challenge(tmp_path: Path):
    client = make_client(tmp_path)

    mock_primary_login()

    responses.get(
        MYTH_URL,
        status=302,
        headers={
            "Location": "/myth/2fa"
        },
    )

    responses.get(
        OTP_URL,
        body="<html>OTP</html>",
        status=200,
    )

    challenge = client.request_otp()

    state = SecureStateStore.read(
        client.otp_session_file
    )

    assert challenge.status == "pending"
    assert state is not None
    assert state["challenge_id"] == challenge.challenge_id


@responses.activate
def test_product_discovery_uses_authenticated_page(
    tmp_path: Path,
):
    client = make_client(tmp_path)

    SecureStateStore.write(
        client.trust_file,
        {
            "name": "th_2auth123",
            "value": "trusted",
            "domain": ".tophost.it",
            "path": "/",
            "secure": True,
            "expires": int(time.time()) + 3600,
        },
    )

    mock_primary_login()

    responses.get(
        MYTH_URL,
        status=302,
        headers={
            "Location": "/myth/rinnova"
        },
    )

    responses.get(
        PRODUCTS_URL,
        body="""
        <section>
          <span>example.com</span>
          <a href="index_th.php?func=dd123456">
            CP
          </a>
        </section>
        """,
        status=200,
    )

    products = client.list_products()

    assert len(products) == 1
    assert products[0].domain == "example.com"
    assert products[0].product_id == "123456"

@responses.activate
def test_authenticate_treats_server_error_as_unavailable(
    tmp_path: Path,
):
    client = make_client(tmp_path)

    responses.get(
        LOGIN_URL,
        status=503,
    )

    with pytest.raises(UpstreamUnavailableError):
        client.authenticate()
