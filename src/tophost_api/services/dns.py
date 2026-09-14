from __future__ import annotations

from collections.abc import Callable

from tophost_api.client.auth import TophostAccountClient
from tophost_api.client.dns import TophostDNSClient
from tophost_api.config import normalize_domain
from tophost_api.errors import (
    AmbiguousDomainError,
    DomainNotFoundError,
)
from tophost_api.models import (
    DNSMutationResult,
    DNSRecord,
    DNSRecordCreate,
    DNSRecordPatch,
    DomainInfo,
)

DNSClientFactory = Callable[[str], TophostDNSClient]


class DNSService:
    """Application-level DNS operations.

    The service exposes domains and DNS resources while hiding Tophost
    product IDs, control-panel SSO, cookies and HTML parsing.
    """

    def __init__(
        self,
        *,
        account: TophostAccountClient,
        default_domain: str | None = None,
        client_factory: DNSClientFactory | None = None,
    ):
        self.account = account
        self.default_domain = (
            normalize_domain(default_domain)
            if default_domain is not None
            else None
        )

        self.client_factory = (
            client_factory
            if client_factory is not None
            else self._default_client_factory
        )

    def list_domains(self) -> list[DomainInfo]:
        products = self.account.list_products()

        return [
            DomainInfo(
                name=product.domain,
                is_default=(
                    product.domain == self.default_domain
                ),
            )
            for product in sorted(
                products,
                key=lambda product: product.domain,
            )
        ]

    def resolve_domain(
        self,
        domain: str | None,
    ) -> str:
        if domain is not None:
            return normalize_domain(domain)

        domains = self.list_domains()

        if not domains:
            raise DomainNotFoundError(
                "No domains were discovered in the Tophost account"
            )

        if self.default_domain is not None:
            if any(
                item.name == self.default_domain
                for item in domains
            ):
                return self.default_domain

            raise DomainNotFoundError(
                "Configured default domain "
                f"{self.default_domain!r} "
                "was not found in the Tophost account"
            )

        if len(domains) == 1:
            return domains[0].name

        raise AmbiguousDomainError(
            "Multiple Tophost domains are available; "
            "an explicit domain is required"
        )

    def list_records(
        self,
        *,
        domain: str | None = None,
    ) -> list[DNSRecord]:
        client = self._client(
            domain
        )

        return client.list_records()

    def get_record(
        self,
        record_id: str,
        *,
        domain: str | None = None,
    ) -> DNSRecord:
        client = self._client(
            domain
        )

        return client.get_record(
            record_id
        )

    def find_records(
        self,
        *,
        domain: str | None = None,
        name: str | None = None,
        record_type: str | None = None,
        value: str | None = None,
    ) -> list[DNSRecord]:
        client = self._client(
            domain
        )

        return client.find_records(
            name=name,
            record_type=record_type,
            value=value,
        )

    def create_record(
        self,
        request: DNSRecordCreate,
        *,
        domain: str | None = None,
    ) -> DNSMutationResult:
        client = self._client(
            domain
        )

        return client.create_record(
            request
        )

    def patch_record(
        self,
        record_id: str,
        patch: DNSRecordPatch,
        *,
        domain: str | None = None,
    ) -> DNSMutationResult:
        client = self._client(
            domain
        )

        return client.patch_record(
            record_id,
            patch,
        )

    def delete_record(
        self,
        record_id: str,
        *,
        domain: str | None = None,
        expected_value: str | None = None,
        expected_priority: int | None = None,
    ) -> DNSMutationResult:
        client = self._client(
            domain
        )

        return client.delete_record(
            record_id,
            expected_value=expected_value,
            expected_priority=expected_priority,
        )

    def _client(
        self,
        domain: str | None,
    ) -> TophostDNSClient:
        resolved_domain = self.resolve_domain(
            domain
        )

        return self.client_factory(
            resolved_domain
        )

    def _default_client_factory(
        self,
        domain: str,
    ) -> TophostDNSClient:
        return TophostDNSClient(
            account=self.account,
            domain=domain,
        )
