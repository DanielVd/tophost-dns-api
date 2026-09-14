from __future__ import annotations

import hmac
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from tophost_api.client.auth import TophostAccountClient
from tophost_api.config import Settings
from tophost_api.services.auth import AuthService
from tophost_api.services.dns import DNSService


@lru_cache
def get_settings() -> Settings:
    return Settings()


SettingsDep = Annotated[
    Settings,
    Depends(get_settings),
]


def require_api_key(
    settings: SettingsDep,
    x_api_key: Annotated[
        str | None,
        Header(alias="X-API-Key"),
    ] = None,
) -> None:
    expected = settings.api_key.get_secret_value()

    if x_api_key is None or not hmac.compare_digest(
        x_api_key,
        expected,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


def get_account(
    settings: SettingsDep,
) -> TophostAccountClient:
    return TophostAccountClient(
        username=settings.username,
        password=settings.password.get_secret_value(),
        trust_file=settings.trust_file,
        otp_session_file=settings.otp_session_file,
        timeout=settings.request_timeout,
    )


AccountDep = Annotated[
    TophostAccountClient,
    Depends(get_account),
]


def get_auth_service(
    account: AccountDep,
) -> AuthService:
    return AuthService(
        account=account,
    )


AuthServiceDep = Annotated[
    AuthService,
    Depends(get_auth_service),
]


def get_dns_service(
    account: AccountDep,
    settings: SettingsDep,
) -> DNSService:
    return DNSService(
        account=account,
        default_domain=settings.default_domain,
    )


DNSServiceDep = Annotated[
    DNSService,
    Depends(get_dns_service),
]
