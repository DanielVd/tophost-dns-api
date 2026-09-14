from __future__ import annotations

from dataclasses import dataclass

from fastapi.testclient import TestClient

from tophost_api.api.app import create_app
from tophost_api.api.dependencies import (
    get_auth_service,
    get_dns_service,
    get_settings,
)
from tophost_api.config import Settings
from tophost_api.errors import RecordChangedError, RecordNotFoundError
from tophost_api.models import (
    AuthStatus,
    DNSMutationResult,
    DNSRecord,
    DomainInfo,
)


@dataclass
class FakeAuthService:
    verified: tuple[str, str] | None = None

    def status(self) -> AuthStatus:
        return AuthStatus(
            credentials_configured=True,
            trusted_2fa_present=True,
            trusted_2fa_valid=True,
            trusted_2fa_expires=9999999999,
            otp_pending=False,
        )

    def request_otp(self):
        from tophost_api.models import OTPChallenge

        return OTPChallenge(
            challenge_id="challenge-123",
            status="pending",
        )

    def verify_otp(
        self,
        *,
        challenge_id: str,
        code: str,
    ) -> AuthStatus:
        self.verified = (
            challenge_id,
            code,
        )

        return self.status()


@dataclass
class FakeDNSService:
    def list_domains(self) -> list[DomainInfo]:
        return [
            DomainInfo(
                name="alpha.it",
                is_default=False,
            ),
            DomainInfo(
                name="example.com",
                is_default=True,
            ),
        ]

    def list_records(
        self,
        *,
        domain=None,
    ) -> list[DNSRecord]:
        assert domain == "example.com"

        return [
            DNSRecord(
                id="abc123",
                name="www",
                type="A",
                value="192.0.2.10",
                priority=0,
            )
        ]

    def find_records(
        self,
        *,
        domain=None,
        name=None,
        record_type=None,
        value=None,
    ) -> list[DNSRecord]:
        assert domain == "example.com"
        assert name == "www"
        assert record_type == "A"
        assert value is None

        return [
            DNSRecord(
                id="abc123",
                name="www",
                type="A",
                value="192.0.2.10",
                priority=0,
            )
        ]

    def get_record(
        self,
        record_id,
        *,
        domain=None,
    ) -> DNSRecord:
        assert domain == "example.com"

        if record_id == "missing":
            raise RecordNotFoundError(
                "DNS record not found"
            )

        return DNSRecord(
            id=record_id,
            name="www",
            type="A",
            value="192.0.2.10",
            priority=0,
        )


    def create_record(
        self,
        request,
        *,
        domain=None,
    ) -> DNSMutationResult:
        assert domain == "example.com"

        record = DNSRecord(
            id="created-id",
            name=request.name,
            type=request.type,
            value=request.value,
            priority=request.priority,
        )

        return DNSMutationResult(
            changed=True,
            before=None,
            after=record,
            dns_serial="2026091401",
            message="created",
        )

    def patch_record(
        self,
        record_id,
        patch,
        *,
        domain=None,
    ) -> DNSMutationResult:
        assert domain == "example.com"

        if patch.expected_value == "stale":
            raise RecordChangedError(
                "DNS record value changed since it was read"
            )

        before = DNSRecord(
            id=record_id,
            name="www",
            type="A",
            value="192.0.2.10",
            priority=0,
        )

        after = DNSRecord(
            id="changed-id",
            name="www",
            type="A",
            value=patch.value or before.value,
            priority=(
                patch.priority
                if patch.priority is not None
                else before.priority
            ),
        )

        return DNSMutationResult(
            changed=True,
            before=before,
            after=after,
            dns_serial="2026091402",
            message="updated",
        )

    def delete_record(
        self,
        record_id,
        *,
        domain=None,
        expected_value=None,
        expected_priority=None,
    ) -> DNSMutationResult:
        assert domain == "example.com"
        assert expected_value == "192.0.2.11"
        assert expected_priority == 0

        before = DNSRecord(
            id=record_id,
            name="www",
            type="A",
            value="192.0.2.11",
            priority=0,
        )

        return DNSMutationResult(
            changed=True,
            before=before,
            after=None,
            dns_serial="2026091403",
            message="deleted",
        )


def fake_settings() -> Settings:
    return Settings(
        username="user@example.com",
        password="secret",
        api_key="test-api-key",
        default_domain=None,
        state_dir="/tmp/tophost-api-test",
    )


def make_client() -> TestClient:
    app = create_app()

    app.dependency_overrides[
        get_settings
    ] = fake_settings

    app.dependency_overrides[
        get_auth_service
    ] = lambda: FakeAuthService()

    app.dependency_overrides[
        get_dns_service
    ] = lambda: FakeDNSService()

    return TestClient(app)


def auth_headers() -> dict[str, str]:
    return {
        "X-API-Key": "test-api-key"
    }


def test_health_is_public():
    client = make_client()

    response = client.get(
        "/health"
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok"
    }


def test_v1_requires_api_key():
    client = make_client()

    response = client.get(
        "/v1/domains"
    )

    assert response.status_code == 401


def test_v1_rejects_wrong_api_key():
    client = make_client()

    response = client.get(
        "/v1/domains",
        headers={
            "X-API-Key": "wrong"
        },
    )

    assert response.status_code == 401


def test_auth_status():
    client = make_client()

    response = client.get(
        "/v1/auth/status",
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert response.json()[
        "trusted_2fa_valid"
    ] is True


def test_list_domains_does_not_expose_product_id():
    client = make_client()

    response = client.get(
        "/v1/domains",
        headers=auth_headers(),
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload == [
        {
            "name": "alpha.it",
            "is_default": False,
        },
        {
            "name": "example.com",
            "is_default": True,
        },
    ]

    assert all(
        "product_id" not in item
        for item in payload
    )


def test_list_dns_records():
    client = make_client()

    response = client.get(
        "/v1/domains/example.com/dns/records",
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert response.json()[0]["id"] == "abc123"


def test_filter_dns_records():
    client = make_client()

    response = client.get(
        (
            "/v1/domains/example.com/dns/records"
            "?name=www&type=A"
        ),
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_dns_record():
    client = make_client()

    response = client.get(
        "/v1/domains/example.com/dns/records/abc123",
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert response.json()["id"] == "abc123"


def test_not_found_becomes_structured_404():
    client = make_client()

    response = client.get(
        "/v1/domains/example.com/dns/records/missing",
        headers=auth_headers(),
    )

    assert response.status_code == 404

    payload = response.json()

    assert payload["error"]["code"] == "RECORD_NOT_FOUND"
    assert payload["error"]["retryable"] is False


def test_create_dns_record():
    client = make_client()

    response = client.post(
        "/v1/domains/example.com/dns/records",
        headers=auth_headers(),
        json={
            "name": "test",
            "type": "A",
            "value": "192.0.2.10",
            "priority": 0,
        },
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["changed"] is True
    assert payload["before"] is None
    assert payload["after"]["id"] == "created-id"
    assert payload["after"]["name"] == "test"
    assert payload["dns_serial"] == "2026091401"


def test_patch_dns_record():
    client = make_client()

    response = client.patch(
        "/v1/domains/example.com/dns/records/old-id",
        headers=auth_headers(),
        json={
            "value": "192.0.2.11",
            "expected_value": "192.0.2.10",
        },
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["changed"] is True
    assert payload["before"]["id"] == "old-id"
    assert payload["after"]["id"] == "changed-id"
    assert payload["after"]["value"] == "192.0.2.11"


def test_patch_stale_record_becomes_structured_409():
    client = make_client()

    response = client.patch(
        "/v1/domains/example.com/dns/records/old-id",
        headers=auth_headers(),
        json={
            "value": "192.0.2.11",
            "expected_value": "stale",
        },
    )

    assert response.status_code == 409

    payload = response.json()

    assert payload["error"]["code"] == "RECORD_CHANGED"
    assert payload["error"]["retryable"] is False


def test_delete_dns_record():
    client = make_client()

    response = client.delete(
        (
            "/v1/domains/example.com/dns/records/changed-id"
            "?expected_value=192.0.2.11"
            "&expected_priority=0"
        ),
        headers=auth_headers(),
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["changed"] is True
    assert payload["before"]["id"] == "changed-id"
    assert payload["after"] is None
    assert payload["dns_serial"] == "2026091403"


def test_request_otp():
    client = make_client()

    response = client.post(
        "/v1/auth/otp",
        headers=auth_headers(),
    )

    assert response.status_code == 202

    assert response.json() == {
        "challenge_id": "challenge-123",
        "status": "pending",
    }


def test_verify_otp():
    client = make_client()

    response = client.post(
        "/v1/auth/otp/challenge-123/verify",
        headers=auth_headers(),
        json={
            "code": "123456",
        },
    )

    assert response.status_code == 200
    assert response.json()["trusted_2fa_valid"] is True
