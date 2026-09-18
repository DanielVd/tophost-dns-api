from dataclasses import dataclass, field

import pytest

from tophost_api.canary import (
    CanaryExit,
    CanaryStatus,
    run_canary,
)
from tophost_api.errors import (
    AuthenticationError,
    OTPRequiredError,
    UpstreamProtocolError,
    UpstreamUnavailableError,
)
from tophost_api.models import TophostProduct


def product(
    domain: str = "example.com",
    product_id: str = "123",
) -> TophostProduct:
    return TophostProduct(
        domain=domain,
        product_id=product_id,
        control_panel_href=(
            "https://www.tophost.it/myth/"
            f"index_th.php?func=dd{product_id}"
        ),
    )


@dataclass
class FakeAccount:
    products: list[TophostProduct] = field(
        default_factory=lambda: [product()]
    )
    error: Exception | None = None

    def list_products(self) -> list[TophostProduct]:
        if self.error is not None:
            raise self.error

        return self.products


@dataclass
class FakeDNSClient:
    connect_error: Exception | None = None
    list_error: Exception | None = None
    records: list[object] = field(
        default_factory=lambda: [object()]
    )
    connected_product: TophostProduct | None = None

    def connect(
        self,
        *,
        product: TophostProduct | None = None,
    ) -> TophostProduct:
        if self.connect_error is not None:
            raise self.connect_error

        assert product is not None
        self.connected_product = product
        return product

    def list_records(self) -> list[object]:
        if self.list_error is not None:
            raise self.list_error

        return self.records


def dns_factory(
    dns: FakeDNSClient,
):
    def factory(account, domain):
        assert domain.endswith(".com")
        return dns

    return factory


def test_canary_is_compatible_for_expected_domain():
    account = FakeAccount(
        products=[
            product("example.com", "111"),
            product("other.com", "222"),
        ]
    )
    dns = FakeDNSClient(
        records=[object(), object()]
    )

    result = run_canary(
        account=account,  # type: ignore[arg-type]
        default_domain="example.com",
        dns_client_factory=dns_factory(dns),
    )

    assert result.status == CanaryStatus.COMPATIBLE
    assert result.exit_code == CanaryExit.COMPATIBLE
    assert result.stage == "complete"
    assert result.product_count == 2
    assert result.record_count == 2
    assert dns.connected_product is not None
    assert dns.connected_product.domain == "example.com"


def test_canary_uses_single_discovered_domain():
    dns = FakeDNSClient()

    result = run_canary(
        account=FakeAccount(),  # type: ignore[arg-type]
        default_domain=None,
        dns_client_factory=dns_factory(dns),
    )

    assert result.status == CanaryStatus.COMPATIBLE


def test_canary_requires_default_for_multiple_domains():
    result = run_canary(
        account=FakeAccount(
            products=[
                product("alpha.com", "111"),
                product("beta.com", "222"),
            ]
        ),  # type: ignore[arg-type]
        default_domain=None,
    )

    assert result.status == CanaryStatus.ATTENTION
    assert result.exit_code == CanaryExit.ATTENTION
    assert result.reason == "default_domain_required"


def test_canary_rejects_missing_configured_domain():
    result = run_canary(
        account=FakeAccount(),  # type: ignore[arg-type]
        default_domain="missing.com",
    )

    assert result.status == CanaryStatus.ATTENTION
    assert result.reason == "configured_domain_missing"


def test_canary_flags_empty_product_parse_as_drift():
    result = run_canary(
        account=FakeAccount(
            products=[]
        ),  # type: ignore[arg-type]
        default_domain=None,
    )

    assert result.status == CanaryStatus.DRIFT
    assert result.exit_code == CanaryExit.DRIFT
    assert result.stage == "products"
    assert result.reason == "no_products_parsed"


@pytest.mark.parametrize(
    ("error", "status", "exit_code", "reason"),
    [
        (
            UpstreamUnavailableError(
                "temporary",
                reason="timeout",
            ),
            CanaryStatus.TRANSIENT,
            CanaryExit.TRANSIENT,
            "timeout",
        ),
        (
            OTPRequiredError("otp"),
            CanaryStatus.ATTENTION,
            CanaryExit.ATTENTION,
            "otp_required",
        ),
        (
            AuthenticationError("auth"),
            CanaryStatus.ATTENTION,
            CanaryExit.ATTENTION,
            "authentication_failed",
        ),
        (
            UpstreamProtocolError("changed"),
            CanaryStatus.DRIFT,
            CanaryExit.DRIFT,
            "upstream_protocol_changed",
        ),
    ],
)
def test_canary_classifies_product_errors(
    error,
    status,
    exit_code,
    reason,
):
    result = run_canary(
        account=FakeAccount(
            error=error
        ),  # type: ignore[arg-type]
        default_domain="example.com",
    )

    assert result.status == status
    assert result.exit_code == exit_code
    assert result.reason == reason


def test_canary_flags_sso_protocol_change():
    dns = FakeDNSClient(
        connect_error=UpstreamProtocolError(
            "changed"
        )
    )

    result = run_canary(
        account=FakeAccount(),  # type: ignore[arg-type]
        default_domain="example.com",
        dns_client_factory=dns_factory(dns),
    )

    assert result.status == CanaryStatus.DRIFT
    assert result.stage == "sso"


def test_canary_flags_dns_protocol_change():
    dns = FakeDNSClient(
        list_error=UpstreamProtocolError(
            "changed"
        )
    )

    result = run_canary(
        account=FakeAccount(),  # type: ignore[arg-type]
        default_domain="example.com",
        dns_client_factory=dns_factory(dns),
    )

    assert result.status == CanaryStatus.DRIFT
    assert result.stage == "dns"


def test_canary_flags_empty_dns_parse_as_drift():
    dns = FakeDNSClient(
        records=[]
    )

    result = run_canary(
        account=FakeAccount(),  # type: ignore[arg-type]
        default_domain="example.com",
        dns_client_factory=dns_factory(dns),
    )

    assert result.status == CanaryStatus.DRIFT
    assert result.reason == "no_dns_records_parsed"


def test_canary_can_allow_empty_dns_zone():
    dns = FakeDNSClient(
        records=[]
    )

    result = run_canary(
        account=FakeAccount(),  # type: ignore[arg-type]
        default_domain="example.com",
        require_records=False,
        dns_client_factory=dns_factory(dns),
    )

    assert result.status == CanaryStatus.COMPATIBLE
    assert result.record_count == 0
