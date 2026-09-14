from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DNSRecord(StrictModel):
    id: str
    name: str
    type: str
    value: str
    priority: int = 0

    @field_validator("type")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        value = value.strip().upper()

        if not value:
            raise ValueError("DNS record type cannot be empty")

        return value


class DNSRecordCreate(StrictModel):
    name: str
    type: str
    value: str
    priority: int = 0

    @field_validator("type")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        value = value.strip().upper()

        if not value:
            raise ValueError("DNS record type cannot be empty")

        return value


class DNSRecordPatch(StrictModel):
    value: str | None = None
    priority: int | None = None

    # Optimistic concurrency guard for MCP/API clients.
    expected_value: str | None = None
    expected_priority: int | None = None


class DNSMutationResult(StrictModel):
    changed: bool
    before: DNSRecord | None = None
    after: DNSRecord | None = None
    dns_serial: str | None = None
    message: str | None = None


class AuthStatus(StrictModel):
    credentials_configured: bool
    trusted_2fa_present: bool
    trusted_2fa_valid: bool
    trusted_2fa_expires: int | None = None
    otp_pending: bool


class OTPChallenge(StrictModel):
    challenge_id: str
    status: str = "pending"


class OTPVerifyRequest(StrictModel):
    code: str = Field(min_length=1)


class ErrorDetail(StrictModel):
    code: str
    message: str
    retryable: bool = False
    context: dict[str, Any] | None = None


class ErrorResponse(StrictModel):
    error: ErrorDetail


class TophostProduct(StrictModel):
    """A Tophost product discovered from the authenticated account page.

    product_id is an upstream implementation detail. The domain is the
    externally meaningful identity.
    """

    domain: str
    product_id: str
    control_panel_href: str

    @field_validator("domain")
    @classmethod
    def normalize_domain(cls, value: str) -> str:
        return value.strip().lower().rstrip(".")


class DomainInfo(StrictModel):
    """Public representation of a domain available to the account."""

    name: str
    is_default: bool = False

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip().lower().rstrip(".")

        if not value or "." not in value:
            raise ValueError("domain must be fully qualified")

        return value
