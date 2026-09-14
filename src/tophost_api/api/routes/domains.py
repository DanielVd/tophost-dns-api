from fastapi import APIRouter, Depends

from tophost_api.api.dependencies import (
    DNSServiceDep,
    require_api_key,
)
from tophost_api.models import DomainInfo

router = APIRouter(
    prefix="/domains",
    tags=["domains"],
    dependencies=[
        Depends(require_api_key)
    ],
)


@router.get(
    "",
    response_model=list[DomainInfo],
)
def list_domains(
    service: DNSServiceDep,
) -> list[DomainInfo]:
    return service.list_domains()
