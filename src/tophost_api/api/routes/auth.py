from fastapi import APIRouter, Depends, status

from tophost_api.api.dependencies import (
    AuthServiceDep,
    require_api_key,
)
from tophost_api.models import (
    AuthStatus,
    OTPChallenge,
    OTPVerifyRequest,
)

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    dependencies=[
        Depends(require_api_key)
    ],
)


@router.get(
    "/status",
    response_model=AuthStatus,
)
def auth_status(
    service: AuthServiceDep,
) -> AuthStatus:
    return service.status()


@router.post(
    "/otp",
    response_model=OTPChallenge,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_otp(
    service: AuthServiceDep,
) -> OTPChallenge:
    return service.request_otp()


@router.post(
    "/otp/{challenge_id}/verify",
    response_model=AuthStatus,
)
def verify_otp(
    challenge_id: str,
    request: OTPVerifyRequest,
    service: AuthServiceDep,
) -> AuthStatus:
    return service.verify_otp(
        challenge_id=challenge_id,
        code=request.code,
    )
