import os

import pytest

from tophost_api.client.auth import TophostAccountClient
from tophost_api.config import Settings
from tophost_api.services.dns import DNSService

pytestmark = pytest.mark.integration


def integration_enabled() -> bool:
    return os.getenv("TOPHOST_RUN_INTEGRATION_TESTS") == "1"


@pytest.mark.skipif(
    not integration_enabled(),
    reason="real Tophost integration tests are disabled",
)
def test_real_service_layer_read():
    settings = Settings()

    account = TophostAccountClient(
        username=settings.username,
        password=settings.password.get_secret_value(),
        trust_file=settings.trust_file,
        otp_session_file=settings.otp_session_file,
        timeout=settings.request_timeout,
    )

    service = DNSService(
        account=account,
        default_domain=settings.default_domain,
    )

    print()
    print("=== DOMAINS ===")

    domains = service.list_domains()

    assert domains

    for domain in domains:
        marker = " [default]" if domain.is_default else ""
        print(f"{domain.name}{marker}")

    resolved = service.resolve_domain(None)

    print()
    print("=== RESOLVED DOMAIN ===")
    print(resolved)

    print()
    print("=== DNS RECORDS ===")

    records = service.list_records(
        domain=resolved,
    )

    assert records

    print(f"records={len(records)}")

    for record in records:
        print(
            f"{record.name:<24} "
            f"{record.type:<6} "
            f"{record.value} "
            f"priority={record.priority}"
        )

    print()
    print("=== SERVICE LAYER REAL READ OK ===")
