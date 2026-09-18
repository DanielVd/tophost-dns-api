import html
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import Tag

from tophost_api.errors import (
    AmbiguousDomainError,
    DomainNotFoundError,
    UpstreamProtocolError,
)
from tophost_api.models import TophostProduct

PRODUCT_FUNC_RE = re.compile(
    r"(?:[?&])func=dd(?P<product_id>[0-9]+)(?:[&#]|$)",
    re.IGNORECASE,
)

DOMAIN_RE = re.compile(
    r"(?<![@A-Za-z0-9_.-])"
    r"(?P<domain>"
    r"(?:[A-Za-z0-9]"
    r"(?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}"
    r")"
    r"(?![A-Za-z0-9_.-])"
)

IGNORED_DOMAINS = {
    "tophost.it",
    "www.tophost.it",
    "cp.tophost.it",
}


def normalize_domain(value: str) -> str:
    return value.strip().lower().rstrip(".")


class ProductParser:
    """Parse Tophost products from the authenticated renewal page."""

    def __init__(
        self,
        *,
        base_url: str = "https://www.tophost.it/myth/",
    ):
        self.base_url = base_url

    def parse(self, page_html: str) -> list[TophostProduct]:
        soup = BeautifulSoup(page_html, "html.parser")

        products: dict[tuple[str, str], TophostProduct] = {}

        for anchor in soup.find_all("a", href=True):
            if not isinstance(anchor, Tag):
                continue

            href = html.unescape(str(anchor.get("href", "")))
            match = PRODUCT_FUNC_RE.search(href)

            if not match:
                continue

            product_id = match.group("product_id")
            domain = self._find_domain_for_anchor(anchor)

            if domain is None:
                raise UpstreamProtocolError(
                    "Tophost product link could not be associated "
                    "with exactly one domain"
                )

            product = TophostProduct(
                domain=domain,
                product_id=product_id,
                control_panel_href=urljoin(
                    self.base_url,
                    href,
                ),
            )

            products[(domain, product_id)] = product

        return sorted(
            products.values(),
            key=lambda product: (
                product.domain,
                product.product_id,
            ),
        )

    def resolve(
        self,
        page_html: str,
        domain: str,
        *,
        product_id_override: str | None = None,
    ) -> TophostProduct:
        target = normalize_domain(domain)
        products = self.parse(page_html)

        matches = [
            product
            for product in products
            if product.domain == target
        ]

        if product_id_override is not None:
            override = product_id_override.strip()

            matches = [
                product
                for product in matches
                if product.product_id == override
            ]

        if not matches:
            discovered = sorted(
                {
                    product.domain
                    for product in products
                }
            )

            suffix = (
                f"; discovered domains: {', '.join(discovered)}"
                if discovered
                else "; no products could be discovered"
            )

            raise DomainNotFoundError(
                f"Tophost domain {target!r} not found"
                f"{suffix}"
            )

        unique_ids = {
            product.product_id
            for product in matches
        }

        if len(unique_ids) > 1:
            raise AmbiguousDomainError(
                f"Tophost domain {target!r} maps to "
                f"multiple product IDs: "
                f"{', '.join(sorted(unique_ids))}"
            )

        if len(matches) != 1:
            raise UpstreamProtocolError(
                f"Unexpected duplicate Tophost product "
                f"for domain {target!r}"
            )

        return matches[0]

    def _find_domain_for_anchor(
        self,
        anchor: Tag,
    ) -> str | None:
        """Find the domain belonging to a control-panel link.

        We walk from the link towards its closest enclosing containers.
        The first container exposing exactly one plausible domain is
        considered the product boundary.

        This avoids coupling the parser to Tophost CSS classes or random
        element IDs while still keeping discovery local to each product.
        """

        node: Tag | None = anchor

        for _ in range(8):
            parent = node.parent

            if not isinstance(parent, Tag):
                break

            node = parent
            candidates = self._domains_from_text(
                " ".join(node.stripped_strings)
            )

            if len(candidates) == 1:
                return next(iter(candidates))

            if len(candidates) > 1:
                # We have probably climbed above the product boundary.
                # Do not guess.
                return None

        return None

    @staticmethod
    def _domains_from_text(text: str) -> set[str]:
        domains = {
            normalize_domain(match.group("domain"))
            for match in DOMAIN_RE.finditer(text)
        }

        return {
            domain
            for domain in domains
            if domain not in IGNORED_DOMAINS
        }
