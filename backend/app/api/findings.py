"""API: findings — filtri, dettaglio, transizioni di stato, commenti."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Finding, FindingComment, FindingStatusHistory
from ..services.ingest import transition_status
from .tenants import get_db

router = APIRouter(prefix="/api")


class StatusIn(BaseModel):
    status: str
    reason: Optional[str] = None
    risk_accepted_until: Optional[date] = None
    changed_by: Optional[str] = None


class CommentIn(BaseModel):
    author: str = "analyst"
    body: str = Field(min_length=1)


class _Repo:
    """Adapter minimale per transition_status (stato manuale lato API)."""

    def __init__(self, db: Session):
        self.db = db

    def update_finding(self, finding_id, changes):
        finding = self.db.get(Finding, finding_id)
        for key, value in changes.items():
            setattr(finding, key, value)
        self.db.flush()

    def record_status_change(self, finding_id, from_status, to_status, reason,
                             import_id, changed_by):
        self.db.add(FindingStatusHistory(
            finding_id=finding_id, from_status=from_status, to_status=to_status,
            reason=reason, import_id=import_id, changed_by=changed_by))
        self.db.flush()


@router.get("/findings")
def list_findings(
    tenant_id: Optional[uuid.UUID] = None,
    environment_id: Optional[uuid.UUID] = None,
    asset_id: Optional[uuid.UUID] = None,
    status: Optional[str] = "active",
    severity: Optional[list[str]] = Query(None),
    scanner: Optional[str] = None,
    kind: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    stmt = select(Finding)
    if tenant_id:
        stmt = stmt.where(Finding.tenant_id == tenant_id)
    if environment_id:
        stmt = stmt.where(Finding.environment_id == environment_id)
    if asset_id:
        stmt = stmt.where(Finding.asset_id == asset_id)
    if status and status != "all":
        stmt = stmt.where(Finding.status == status)
    if severity:
        stmt = stmt.where(Finding.severity.in_(severity))
    if scanner:
        stmt = stmt.where(Finding.scanner == scanner)
    if kind:
        stmt = stmt.where(Finding.kind == kind)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(Finding.rule_title.ilike(pattern) | Finding.rule_id.ilike(pattern)
                          | Finding.description.ilike(pattern))
    stmt = stmt.order_by(Finding.last_seen.desc()).limit(limit).offset(offset)
    return db.execute(stmt).scalars().all()


@router.get("/findings/{finding_id}")
def get_finding(finding_id: int, db: Session = Depends(get_db)):
    finding = db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(404, "Finding non trovato")
    history = db.execute(
        select(FindingStatusHistory).where(FindingStatusHistory.finding_id == finding_id)
        .order_by(FindingStatusHistory.changed_at.desc())).scalars().all()
    comments = db.execute(
        select(FindingComment).where(FindingComment.finding_id == finding_id)
        .order_by(FindingComment.created_at.desc())).scalars().all()
    return {"finding": finding, "history": history, "comments": comments}


@router.post("/findings/{finding_id}/status")
def change_status(finding_id: int, payload: StatusIn, db: Session = Depends(get_db)):
    """Transizioni: Active / Mitigated / False Positive / Risk Accepted
    (con data scadenza + nota obbligatoria)."""
    finding = db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(404, "Finding non trovato")
    current = {c.name: getattr(finding, c.name) for c in finding.__table__.columns}
    try:
        transition_status(_Repo(db), current, payload.status, payload.reason,
                          payload.risk_accepted_until.isoformat() if payload.risk_accepted_until else None,
                          None, payload.changed_by)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.commit()
    db.refresh(finding)
    return finding


@router.post("/findings/{finding_id}/comments", status_code=201)
def add_comment(finding_id: int, payload: CommentIn, db: Session = Depends(get_db)):
    if not db.get(Finding, finding_id):
        raise HTTPException(404, "Finding non trovato")
    comment = FindingComment(finding_id=finding_id, **payload.model_dump())
    db.add(comment)
    db.commit()
    return comment
