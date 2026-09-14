import os
import time

import pytest

from tophost_api.client.auth import TophostAccountClient
from tophost_api.client.dns import TophostDNSClient
from tophost_api.config import Settings
from tophost_api.models import DNSRecordCreate, DNSRecordPatch

pytestmark = pytest.mark.integration


def mutation_tests_enabled() -> bool:
    return os.getenv("TOPHOST_RUN_MUTATION_TESTS") == "1"


@pytest.mark.skipif(
    not mutation_tests_enabled(),
    reason="real DNS mutation tests are disabled",
)
def test_real_dns_crud():
    settings = Settings()

    if settings.default_domain is None:
        pytest.fail(
            "TOPHOST_DEFAULT_DOMAIN is required "
            "for the real mutation integration test"
        )

    account = TophostAccountClient(
        username=settings.username,
        password=settings.password.get_secret_value(),
        trust_file=settings.trust_file,
        otp_session_file=settings.otp_session_file,
        timeout=settings.request_timeout,
    )

    dns = TophostDNSClient(
        account=account,
        domain=settings.default_domain,
    )

    name = f"tophost-api-test-{int(time.time())}"

    # RFC 5737 TEST-NET-1 addresses.
    initial_value = "192.0.2.10"
    updated_value = "192.0.2.11"

    current_id = None

    try:
        print()
        print("=== CREATE ===")

        created = dns.create_record(
            DNSRecordCreate(
                name=name,
                type="A",
                value=initial_value,
            )
        )

        assert created.changed is True
        assert created.after is not None
        assert created.after.name == name
        assert created.after.value == initial_value

        current_id = created.after.id

        print(
            f"{created.after.name} "
            f"{created.after.type} "
            f"{created.after.value} "
            f"id={current_id}"
        )

        print()
        print("=== READ ===")

        read = dns.get_record(current_id)

        assert read.name == name
        assert read.value == initial_value

        print(
            f"{read.name} "
            f"{read.type} "
            f"{read.value} "
            f"id={read.id}"
        )

        print()
        print("=== UPDATE ===")

        updated = dns.patch_record(
            current_id,
            DNSRecordPatch(
                value=updated_value,
                expected_value=initial_value,
            ),
        )

        assert updated.changed is True
        assert updated.before is not None
        assert updated.after is not None
        assert updated.before.id == current_id
        assert updated.after.value == updated_value

        # Tophost record IDs can change when record contents change.
        current_id = updated.after.id

        print(
            f"{updated.after.name} "
            f"{updated.after.type} "
            f"{updated.after.value} "
            f"id={current_id}"
        )

        print()
        print("=== READ UPDATED ===")

        reread = dns.get_record(current_id)

        assert reread.value == updated_value

        print(
            f"{reread.name} "
            f"{reread.type} "
            f"{reread.value} "
            f"id={reread.id}"
        )

        print()
        print("=== DELETE ===")

        deleted = dns.delete_record(
            current_id,
            expected_value=updated_value,
        )

        assert deleted.changed is True
        assert deleted.before is not None
        assert deleted.after is None

        current_id = None

        print("deleted")

        print()
        print("=== VERIFY ABSENT ===")

        remaining = dns.find_records(
            name=name,
            record_type="A",
        )

        assert remaining == []

        print("absent")
        print()
        print("=== REAL CRUD OK ===")

    finally:
        # Best-effort cleanup if the test fails after create/update.
        if current_id is not None:
            try:
                record = dns.get_record(current_id)
                dns.delete_record(
                    current_id,
                    expected_value=record.value,
                    expected_priority=record.priority,
                )
                print()
                print("=== CLEANUP OK ===")
            except Exception as exc:  # noqa: BLE001  # noqa: BLE001
                print()
                print(
                    "WARNING: automatic cleanup failed: "
                    f"{exc}"
                )
