"""
Approval Service for Salon Payments Ops.
Enforces the human-in-the-loop gate before any money adjustment can occur.
"""

from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import select

from libs.ledger.engine import get_db_session, init_db
from libs.ledger.models import Proposal, ExceptionRecord, AuditLog
from libs.ledger.operations import record_audit
from .executor import execute_approved_proposal, ExecutionError


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Salon Payments Approval Service",
    version="0.1.0",
    description="Human decision gate for exception fix proposals. Only this service executes financial actions.",
    lifespan=lifespan,
)


def get_db():
    with get_db_session() as session:
        yield session


# ===================== SCHEMAS =====================

class DecisionRequest(BaseModel):
    decision: str = Field(..., description="'approved' or 'rejected'")
    decision_notes: Optional[str] = None
    actor: str = Field(default="human:ops_manager")


class ProposalOut(BaseModel):
    id: str
    exception_id: str
    action: str
    amount_minor: int
    reason: str
    evidence_ids: List[str]
    confidence: float
    status: str
    decision_notes: Optional[str] = None
    created_at: Optional[str] = None


# ===================== ENDPOINTS =====================

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "approval_service"}


@app.get("/v1/proposals")
def list_proposals(
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
):
    query = select(Proposal)
    if status_filter:
        query = query.where(Proposal.status == status_filter)
    proposals = db.scalars(query.order_by(Proposal.created_at.desc())).all()

    return [
        {
            "id": p.id,
            "exception_id": p.exception_id,
            "action": p.action,
            "amount_minor": p.amount_minor,
            "reason": p.reason,
            "evidence_ids": p.evidence_ids,
            "confidence": p.confidence,
            "status": p.status,
            "decision_notes": p.decision_notes,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in proposals
    ]


@app.get("/v1/proposals/{proposal_id}")
def get_proposal(proposal_id: str, db: Session = Depends(get_db)):
    p = db.scalar(select(Proposal).where(Proposal.id == proposal_id))
    if not p:
        raise HTTPException(status_code=404, detail="Proposal not found")
    
    exc = db.scalar(select(ExceptionRecord).where(ExceptionRecord.id == p.exception_id))

    return {
        "id": p.id,
        "exception_id": p.exception_id,
        "exception_kind": exc.kind if exc else None,
        "exception_delta_minor": exc.delta_minor if exc else None,
        "action": p.action,
        "amount_minor": p.amount_minor,
        "reason": p.reason,
        "evidence_ids": p.evidence_ids,
        "confidence": p.confidence,
        "status": p.status,
        "decision_notes": p.decision_notes,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


@app.post("/v1/proposals/{proposal_id}/decision")
def decide_proposal(
    proposal_id: str,
    req: DecisionRequest,
    db: Session = Depends(get_db),
):
    p = db.scalar(select(Proposal).where(Proposal.id == proposal_id))
    if not p:
        raise HTTPException(status_code=404, detail="Proposal not found")

    if p.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Proposal has already been decided with status '{p.status}'",
        )

    if req.decision not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="Decision must be 'approved' or 'rejected'")

    p.status = req.decision
    p.decision_notes = req.decision_notes

    record_audit(
        session=db,
        correlation_id=p.id,
        actor=req.actor,
        event=f"proposal_{req.decision}",
        details={"proposal_id": p.id, "notes": req.decision_notes},
    )

    execution_result = None
    if req.decision == "approved":
        try:
            execution_result = execute_approved_proposal(db, proposal_id=p.id, actor=req.actor)
        except ExecutionError as e:
            raise HTTPException(status_code=500, detail=f"Execution error: {str(e)}")

    db.flush()

    return {
        "proposal_id": p.id,
        "status": p.status,
        "executed": execution_result is not None,
        "execution_result": execution_result,
    }
