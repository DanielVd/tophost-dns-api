from pathlib import Path

import pytest
from pydantic import ValidationError

from tophost_api.config import Settings


def make_settings(**overrides):
    values = {
        "username": "user@example.com",
        "password": "secret",
        "api_key": "api-secret",
        "default_domain": None,
        "state_dir": Path("/tmp/tophost-dns-api-test"),
    }
    values.update(overrides)
    return Settings(**values)


def test_default_domain_is_optional():
    settings = make_settings()

    assert settings.default_domain is None


def test_default_domain_is_normalized():
    settings = make_settings(
        default_domain="  Example.COM. "
    )

    assert settings.default_domain == "example.com"


def test_empty_default_domain_becomes_none():
    settings = make_settings(
        default_domain="   "
    )

    assert settings.default_domain is None


def test_non_fqdn_default_domain_is_rejected():
    with pytest.raises(ValidationError):
        make_settings(
            default_domain="localhost"
        )


def test_product_id_is_not_part_of_public_settings():
    assert "product_id" not in Settings.model_fields


def test_domain_is_not_required_configuration():
    assert "domain" not in Settings.model_fields


def test_state_files_are_derived_from_state_dir():
    settings = make_settings(
        state_dir=Path("/var/lib/tophost-dns-api")
    )

    assert settings.trust_file == Path(
        "/var/lib/tophost-dns-api/2fa.json"
    )

    assert settings.otp_session_file == Path(
        "/var/lib/tophost-dns-api/otp-session.json"
    )


def test_request_timeout_must_be_positive():
    with pytest.raises(ValidationError):
        make_settings(
            request_timeout=0,
        )
