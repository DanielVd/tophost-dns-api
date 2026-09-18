from __future__ import annotations

import argparse
import json
import sys
import traceback
from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import IntEnum, StrEnum
from pathlib import Path

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from tophost_api.client.auth import TophostAccountClient
from tophost_api.client.dns import TophostDNSClient
from tophost_api.config import normalize_domain
from tophost_api.errors import (
    AuthenticationError,
    OTPRequiredError,
    UpstreamProtocolError,
    UpstreamUnavailableError,
)
from tophost_api.models import TophostProduct


class CanaryStatus(StrEnum):
    COMPATIBLE = "compatible"
    TRANSIENT = "transient"
    ATTENTION = "attention"
    DRIFT = "drift"
    ERROR = "error"


class CanaryExit(IntEnum):
    INTERNAL_ERROR = 1
    COMPATIBLE = 0
    TRANSIENT = 10
    ATTENTION = 20
    DRIFT = 30


@dataclass(frozen=True)
class CanaryResult:
    status: CanaryStatus
    exit_code: CanaryExit
    stage: str
    reason: str
    product_count: int | None = None
    record_count: int | None = None

    def to_json(self) -> str:
        return json.dumps(
            asdict(self),
            separators=(",", ":"),
            sort_keys=True,
        )


class CanarySettings(BaseSettings):
    """Configuration required by the live upstream compatibility canary."""

    model_config = SettingsConfigDict(
        extra="ignore",
        case_sensitive=True,
        populate_by_name=True,
    )

    username: str = Field(
        min_length=1,
        validation_alias="TOPHOST_USER",
    )

    password: SecretStr = Field(
        min_length=1,
        validation_alias="TOPHOST_PASS",
    )

    default_domain: str | None = Field(
        default=None,
        validation_alias="TOPHOST_DEFAULT_DOMAIN",
    )

    state_dir: Path = Field(
        default=Path.home() / ".local/state/tophost-dns-api",
        validation_alias="TOPHOST_STATE_DIR",
    )

    request_timeout: float = Field(
        default=20.0,
        validation_alias="TOPHOST_REQUEST_TIMEOUT",
        gt=0,
    )

    require_records: bool = Field(
        default=True,
        validation_alias="TOPHOST_CANARY_REQUIRE_RECORDS",
    )

    @field_validator("default_domain")
    @classmethod
    def normalize_default_domain(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            return None

        return normalize_domain(value)

    @property
    def trust_file(self) -> Path:
        return self.state_dir / "2fa.json"

    @property
    def otp_session_file(self) -> Path:
        return self.state_dir / "otp-session.json"


DNSClientFactory = Callable[
    [TophostAccountClient, str],
    TophostDNSClient,
]


def _default_dns_client_factory(
    account: TophostAccountClient,
    domain: str,
) -> TophostDNSClient:
    return TophostDNSClient(
        account=account,
        domain=domain,
    )


def _classified_error(
    *,
    stage: str,
    exc: Exception,
    product_count: int | None = None,
) -> CanaryResult:
    if isinstance(exc, UpstreamUnavailableError):
        return CanaryResult(
            status=CanaryStatus.TRANSIENT,
            exit_code=CanaryExit.TRANSIENT,
            stage=stage,
            reason=exc.reason,
            product_count=product_count,
        )

    if isinstance(exc, OTPRequiredError):
        return CanaryResult(
            status=CanaryStatus.ATTENTION,
            exit_code=CanaryExit.ATTENTION,
            stage="authentication",
            reason="otp_required",
            product_count=product_count,
        )

    if isinstance(exc, AuthenticationError):
        return CanaryResult(
            status=CanaryStatus.ATTENTION,
            exit_code=CanaryExit.ATTENTION,
            stage="authentication",
            reason="authentication_failed",
            product_count=product_count,
        )

    if isinstance(exc, UpstreamProtocolError):
        return CanaryResult(
            status=CanaryStatus.DRIFT,
            exit_code=CanaryExit.DRIFT,
            stage=stage,
            reason="upstream_protocol_changed",
            product_count=product_count,
        )

    raise exc


def _select_product(
    products: list[TophostProduct],
    default_domain: str | None,
) -> TophostProduct | CanaryResult:
    product_count = len(products)

    if product_count == 0:
        return CanaryResult(
            status=CanaryStatus.DRIFT,
            exit_code=CanaryExit.DRIFT,
            stage="products",
            reason="no_products_parsed",
            product_count=0,
        )

    if default_domain is None:
        if product_count == 1:
            return products[0]

        return CanaryResult(
            status=CanaryStatus.ATTENTION,
            exit_code=CanaryExit.ATTENTION,
            stage="products",
            reason="default_domain_required",
            product_count=product_count,
        )

    target = normalize_domain(default_domain)
    matches = [
        product
        for product in products
        if product.domain == target
    ]

    if not matches:
        return CanaryResult(
            status=CanaryStatus.ATTENTION,
            exit_code=CanaryExit.ATTENTION,
            stage="products",
            reason="configured_domain_missing",
            product_count=product_count,
        )

    if len(matches) > 1:
        return CanaryResult(
            status=CanaryStatus.ATTENTION,
            exit_code=CanaryExit.ATTENTION,
            stage="products",
            reason="configured_domain_ambiguous",
            product_count=product_count,
        )

    return matches[0]


def run_canary(
    *,
    account: TophostAccountClient,
    default_domain: str | None,
    require_records: bool = True,
    dns_client_factory: DNSClientFactory = _default_dns_client_factory,
) -> CanaryResult:
    """Exercise the live read-only Tophost path used by the API.

    The result intentionally contains no domain names, HTML, cookies,
    credentials or upstream response bodies so it is safe to surface in
    public GitHub Actions logs and issues.
    """

    try:
        products = account.list_products()
    except (
        AuthenticationError,
        OTPRequiredError,
        UpstreamProtocolError,
        UpstreamUnavailableError,
    ) as exc:
        return _classified_error(
            stage="products",
            exc=exc,
        )

    selected = _select_product(
        products,
        default_domain,
    )

    if isinstance(selected, CanaryResult):
        return selected

    product_count = len(products)
    dns_client = dns_client_factory(
        account,
        selected.domain,
    )

    try:
        dns_client.connect(
            product=selected
        )
    except (
        AuthenticationError,
        OTPRequiredError,
        UpstreamProtocolError,
        UpstreamUnavailableError,
    ) as exc:
        return _classified_error(
            stage="sso",
            exc=exc,
            product_count=product_count,
        )

    try:
        records = dns_client.list_records()
    except (
        AuthenticationError,
        OTPRequiredError,
        UpstreamProtocolError,
        UpstreamUnavailableError,
    ) as exc:
        return _classified_error(
            stage="dns",
            exc=exc,
            product_count=product_count,
        )

    record_count = len(records)

    if require_records and record_count == 0:
        return CanaryResult(
            status=CanaryStatus.DRIFT,
            exit_code=CanaryExit.DRIFT,
            stage="dns",
            reason="no_dns_records_parsed",
            product_count=product_count,
            record_count=0,
        )

    return CanaryResult(
        status=CanaryStatus.COMPATIBLE,
        exit_code=CanaryExit.COMPATIBLE,
        stage="complete",
        reason="compatible",
        product_count=product_count,
        record_count=record_count,
    )


def _build_account(
    settings: CanarySettings,
) -> TophostAccountClient:
    return TophostAccountClient(
        username=settings.username,
        password=settings.password.get_secret_value(),
        trust_file=settings.trust_file,
        otp_session_file=settings.otp_session_file,
        timeout=settings.request_timeout,
    )


def main(
    argv: list[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the read-only Tophost upstream compatibility canary"
        )
    )
    parser.add_argument(
        "--allow-empty-dns",
        action="store_true",
        help="Do not treat an empty parsed DNS zone as upstream drift",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print a traceback for unexpected internal errors",
    )
    args = parser.parse_args(argv)

    try:
        settings = CanarySettings()
    except ValidationError:
        result = CanaryResult(
            status=CanaryStatus.ATTENTION,
            exit_code=CanaryExit.ATTENTION,
            stage="configuration",
            reason="invalid_configuration",
        )
        print(result.to_json())
        return int(result.exit_code)

    try:
        result = run_canary(
            account=_build_account(settings),
            default_domain=settings.default_domain,
            require_records=(
                settings.require_records
                and not args.allow_empty_dns
            ),
        )
    except Exception:  # noqa: BLE001
        # CLI boundary intentionally sanitizes unexpected failures.
        if args.debug:
            traceback.print_exc(
                file=sys.stderr
            )

        result = CanaryResult(
            status=CanaryStatus.ERROR,
            exit_code=CanaryExit.INTERNAL_ERROR,
            stage="internal",
            reason="unexpected_exception",
        )

    print(result.to_json())
    return int(result.exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
