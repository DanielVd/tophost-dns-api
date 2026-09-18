from __future__ import annotations

import errno
import socket
import ssl
from collections.abc import Iterator
from typing import Any

import requests

from tophost_api.errors import UpstreamUnavailableError

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/151.0.0.0 Safari/537.36"
)


def _exception_chain(exc: BaseException) -> Iterator[BaseException]:
    pending = [exc]
    seen: set[int] = set()

    while pending:
        current = pending.pop()
        identity = id(current)

        if identity in seen:
            continue

        seen.add(identity)
        yield current

        for nested in (
            current.__cause__,
            current.__context__,
            getattr(current, "reason", None),
            getattr(current, "_reason", None),
        ):
            if isinstance(nested, BaseException):
                pending.append(nested)

        for argument in current.args:
            if isinstance(argument, BaseException):
                pending.append(argument)


def _connection_reason(exc: requests.ConnectionError) -> str:
    for current in _exception_chain(exc):
        if isinstance(current, socket.gaierror):
            return "dns_resolution_error"

        if isinstance(current, ssl.SSLError):
            return "tls_error"

        if isinstance(current, ConnectionRefusedError):
            return "connection_refused"

        if isinstance(current, ConnectionResetError):
            return "connection_reset"

        if isinstance(current, OSError):
            if current.errno == errno.ECONNREFUSED:
                return "connection_refused"

            if current.errno == errno.ECONNRESET:
                return "connection_reset"

    return "connection_error"


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
        except requests.ConnectTimeout as exc:
            raise UpstreamUnavailableError(
                "Tophost connection timed out",
                reason="connect_timeout",
            ) from exc
        except requests.ReadTimeout as exc:
            raise UpstreamUnavailableError(
                "Tophost response timed out",
                reason="read_timeout",
            ) from exc
        except requests.Timeout as exc:
            raise UpstreamUnavailableError(
                "Tophost request timed out",
                reason="timeout",
            ) from exc
        except requests.exceptions.SSLError as exc:
            raise UpstreamUnavailableError(
                "Tophost TLS connection failed",
                reason="tls_error",
            ) from exc
        except requests.ConnectionError as exc:
            raise UpstreamUnavailableError(
                "Tophost connection failed",
                reason=_connection_reason(exc),
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
