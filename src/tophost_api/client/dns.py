from __future__ import annotations

import time
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from bs4.element import Tag

from tophost_api.client.auth import TophostAccountClient
from tophost_api.errors import (
    AuthenticationError,
    RecordChangedError,
    RecordNotFoundError,
    UpstreamProtocolError,
    UpstreamUnavailableError,
)
from tophost_api.models import (
    DNSMutationResult,
    DNSRecord,
    DNSRecordCreate,
    DNSRecordPatch,
    TophostProduct,
)

CP_HOST = "cp.tophost.it"
CP_BASE_URL = "https://cp.tophost.it"
DNS_URL = f"{CP_BASE_URL}/dns"

DNS_ADD_URL = f"{CP_BASE_URL}/x-dns-add"
DNS_MOD_URL = f"{CP_BASE_URL}/x-dns-mod"
DNS_DEL_URL = f"{CP_BASE_URL}/x-dns-del"


class DNSPageParser:
    """Parse DNS records from the Tophost control-panel HTML."""

    def parse(
        self,
        page_html: str,
        *,
        zone_name: str,
    ) -> list[DNSRecord]:
        soup = BeautifulSoup(page_html, "html.parser")
        records: list[DNSRecord] = []

        for row in soup.find_all("tr"):
            if not isinstance(row, Tag):
                continue

            row_id = row.get("id")

            if not isinstance(row_id, str):
                continue

            if not row_id.startswith("tr-"):
                continue

            record_id = row_id.removeprefix("tr-")

            if not record_id:
                continue

            markers = {
                "name": row.find(id=f"name-{record_id}"),
                "type": row.find(id=f"type-{record_id}"),
                "value": row.find(id=f"value-{record_id}"),
                "valueo": row.find(
                    "input",
                    attrs={"name": f"valueo-{record_id}"},
                ),
                "priorityo": row.find(
                    "input",
                    attrs={"name": f"priorityo-{record_id}"},
                ),
            }

            if not any(
                isinstance(marker, Tag)
                for marker in markers.values()
            ):
                # Tophost also uses tr-* IDs for non-record rows.
                continue

            name = self._cell_text(
                row,
                f"name-{record_id}",
            )
            record_type = self._cell_text(
                row,
                f"type-{record_id}",
            )
            value = self._cell_text(
                row,
                f"value-{record_id}",
            )

            if record_type is None or value is None:
                raise UpstreamProtocolError(
                    "Tophost DNS record row has an unexpected structure"
                )

            if name is None:
                table = row.find_parent("table")

                if (
                    isinstance(table, Tag)
                    and table.get("id") == "dns-soa"
                ):
                    name = zone_name
                else:
                    raise UpstreamProtocolError(
                        "Tophost DNS record row has no resolvable name"
                    )

            priority_input = row.find(
                "input",
                attrs={
                    "name": f"priorityo-{record_id}",
                },
            )

            priority = 0

            if isinstance(priority_input, Tag):
                raw_priority = priority_input.get(
                    "value",
                    "0",
                )

                try:
                    priority = int(str(raw_priority))
                except ValueError as exc:
                    raise UpstreamProtocolError(
                        f"Invalid DNS priority for record {record_id!r}"
                    ) from exc

            records.append(
                DNSRecord(
                    id=record_id,
                    name=name,
                    type=record_type,
                    value=value,
                    priority=priority,
                )
            )

        return records

    @staticmethod
    def _cell_text(
        row: Tag,
        cell_id: str,
    ) -> str | None:
        cell = row.find(
            id=cell_id,
        )

        if not isinstance(cell, Tag):
            return None

        return cell.get_text(
            " ",
            strip=True,
        )


class TophostDNSClient:
    """DNS operations for one explicitly selected Tophost domain."""

    def __init__(
        self,
        *,
        account: TophostAccountClient,
        domain: str,
    ):
        self.account = account
        self.domain = domain.strip().lower().rstrip(".")

        self.parser = DNSPageParser()

        self.product: TophostProduct | None = None
        self.connected = False

    def connect(
        self,
        *,
        product: TophostProduct | None = None,
    ) -> TophostProduct:
        if product is None:
            product = self.account.resolve_product(
                self.domain
            )
        elif product.domain != self.domain:
            raise UpstreamProtocolError(
                "Pre-resolved Tophost product does not match requested domain"
            )

        response = self.account.http.get(
            product.control_panel_href,
        )

        self._check_http_response(response)

        host = urlparse(response.url).hostname

        if host != CP_HOST:
            raise UpstreamProtocolError(
                "Tophost SSO did not reach the expected control panel"
            )

        self.product = product
        self.connected = True

        return product

    def list_records(self) -> list[DNSRecord]:
        self._ensure_connected()

        response = self.account.http.get(
            DNS_URL
        )

        self._check_http_response(response)
        self._ensure_cp_response(response)

        return self.parser.parse(
            response.text,
            zone_name=self.domain,
        )

    def get_record(
        self,
        record_id: str,
    ) -> DNSRecord:
        for record in self.list_records():
            if record.id == record_id:
                return record

        raise RecordNotFoundError(
            f"DNS record {record_id!r} not found "
            f"for domain {self.domain!r}"
        )

    def find_records(
        self,
        *,
        name: str | None = None,
        record_type: str | None = None,
        value: str | None = None,
    ) -> list[DNSRecord]:
        records = self.list_records()

        normalized_type = (
            record_type.strip().upper()
            if record_type is not None
            else None
        )

        return [
            record
            for record in records
            if (
                name is None
                or record.name == name
            )
            and (
                normalized_type is None
                or record.type == normalized_type
            )
            and (
                value is None
                or record.value == value
            )
        ]

    def create_record(
        self,
        request: DNSRecordCreate,
    ) -> DNSMutationResult:
        existing = [
            record
            for record in self.list_records()
            if (
                record.name == request.name
                and record.type == request.type
                and record.value == request.value
                and record.priority == request.priority
            )
        ]

        if existing:
            record = existing[0]

            return DNSMutationResult(
                changed=False,
                before=record,
                after=record,
                message="DNS record already present",
            )

        payload = {
            "record": str(
                time.time_ns() // 1_000_000
            ),
            "name": request.name,
            "type": request.type,
            "value": request.value,
        }

        if (
            request.type == "MX"
            or request.priority != 0
        ):
            payload["priority"] = str(
                request.priority
            )

        response = self.account.http.post(
            DNS_ADD_URL,
            headers=self._ajax_headers(),
            data=payload,
        )

        data = self._parse_mutation_response(
            response
        )

        record_id = data.get(
            "recordnewid"
        )

        if not isinstance(record_id, str) or not record_id:
            raise UpstreamProtocolError(
                "Tophost create response does not contain recordnewid"
            )

        after = DNSRecord(
            id=record_id,
            name=request.name,
            type=request.type,
            value=str(
                data.get("value", request.value)
            ),
            priority=self._response_priority(
                data,
                request.priority,
            ),
        )

        return DNSMutationResult(
            changed=True,
            before=None,
            after=after,
            dns_serial=self._dns_serial(data),
            message=self._message(data),
        )

    def patch_record(
        self,
        record_id: str,
        patch: DNSRecordPatch,
    ) -> DNSMutationResult:
        current = self.get_record(
            record_id
        )

        self._assert_expected_state(
            current,
            expected_value=patch.expected_value,
            expected_priority=patch.expected_priority,
        )

        new_value = (
            patch.value
            if patch.value is not None
            else current.value
        )

        new_priority = (
            patch.priority
            if patch.priority is not None
            else current.priority
        )

        if (
            new_value == current.value
            and new_priority == current.priority
        ):
            return DNSMutationResult(
                changed=False,
                before=current,
                after=current,
                message="DNS record already has requested state",
            )

        response = self.account.http.post(
            DNS_MOD_URL,
            headers=self._ajax_headers(),
            data={
                "record": current.id,
                "value": new_value,
                "valueo": current.value,
                "priority": str(new_priority),
                "priorityo": str(current.priority),
            },
        )

        data = self._parse_mutation_response(
            response
        )

        new_id = data.get(
            "recordnewid"
        )

        if not isinstance(new_id, str) or not new_id:
            raise UpstreamProtocolError(
                "Tophost update response does not contain recordnewid"
            )

        after = DNSRecord(
            id=new_id,
            name=current.name,
            type=current.type,
            value=str(
                data.get("value", new_value)
            ),
            priority=self._response_priority(
                data,
                new_priority,
            ),
        )

        return DNSMutationResult(
            changed=True,
            before=current,
            after=after,
            dns_serial=self._dns_serial(data),
            message=self._message(data),
        )

    def delete_record(
        self,
        record_id: str,
        *,
        expected_value: str | None = None,
        expected_priority: int | None = None,
    ) -> DNSMutationResult:
        current = self.get_record(
            record_id
        )

        self._assert_expected_state(
            current,
            expected_value=expected_value,
            expected_priority=expected_priority,
        )

        response = self.account.http.post(
            DNS_DEL_URL,
            headers=self._ajax_headers(),
            data={
                "record": current.id,
            },
        )

        data = self._parse_mutation_response(
            response
        )

        return DNSMutationResult(
            changed=True,
            before=current,
            after=None,
            dns_serial=self._dns_serial(data),
            message=self._message(data),
        )

    def _ensure_connected(self) -> None:
        if not self.connected:
            self.connect()

    def _ensure_cp_response(
        self,
        response,
    ) -> None:
        host = urlparse(response.url).hostname

        if host != CP_HOST:
            raise AuthenticationError(
                "Tophost control-panel session is not authenticated"
            )

    @staticmethod
    def _check_http_response(
        response,
    ) -> None:
        if (
            response.status_code in {408, 425, 429}
            or response.status_code >= 500
        ):
            raise UpstreamUnavailableError(
                "Tophost control panel is temporarily unavailable: "
                f"HTTP {response.status_code}"
            )

        if response.status_code >= 400:
            raise UpstreamProtocolError(
                "Unexpected Tophost control-panel HTTP response: "
                f"{response.status_code}"
            )

    def _parse_mutation_response(
        self,
        response,
    ) -> dict:
        self._check_http_response(
            response
        )
        self._ensure_cp_response(
            response
        )

        try:
            data = response.json()
        except ValueError as exc:
            raise UpstreamProtocolError(
                "Tophost DNS mutation response is not JSON"
            ) from exc

        if not isinstance(data, dict):
            raise UpstreamProtocolError(
                "Tophost DNS mutation response has unexpected shape"
            )

        if data.get("auth") == 0:
            raise AuthenticationError(
                "Tophost control-panel session expired"
            )

        if data.get("auth") != 1:
            raise UpstreamProtocolError(
                "Tophost DNS mutation response has unexpected auth state"
            )

        return data

    @staticmethod
    def _assert_expected_state(
        record: DNSRecord,
        *,
        expected_value: str | None,
        expected_priority: int | None,
    ) -> None:
        if (
            expected_value is not None
            and record.value != expected_value
        ):
            raise RecordChangedError(
                "DNS record value changed since it was read"
            )

        if (
            expected_priority is not None
            and record.priority != expected_priority
        ):
            raise RecordChangedError(
                "DNS record priority changed since it was read"
            )

    @staticmethod
    def _ajax_headers() -> dict[str, str]:
        return {
            "Origin": CP_BASE_URL,
            "Referer": DNS_URL,
            "X-Requested-With": "XMLHttpRequest",
        }

    @staticmethod
    def _dns_serial(
        data: dict,
    ) -> str | None:
        value = data.get(
            "dns_serial"
        )

        if not isinstance(value, dict):
            return None

        serial = value.get(
            "msg"
        )

        return (
            str(serial)
            if serial is not None
            else None
        )

    @staticmethod
    def _message(
        data: dict,
    ) -> str | None:
        value = data.get(
            "msg"
        )

        if value is None:
            return None

        return BeautifulSoup(
            str(value),
            "html.parser",
        ).get_text(
            " ",
            strip=True,
        )

    @staticmethod
    def _response_priority(
        data: dict,
        fallback: int,
    ) -> int:
        value = data.get(
            "priority",
            fallback,
        )

        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise UpstreamProtocolError(
                "Tophost returned an invalid DNS priority"
            ) from exc
