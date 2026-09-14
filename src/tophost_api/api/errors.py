from __future__ import annotations

from fastapi import Request, status
from fastapi.responses import JSONResponse

from tophost_api.errors import (
    AmbiguousDomainError,
    AuthenticationError,
    DomainNotFoundError,
    OTPChallengeNotFoundError,
    OTPInvalidError,
    OTPRequiredError,
    RecordChangedError,
    RecordNotFoundError,
    TophostAPIError,
    UpstreamProtocolError,
    UpstreamUnavailableError,
)


def status_for_error(
    exc: TophostAPIError,
) -> int:
    if isinstance(
        exc,
        (
            AuthenticationError,
            OTPInvalidError,
        ),
    ):
        return status.HTTP_401_UNAUTHORIZED

    if isinstance(
        exc,
        OTPRequiredError,
    ):
        return status.HTTP_428_PRECONDITION_REQUIRED

    if isinstance(
        exc,
        (
            DomainNotFoundError,
            RecordNotFoundError,
            OTPChallengeNotFoundError,
        ),
    ):
        return status.HTTP_404_NOT_FOUND

    if isinstance(
        exc,
        (
            AmbiguousDomainError,
            RecordChangedError,
        ),
    ):
        return status.HTTP_409_CONFLICT

    if isinstance(
        exc,
        UpstreamUnavailableError,
    ):
        return status.HTTP_503_SERVICE_UNAVAILABLE

    if isinstance(
        exc,
        UpstreamProtocolError,
    ):
        return status.HTTP_502_BAD_GATEWAY

    return status.HTTP_400_BAD_REQUEST


async def tophost_error_handler(
    request: Request,
    exc: TophostAPIError,
) -> JSONResponse:
    del request

    code = (
        exc.code.value
        if hasattr(exc.code, "value")
        else str(exc.code)
    )

    return JSONResponse(
        status_code=status_for_error(exc),
        content={
            "error": {
                "code": code,
                "message": str(exc),
                "retryable": bool(exc.retryable),
                "context": getattr(
                    exc,
                    "context",
                    None,
                ),
            }
        },
    )
