from fastapi import APIRouter

from src.api.routes import tenants, accounts, queries, schedules, executions

api_router = APIRouter(prefix="/api/v1", tags=["api"])

api_router.include_router(tenants.router, prefix="/tenants", tags=["tenants"])
api_router.include_router(accounts.router, prefix="/tenants/{tenant_id}/accounts", tags=["accounts"])
api_router.include_router(queries.router, prefix="/queries", tags=["queries"])
api_router.include_router(schedules.router, prefix="/schedules", tags=["schedules"])
api_router.include_router(executions.router, prefix="/executions", tags=["executions"])
