"""FastAPI application: health, metrics, API routes. No Steampipe execution."""
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from src.api.routes import api_router
from src.services.database import init_db

# Prometheus metrics
execution_total = Counter("execution_total", "Total executions", ["status"])
execution_duration = Counter("execution_duration_seconds_total", "Total execution duration seconds")
active_jobs = Gauge("active_jobs", "Currently running execution jobs")
queue_depth = Gauge("queue_depth", "Job queue depth")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield
    # shutdown: close pools if needed
    pass


app = FastAPI(
    title="Cloud Governance & Cost Intelligence API",
    description="Steampipe-powered multi-tenant execution API",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/ready")
def ready() -> dict[str, str]:
    return {"status": "ready"}


@app.get("/live")
def live() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/metrics")
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


app.include_router(api_router)


def get_metrics() -> dict[str, Any]:
    """Expose metric objects for worker/scheduler to update."""
    return {
        "execution_total": execution_total,
        "execution_duration": execution_duration,
        "active_jobs": active_jobs,
        "queue_depth": queue_depth,
    }
