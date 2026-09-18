from dataclasses import dataclass

import pytest
import responses

from tophost_api.client.dns import (
    DNS_ADD_URL,
    DNS_DEL_URL,
    DNS_MOD_URL,
    DNS_URL,
    DNSPageParser,
    TophostDNSClient,
)
from tophost_api.client.session import TophostHTTPSession
from tophost_api.errors import (
    RecordChangedError,
    UpstreamProtocolError,
    UpstreamUnavailableError,
)
from tophost_api.models import (
    DNSRecordCreate,
    DNSRecordPatch,
    TophostProduct,
)

RECORD_ID = "035083619812ceb35baa699bc71e746b"
NEW_RECORD_ID = "09c083e197f568dbc114ba332b6d0f35"


def dns_html(
    *,
    record_id: str = RECORD_ID,
    value: str = "192.0.2.10",
    priority: int = 0,
) -> str:
    return f"""
    <html>
      <body>
        <table>
          <tr id="tr-{record_id}">
            <input
              type="hidden"
              name="valueo-{record_id}"
              value="{value}"
            />
            <input
              type="hidden"
              name="priorityo-{record_id}"
              value="{priority}"
            />
            <td id="name-{record_id}">
              <span title="record originale">mcp</span>
            </td>
            <td id="type-{record_id}">A</td>
            <td id="value-{record_id}">{value}</td>
          </tr>
        </table>
      </body>
    </html>
    """


@dataclass
class FakeAccount:
    http: TophostHTTPSession

    def resolve_product(
        self,
        domain: str,
    ) -> TophostProduct:
        assert domain == "example.com"

        return TophostProduct(
            domain="example.com",
            product_id="1234567",
            control_panel_href=(
                "https://www.tophost.it/myth/"
                "index_th.php?func=dd1234567"
            ),
        )


def make_client() -> TophostDNSClient:
    account = FakeAccount(
        http=TophostHTTPSession()
    )

    return TophostDNSClient(
        account=account,  # type: ignore[arg-type]
        domain="example.com",
    )


def mock_sso():
    responses.get(
        "https://www.tophost.it/myth/"
        "index_th.php?func=dd1234567",
        status=302,
        headers={
            "Location": "https://cp.tophost.it/cplogin/token123",
        },
    )

    responses.get(
        "https://cp.tophost.it/cplogin/token123",
        status=302,
        headers={
            "Location": "/",
            "Set-Cookie": (
                "logged_cp=example.com; "
                "Path=/; Secure; HttpOnly"
            ),
        },
    )

    responses.get(
        "https://cp.tophost.it/",
        body="<html>Control panel</html>",
        status=200,
    )


def test_dns_page_parser():
    records = DNSPageParser().parse(
        dns_html()
    )

    assert len(records) == 1

    record = records[0]

    assert record.id == RECORD_ID
    assert record.name == "mcp"
    assert record.type == "A"
    assert record.value == "192.0.2.10"
    assert record.priority == 0


def test_dns_page_parser_rejects_partial_record():
    html = f"""
    <table>
      <tr id="tr-{RECORD_ID}">
        <td id="name-{RECORD_ID}">mcp</td>
        <td id="type-{RECORD_ID}">A</td>
      </tr>
    </table>
    """

    with pytest.raises(UpstreamProtocolError):
        DNSPageParser().parse(html)


@responses.activate
def test_connect_follows_sso():
    mock_sso()

    client = make_client()

    product = client.connect()

    assert client.connected is True
    assert product.domain == "example.com"
    assert product.product_id == "1234567"


@responses.activate
def test_connect_accepts_pre_resolved_product(monkeypatch):
    mock_sso()

    client = make_client()

    product = TophostProduct(
        domain="example.com",
        product_id="1234567",
        control_panel_href=(
            "https://www.tophost.it/myth/"
            "index_th.php?func=dd1234567"
        ),
    )

    monkeypatch.setattr(
        client.account,
        "resolve_product",
        lambda domain: pytest.fail(
            "resolve_product must not be called"
        ),
    )

    result = client.connect(
        product=product
    )

    assert result == product
    assert client.connected is True


@responses.activate
def test_connect_treats_server_error_as_unavailable():
    responses.get(
        "https://www.tophost.it/myth/"
        "index_th.php?func=dd1234567",
        status=503,
    )

    client = make_client()

    with pytest.raises(UpstreamUnavailableError):
        client.connect()


@responses.activate
def test_list_records():
    mock_sso()

    responses.get(
        DNS_URL,
        body=dns_html(),
        status=200,
    )

    client = make_client()

    records = client.list_records()

    assert len(records) == 1
    assert records[0].id == RECORD_ID


@responses.activate
def test_create_record():
    mock_sso()

    responses.get(
        DNS_URL,
        body="<html><table></table></html>",
        status=200,
    )

    responses.post(
        DNS_ADD_URL,
        json={
            "auth": 1,
            "record": "mcp A 192.0.2.10",
            "value": "192.0.2.10",
            "priority": 0,
            "recordnewid": RECORD_ID,
            "dns_serial": {
                "msg": "2026091401"
            },
            "msg": "Record DNS creato...",
        },
        status=200,
    )

    client = make_client()

    result = client.create_record(
        DNSRecordCreate(
            name="mcp",
            type="A",
            value="192.0.2.10",
        )
    )

    assert result.changed is True
    assert result.before is None
    assert result.after is not None
    assert result.after.id == RECORD_ID
    assert result.dns_serial == "2026091401"


@responses.activate
def test_create_existing_record_is_noop():
    mock_sso()

    responses.get(
        DNS_URL,
        body=dns_html(),
        status=200,
    )

    client = make_client()

    result = client.create_record(
        DNSRecordCreate(
            name="mcp",
            type="A",
            value="192.0.2.10",
        )
    )

    assert result.changed is False
    assert result.after is not None
    assert result.after.id == RECORD_ID


@responses.activate
def test_patch_record_returns_new_record_id():
    mock_sso()

    responses.get(
        DNS_URL,
        body=dns_html(),
        status=200,
    )

    responses.post(
        DNS_MOD_URL,
        json={
            "auth": 1,
            "record": "mcp A 192.0.2.11",
            "value": "192.0.2.11",
            "priority": 0,
            "recordnewid": NEW_RECORD_ID,
            "dns_serial": {
                "msg": "2026091402"
            },
            "msg": "Record DNS aggiornato...",
        },
        status=200,
    )

    client = make_client()

    result = client.patch_record(
        RECORD_ID,
        DNSRecordPatch(
            value="192.0.2.11",
            expected_value="192.0.2.10",
        ),
    )

    assert result.changed is True
    assert result.before is not None
    assert result.before.id == RECORD_ID

    assert result.after is not None
    assert result.after.id == NEW_RECORD_ID
    assert result.after.value == "192.0.2.11"


@responses.activate
def test_patch_rejects_stale_expected_value():
    mock_sso()

    responses.get(
        DNS_URL,
        body=dns_html(
            value="192.0.2.99"
        ),
        status=200,
    )

    client = make_client()

    with pytest.raises(RecordChangedError):
        client.patch_record(
            RECORD_ID,
            DNSRecordPatch(
                value="192.0.2.11",
                expected_value="192.0.2.10",
            ),
        )

    assert not any(
        call.request.url == DNS_MOD_URL
        for call in responses.calls
    )


@responses.activate
def test_delete_record():
    mock_sso()

    responses.get(
        DNS_URL,
        body=dns_html(),
        status=200,
    )

    responses.post(
        DNS_DEL_URL,
        json={
            "auth": 1,
            "dns_serial": {
                "msg": "2026091403"
            },
            "msg": "Record DNS eliminato...",
        },
        status=200,
    )

    client = make_client()

    result = client.delete_record(
        RECORD_ID,
        expected_value="192.0.2.10",
    )

    assert result.changed is True
    assert result.before is not None
    assert result.before.id == RECORD_ID
    assert result.after is None
    assert result.dns_serial == "2026091403"
