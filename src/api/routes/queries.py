from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query as Q

from src.api.deps import DbSession
from src.api.schemas import QueryCreate, QueryResponse
from src.models import Query
from src.services.query_hash import content_hash_for_query_text

router = APIRouter()


@router.post("", response_model=QueryResponse)
def create_query(session: DbSession, body: QueryCreate) -> Query:
    existing = session.query(Query).filter(Query.name == body.name, Query.version == body.version).first()
    if existing:
        raise HTTPException(status_code=409, detail="Query with this name and version already exists")
    q = Query(
        id=str(uuid4()),
        name=body.name,
        version=body.version,
        provider=body.provider,
        plugin=body.plugin,
        query_text=body.query_text,
        execution_mode=body.execution_mode,
        output_format=body.output_format,
        schedule_enabled=body.schedule_enabled,
        extra_metadata=body.extra_metadata,
        content_hash=content_hash_for_query_text(body.query_text),
    )
    session.add(q)
    session.flush()
    return q


@router.get("", response_model=list[QueryResponse])
def list_queries(
    session: DbSession,
    skip: int = Q(0, ge=0),
    limit: int = Q(20, ge=1, le=100),
    provider: str | None = None,
    active: bool | None = None,
) -> list[Query]:
    query = session.query(Query).filter(Query.deleted_at.is_(None))
    if provider:
        query = query.filter(Query.provider == provider)
    if active is not None:
        query = query.filter(Query.active == active)
    return query.offset(skip).limit(limit).all()
