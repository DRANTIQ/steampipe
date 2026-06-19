"""GET /v1/control-results, GET /v1/control-results/{id}/evidence."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_tenant_id
from app.models.compliance import ControlResult, ControlEvidenceResource
from app.schemas.common import ControlResultResponse

router = APIRouter(prefix="/control-results", tags=["control-results"])

@router.get("", response_model=list[ControlResultResponse])
def list_control_results(run_id: UUID | None = Query(None), db: Session = Depends(get_db), tenant_id: str = Depends(get_tenant_id)):
    q = db.query(ControlResult).filter(ControlResult.tenant_id == UUID(tenant_id))
    if run_id is not None:
        q = q.filter(ControlResult.evaluation_run_id == run_id)
    return [ControlResultResponse.model_validate(r) for r in q.all()]

@router.get("/{result_id}/evidence")
def get_control_result_evidence(result_id: UUID, db: Session = Depends(get_db), tenant_id: str = Depends(get_tenant_id)):
    result = db.query(ControlResult).filter(ControlResult.id == result_id, ControlResult.tenant_id == UUID(tenant_id)).first()
    if not result:
        raise HTTPException(404, "Control result not found")
    evidence_rows = db.query(ControlEvidenceResource).filter(ControlEvidenceResource.control_result_id == result_id).all()
    return {"control_result_id": str(result.id), "control_id": result.control_id, "status": result.status, "evidence_in_details": (result.details or {}).get("evidence", []), "evidence_resources": [{"resource_type": r.resource_type, "resource_id": r.resource_id, "record_id": str(r.record_id) if r.record_id else None, "payload_excerpt": r.payload_excerpt} for r in evidence_rows]}
