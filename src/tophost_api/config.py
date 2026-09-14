from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_domain(value: str) -> str:
    value = value.strip().lower().rstrip(".")

    if not value:
        raise ValueError("domain cannot be empty")

    if "." not in value:
        raise ValueError("domain must be fully qualified")

    return value


class Settings(BaseSettings):
    """Application configuration.

    A Tophost account may expose zero, one or many domains.

    Domains and Tophost product IDs are discovered dynamically after
    authentication. A default domain may optionally be configured as a
    convenience for clients that do not explicitly specify one.

    Runtime authentication state lives outside the source tree.
    """

    model_config = SettingsConfigDict(
        extra="ignore",
        case_sensitive=True,
        populate_by_name=True,
    )

    username: str = Field(
        validation_alias="TOPHOST_USER",
    )

    password: SecretStr = Field(
        validation_alias="TOPHOST_PASS",
    )

    api_key: SecretStr = Field(
        validation_alias="TOPHOST_API_KEY",
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
