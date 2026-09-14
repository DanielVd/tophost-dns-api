from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from tophost_api.errors import (
    AmbiguousDomainError,
    DomainNotFoundError,
)
from tophost_api.models import (
    AuthStatus,
    DNSMutationResult,
    DNSRecord,
    DNSRecordCreate,
    DNSRecordPatch,
    OTPChallenge,
    TophostProduct,
)
from tophost_api.services.auth import AuthService
from tophost_api.services.dns import DNSService


def product(
    domain: str,
    product_id: str,
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
        default_factory=list
    )
    confirmed: tuple[str, str] | None = None

    def list_products(self) -> list[TophostProduct]:
        return self.products

    def auth_status(self) -> AuthStatus:
        return AuthStatus(
            credentials_configured=True,
            trusted_2fa_present=True,
            trusted_2fa_valid=True,
            trusted_2fa_expires=9999999999,
            otp_pending=False,
        )

    def request_otp(self) -> OTPChallenge:
        return OTPChallenge(
            challenge_id="challenge-123",
            status="pending",
        )

    def confirm_otp(
        self,
        *,
        challenge_id: str,
        code: str,
        trust_days: int = 90,
    ) -> int:
        assert trust_days == 90

        self.confirmed = (
            challenge_id,
            code,
        )

        return 9999999999


@dataclass
class FakeDNSClient:
    domain: str
    calls: list[tuple] = field(
        default_factory=list
    )

    def list_records(self) -> list[DNSRecord]:
        self.calls.append(
            ("list",)
        )

        return [
            DNSRecord(
                id="abc",
                name="www",
                type="A",
                value="192.0.2.10",
                priority=0,
            )
        ]

    def get_record(
        self,
        record_id: str,
    ) -> DNSRecord:
        self.calls.append(
            ("get", record_id)
        )

        return DNSRecord(
            id=record_id,
            name="www",
            type="A",
            value="192.0.2.10",
            priority=0,
        )

    def find_records(
        self,
        *,
        name=None,
        record_type=None,
        value=None,
    ) -> list[DNSRecord]:
        self.calls.append(
            (
                "find",
                name,
                record_type,
                value,
            )
        )

        return []

    def create_record(
        self,
        request: DNSRecordCreate,
    ) -> DNSMutationResult:
        self.calls.append(
            (
                "create",
                request.name,
                request.type,
                request.value,
            )
        )

        record = DNSRecord(
            id="created",
            name=request.name,
            type=request.type,
            value=request.value,
            priority=request.priority,
        )

        return DNSMutationResult(
            changed=True,
            before=None,
            after=record,
        )

    def patch_record(
        self,
        record_id: str,
        patch: DNSRecordPatch,
    ) -> DNSMutationResult:
        self.calls.append(
            (
                "patch",
                record_id,
                patch.value,
                patch.expected_value,
            )
        )

        before = DNSRecord(
            id=record_id,
            name="www",
            type="A",
            value="192.0.2.10",
            priority=0,
        )

        after = DNSRecord(
            id="new-id",
            name="www",
            type="A",
            value=patch.value or before.value,
            priority=0,
        )

        return DNSMutationResult(
            changed=True,
            before=before,
            after=after,
        )

    def delete_record(
        self,
        record_id: str,
        *,
        expected_value=None,
        expected_priority=None,
    ) -> DNSMutationResult:
        self.calls.append(
            (
                "delete",
                record_id,
                expected_value,
                expected_priority,
            )
        )

        before = DNSRecord(
            id=record_id,
            name="www",
            type="A",
            value="192.0.2.10",
            priority=0,
        )

        return DNSMutationResult(
            changed=True,
            before=before,
            after=None,
        )


def test_auth_service():
    account = FakeAccount()

    service = AuthService(
        account=account,  # type: ignore[arg-type]
    )

    challenge = service.request_otp()

    assert challenge.challenge_id == "challenge-123"

    status = service.verify_otp(
        challenge_id="challenge-123",
        code="123456",
    )

    assert account.confirmed == (
        "challenge-123",
        "123456",
    )
    assert status.trusted_2fa_valid is True


def test_list_domains_hides_product_ids():
    account = FakeAccount(
        products=[
            product("beta.it", "222"),
            product("alpha.it", "111"),
        ]
    )

    service = DNSService(
        account=account,  # type: ignore[arg-type]
        default_domain="beta.it",
    )

    domains = service.list_domains()

    assert [item.name for item in domains] == [
        "alpha.it",
        "beta.it",
    ]

    assert domains[0].is_default is False
    assert domains[1].is_default is True

    assert "product_id" not in type(domains[0]).model_fields


def test_single_domain_is_implicit_default():
    account = FakeAccount(
        products=[
            product("example.com", "123"),
        ]
    )

    service = DNSService(
        account=account,  # type: ignore[arg-type]
    )

    assert service.resolve_domain(None) == "example.com"


def test_multiple_domains_require_explicit_domain():
    account = FakeAccount(
        products=[
            product("alpha.it", "111"),
            product("beta.it", "222"),
        ]
    )

    service = DNSService(
        account=account,  # type: ignore[arg-type]
    )

    with pytest.raises(AmbiguousDomainError):
        service.resolve_domain(None)


def test_missing_configured_default_is_rejected():
    account = FakeAccount(
        products=[
            product("alpha.it", "111"),
        ]
    )

    service = DNSService(
        account=account,  # type: ignore[arg-type]
        default_domain="missing.it",
    )

    with pytest.raises(DomainNotFoundError):
        service.resolve_domain(None)


def test_explicit_domain_is_normalized_without_discovery():
    account = FakeAccount()

    service = DNSService(
        account=account,  # type: ignore[arg-type]
    )

    assert (
        service.resolve_domain(" Example.COM. ")
        == "example.com"
    )


def test_dns_read_is_delegated_to_selected_domain():
    account = FakeAccount()

    clients: dict[str, FakeDNSClient] = {}

    def factory(domain: str):
        client = FakeDNSClient(
            domain=domain
        )
        clients[domain] = client
        return client

    service = DNSService(
        account=account,  # type: ignore[arg-type]
        client_factory=factory,  # type: ignore[arg-type]
    )

    records = service.list_records(
        domain="example.com"
    )

    assert records[0].name == "www"
    assert clients["example.com"].calls == [
        ("list",)
    ]


def test_dns_patch_preserves_optimistic_concurrency():
    account = FakeAccount()

    clients: dict[str, FakeDNSClient] = {}

    def factory(domain: str):
        client = FakeDNSClient(
            domain=domain
        )
        clients[domain] = client
        return client

    service = DNSService(
        account=account,  # type: ignore[arg-type]
        client_factory=factory,  # type: ignore[arg-type]
    )

    result = service.patch_record(
        "old-id",
        DNSRecordPatch(
            value="192.0.2.11",
            expected_value="192.0.2.10",
        ),
        domain="example.com",
    )

    assert result.changed is True

    assert clients["example.com"].calls == [
        (
            "patch",
            "old-id",
            "192.0.2.11",
            "192.0.2.10",
        )
    ]


def test_dns_delete_preserves_expected_state():
    account = FakeAccount()

    clients: dict[str, FakeDNSClient] = {}

    def factory(domain: str):
        client = FakeDNSClient(
            domain=domain
        )
        clients[domain] = client
        return client

    service = DNSService(
        account=account,  # type: ignore[arg-type]
        client_factory=factory,  # type: ignore[arg-type]
    )

    service.delete_record(
        "abc",
        domain="example.com",
        expected_value="192.0.2.10",
        expected_priority=0,
    )

    assert clients["example.com"].calls == [
        (
            "delete",
            "abc",
            "192.0.2.10",
            0,
        )
    ]
