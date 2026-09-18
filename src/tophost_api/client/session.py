from __future__ import annotations

from typing import Any

import requests

from tophost_api.errors import UpstreamUnavailableError

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/151.0.0.0 Safari/537.36"
)


class TophostHTTPSession:
    """Thin HTTP transport for Tophost.

    This layer knows HTTP, cookies and timeouts, but knows nothing about
    authentication flows, products or DNS semantics.
    """

    def __init__(
        self,
        *,
        timeout: float = 20.0,
        user_agent: str = DEFAULT_USER_AGENT,
    ):
        self.timeout = timeout
        self.user_agent = user_agent
        self.session = self._new_session()

    def _new_session(self) -> requests.Session:
        session = requests.Session()
        session.headers["User-Agent"] = self.user_agent
        return session

    def reset(self) -> None:
        self.session.close()
        self.session = self._new_session()

    def request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)

        try:
            return self.session.request(
                method,
                url,
                **kwargs,
            )
        except requests.Timeout as exc:
            raise UpstreamUnavailableError(
                "Tophost request timed out",
                reason="timeout",
            ) from exc
        except requests.ConnectionError as exc:
            raise UpstreamUnavailableError(
                "Tophost connection failed",
                reason="connection_error",
            ) from exc
        except requests.RequestException as exc:
            raise UpstreamUnavailableError(
                "Tophost request failed",
                reason="request_error",
            ) from exc

    def get(
        self,
        url: str,
        **kwargs: Any,
    ) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def post(
        self,
        url: str,
        **kwargs: Any,
    ) -> requests.Response:
        return self.request("POST", url, **kwargs)

    def export_cookies(self) -> list[dict[str, Any]]:
        return [
            {
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
                "secure": bool(cookie.secure),
                "expires": cookie.expires,
            }
            for cookie in self.session.cookies
        ]

    def import_cookies(
        self,
        cookies: list[dict[str, Any]],
    ) -> None:
        for item in cookies:
            kwargs: dict[str, Any] = {
                "name": item["name"],
                "value": item["value"],
                "path": item.get("path") or "/",
                "secure": bool(item.get("secure")),
            }

            if item.get("domain"):
                kwargs["domain"] = item["domain"]

            if item.get("expires") is not None:
                kwargs["expires"] = item["expires"]

            cookie = requests.cookies.create_cookie(
                **kwargs
            )
            self.session.cookies.set_cookie(cookie)
