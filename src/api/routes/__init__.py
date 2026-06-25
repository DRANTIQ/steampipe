from fastapi import APIRouter, Depends

from src.api.deps import enforce_auth_when_required
from src.api.routes import tenants, accounts, queries, schedules, executions, auth

api_router = APIRouter(prefix="/api/v1", tags=["api"])

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(
    tenants.router,
    prefix="/tenants",
    tags=["tenants"],
    dependencies=[Depends(enforce_auth_when_required)],
)
api_router.include_router(
    accounts.router,
    prefix="/tenants/{tenant_id}/accounts",
    tags=["accounts"],
    dependencies=[Depends(enforce_auth_when_required)],
)
api_router.include_router(
    queries.router,
    prefix="/queries",
    tags=["queries"],
    dependencies=[Depends(enforce_auth_when_required)],
)
api_router.include_router(
    schedules.router,
    prefix="/schedules",
    tags=["schedules"],
    dependencies=[Depends(enforce_auth_when_required)],
)
api_router.include_router(
    executions.router,
    prefix="/executions",
    tags=["executions"],
    dependencies=[Depends(enforce_auth_when_required)],
)
