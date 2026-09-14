from __future__ import annotations

from tophost_api.client.auth import TophostAccountClient
from tophost_api.models import AuthStatus, OTPChallenge


class AuthService:
    """Application-level authentication operations.

    API consumers never interact with Tophost cookies or HTTP sessions.
    """

    def __init__(
        self,
        account: TophostAccountClient,
    ):
        self.account = account

    def status(self) -> AuthStatus:
        return self.account.auth_status()

    def request_otp(self) -> OTPChallenge:
        return self.account.request_otp()

    def verify_otp(
        self,
        *,
        challenge_id: str,
        code: str,
    ) -> AuthStatus:
        self.account.confirm_otp(
            challenge_id=challenge_id,
            code=code,
        )

        return self.account.auth_status()
