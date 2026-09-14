from __future__ import annotations

import secrets
import time
from pathlib import Path

from bs4 import BeautifulSoup

from tophost_api.client.products import ProductParser
from tophost_api.client.session import TophostHTTPSession
from tophost_api.client.state import SecureStateStore
from tophost_api.errors import (
    AuthenticationError,
    OTPChallengeNotFoundError,
    OTPInvalidError,
    OTPRequiredError,
    UpstreamProtocolError,
)
from tophost_api.models import (
    AuthStatus,
    OTPChallenge,
    TophostProduct,
)

LOGIN_URL = "https://www.tophost.it/co/accesso"
LOGIN_AJAX_URL = "https://www.tophost.it/co/login_myth_ajax"
MYTH_URL = "https://www.tophost.it/myth/"
OTP_URL = "https://www.tophost.it/myth/2fa"
PRODUCTS_URL = "https://www.tophost.it/myth/rinnova"


class TophostAccountClient:
    """Authenticated Tophost account client.

    Handles login, trusted 2FA state, OTP challenges and product discovery.
    It deliberately does not know anything about DNS records.
    """

    def __init__(
        self,
        *,
        username: str,
        password: str,
        trust_file: Path,
        otp_session_file: Path,
        timeout: float = 20.0,
        http: TophostHTTPSession | None = None,
    ):
        self.username = username
        self.password = password
        self.trust_file = trust_file
        self.otp_session_file = otp_session_file

        self.http = http or TophostHTTPSession(
            timeout=timeout
        )

        self.products = ProductParser()

    def auth_status(self) -> AuthStatus:
        trust = SecureStateStore.read(
            self.trust_file
        )

        expires = None
        valid = False

        if trust is not None:
            expires = trust.get("expires")

            valid = bool(
                isinstance(expires, (int, float))
                and expires > time.time()
            )

        return AuthStatus(
            credentials_configured=bool(
                self.username and self.password
            ),
            trusted_2fa_present=trust is not None,
            trusted_2fa_valid=valid,
            trusted_2fa_expires=(
                int(expires)
                if isinstance(expires, (int, float))
                else None
            ),
            otp_pending=self.otp_session_file.exists(),
        )

    def authenticate(
        self,
        *,
        use_trusted_2fa: bool = True,
    ) -> None:
        self.http.reset()

        if use_trusted_2fa:
            self._restore_trusted_cookie()

        self._perform_primary_login()

        response = self.http.get(
            MYTH_URL,
            allow_redirects=False,
        )

        self._raise_for_http_error(response)

        location = response.headers.get(
            "Location"
        )

        if (
            response.status_code == 302
            and location == "/myth/rinnova"
        ):
            return

        if (
            response.status_code == 302
            and location == "/myth/2fa"
        ):
            raise OTPRequiredError(
                "Tophost requires two-factor authentication"
            )

        raise UpstreamProtocolError(
            "Unexpected Tophost authentication state: "
            f"HTTP {response.status_code}, "
            f"Location={location!r}"
        )

    def request_otp(self) -> OTPChallenge:
        self.http.reset()

        self._perform_primary_login()

        response = self.http.get(
            MYTH_URL,
            allow_redirects=False,
        )

        self._raise_for_http_error(response)

        if not (
            response.status_code == 302
            and response.headers.get("Location") == "/myth/2fa"
        ):
            raise UpstreamProtocolError(
                "Tophost did not enter the expected 2FA state"
            )

        response = self.http.get(
            OTP_URL
        )
        self._raise_for_http_error(response)

        challenge_id = secrets.token_urlsafe(24)

        SecureStateStore.write(
            self.otp_session_file,
            {
                "version": 1,
                "challenge_id": challenge_id,
                "created_at": int(time.time()),
                "cookies": self.http.export_cookies(),
            },
        )

        return OTPChallenge(
            challenge_id=challenge_id,
            status="pending",
        )

    def confirm_otp(
        self,
        *,
        challenge_id: str,
        code: str,
        trust_days: int = 90,
    ) -> int | None:
        state = SecureStateStore.read(
            self.otp_session_file
        )

        if state is None:
            raise OTPChallengeNotFoundError(
                "No pending OTP challenge"
            )

        if state.get("challenge_id") != challenge_id:
            raise OTPChallengeNotFoundError(
                "OTP challenge does not match"
            )

        cookies = state.get("cookies")

        if not isinstance(cookies, list):
            raise UpstreamProtocolError(
                "Pending OTP challenge contains invalid cookie state"
            )

        self.http.reset()
        self.http.import_cookies(cookies)

        response = self.http.post(
            OTP_URL,
            headers={
                "Origin": "https://www.tophost.it",
                "Referer": OTP_URL,
            },
            data={
                "expire_gg": str(trust_days),
                "cod_2fa": code.strip(),
                "submit": "",
            },
        )

        self._raise_for_http_error(response)

        response = self.http.get(
            MYTH_URL,
            allow_redirects=False,
        )

        self._raise_for_http_error(response)

        if not (
            response.status_code == 302
            and response.headers.get("Location") == "/myth/rinnova"
        ):
            raise OTPInvalidError(
                "OTP was not accepted by Tophost"
            )

        trusted = self._find_trusted_cookie()

        if trusted is None:
            raise UpstreamProtocolError(
                "Tophost accepted OTP but did not issue "
                "a trusted 2FA cookie"
            )

        SecureStateStore.write(
            self.trust_file,
            trusted,
        )

        SecureStateStore.delete(
            self.otp_session_file
        )

        expires = trusted.get("expires")

        return (
            int(expires)
            if isinstance(expires, (int, float))
            else None
        )

    def list_products(
        self,
    ) -> list[TophostProduct]:
        self.authenticate()

        response = self.http.get(
            PRODUCTS_URL
        )

        self._raise_for_http_error(response)

        return self.products.parse(
            response.text
        )

    def resolve_product(
        self,
        domain: str,
    ) -> TophostProduct:
        self.authenticate()

        response = self.http.get(
            PRODUCTS_URL
        )

        self._raise_for_http_error(response)

        return self.products.resolve(
            response.text,
            domain,
        )

    def _perform_primary_login(self) -> None:
        response = self.http.get(
            LOGIN_URL
        )
        self._raise_for_http_error(response)

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        meta = soup.find(
            "meta",
            attrs={"name": "csrf_token"},
        )

        csrf = (
            meta.get("content")
            if meta is not None
            else None
        )

        if not isinstance(csrf, str) or not csrf:
            raise UpstreamProtocolError(
                "Tophost CSRF token not found"
            )

        response = self.http.post(
            LOGIN_AJAX_URL,
            headers={
                "Origin": "https://www.tophost.it",
                "Referer": LOGIN_URL,
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRF-Token": csrf,
            },
            data={
                "prodotto": "",
                "username": self.username,
                "password": self.password,
                "_valid": "tophost",
            },
        )

        self._raise_for_http_error(response)

        try:
            payload = response.json()
        except ValueError as exc:
            raise UpstreamProtocolError(
                "Tophost login response is not JSON"
            ) from exc

        if not isinstance(payload, dict):
            raise UpstreamProtocolError(
                "Tophost login response has an unexpected shape"
            )

        if "uid" not in payload:
            raise AuthenticationError(
                "Tophost username or password was not accepted"
            )

    def _restore_trusted_cookie(self) -> None:
        trusted = SecureStateStore.read(
            self.trust_file
        )

        if trusted is None:
            return

        expires = trusted.get("expires")

        if not isinstance(expires, (int, float)):
            return

        if expires <= time.time():
            return

        self.http.import_cookies(
            [trusted]
        )

    def _find_trusted_cookie(
        self,
    ) -> dict | None:
        for cookie in self.http.export_cookies():
            if str(cookie.get("name", "")).startswith(
                "th_2auth"
            ):
                return cookie

        return None

    @staticmethod
    def _raise_for_http_error(response) -> None:
        if response.status_code >= 400:
            raise UpstreamProtocolError(
                "Unexpected Tophost HTTP response: "
                f"{response.status_code}"
            )
