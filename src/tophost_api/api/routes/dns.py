from typing import Annotated

from fastapi import APIRouter, Depends, Query

from tophost_api.api.dependencies import (
    DNSServiceDep,
    require_api_key,
)
from tophost_api.models import (
    DNSMutationResult,
    DNSRecord,
    DNSRecordCreate,
    DNSRecordPatch,
)

router = APIRouter(
    prefix="/domains/{domain}/dns/records",
    tags=["dns"],
    dependencies=[
        Depends(require_api_key)
    ],
)


@router.get(
    "",
    response_model=list[DNSRecord],
)
def list_records(
    domain: str,
    service: DNSServiceDep,
    name: str | None = None,
    record_type: Annotated[
        str | None,
        Query(alias="type"),
    ] = None,
    value: str | None = None,
) -> list[DNSRecord]:
    if (
        name is not None
        or record_type is not None
        or value is not None
    ):
        return service.find_records(
            domain=domain,
            name=name,
            record_type=record_type,
            value=value,
        )

    return service.list_records(
        domain=domain
    )


@router.get(
    "/{record_id}",
    response_model=DNSRecord,
)
def get_record(
    domain: str,
    record_id: str,
    service: DNSServiceDep,
) -> DNSRecord:
    return service.get_record(
        record_id,
        domain=domain,
    )


@router.post(
    "",
    response_model=DNSMutationResult,
)
def create_record(
    domain: str,
    request: DNSRecordCreate,
    service: DNSServiceDep,
) -> DNSMutationResult:
    return service.create_record(
        request,
        domain=domain,
    )


@router.patch(
    "/{record_id}",
    response_model=DNSMutationResult,
)
def patch_record(
    domain: str,
    record_id: str,
    patch: DNSRecordPatch,
    service: DNSServiceDep,
) -> DNSMutationResult:
    return service.patch_record(
        record_id,
        patch,
        domain=domain,
    )


@router.delete(
    "/{record_id}",
    response_model=DNSMutationResult,
)
def delete_record(
    domain: str,
    record_id: str,
    service: DNSServiceDep,
    expected_value: str | None = None,
    expected_priority: int | None = None,
) -> DNSMutationResult:
    return service.delete_record(
        record_id,
        domain=domain,
        expected_value=expected_value,
        expected_priority=expected_priority,
    )
