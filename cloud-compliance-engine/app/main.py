"""FastAPI app for Cloud Compliance Engine."""
from pathlib import Path

from fastapi import FastAPI

from app.api.deps import get_db, get_tenant_id
from app.api.v1 import evaluation_runs, control_results, controls, control_status, simulate, snapshots, scan_runs

app = FastAPI(title="Cloud Compliance Engine", version="1.0.0")

app.include_router(evaluation_runs.router, prefix="/v1")
app.include_router(scan_runs.router, prefix="/v1")
app.include_router(control_results.router, prefix="/v1")
app.include_router(controls.router, prefix="/v1")
app.include_router(control_status.router, prefix="/v1")
app.include_router(simulate.router, prefix="/v1")
app.include_router(snapshots.router, prefix="/v1")


@app.get("/health")
def health():
    return {"status": "ok"}
