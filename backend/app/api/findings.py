"""API: findings — scoped lists, detail, status transitions, comments."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Text, and_, cast, func, or_, select
from sqlalchemy.orm import Session

from ..models import (Asset, Environment, Finding, FindingComment,
                      FindingStatusHistory, ScanImport)
from ..services.ingest import transition_status
from .scope import require_asset, require_environment, require_finding
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
    """Adapter for transition_status (manual status changes via API)."""

    def __init__(self, db: Session):
        self.db = db

    def update_finding(self, finding_id, changes):
        finding = self.db.get(Finding, finding_id)
        for key, value in changes.items():
            setattr(finding, key, value)
        self.db.flush()

    def record_status_change(self, finding_id, from_status, to_status, reason,
                             import_id, changed_by):
        finding = self.db.get(Finding, finding_id)
        self.db.add(FindingStatusHistory(
            tenant_id=finding.tenant_id, finding_id=finding_id,
            from_status=from_status, to_status=to_status,
            reason=reason, import_id=import_id, changed_by=changed_by))
        self.db.flush()


def _literal_like(value: str) -> str:
    """Treat user search text literally, including SQL wildcard characters."""
    return '%' + value.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'


@router.get("/findings")
def list_findings(
    tenant_id: uuid.UUID,
    environment_id: Optional[uuid.UUID] = None,
    asset_id: Optional[uuid.UUID] = None,
    status: Optional[str] = "active",
    severity: Optional[list[str]] = Query(None),
    scanner: Optional[str] = None,
    kind: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Paginated operational rows: one row = one finding on one asset and port.

    Filters are applied before pagination so items and total always agree.
    """
    if environment_id:
        require_environment(db, environment_id, tenant_id)
    if asset_id:
        require_asset(db, asset_id, tenant_id)
    stmt = select(
        Finding.id, Finding.environment_id,
        Environment.name.label("environment_name"),
        Finding.asset_id,
        cast(Asset.ip, Text).label("asset_ip"),
        Asset.fqdn.label("asset_fqdn"),
        Asset.hostname_netbios.label("asset_hostname"),
        Asset.os.label("asset_os"),
        Asset.tags.label("asset_tags"),
        Finding.kind, Finding.scanner, Finding.rule_id, Finding.rule_title,
        Finding.cves, Finding.severity, Finding.severity_raw, Finding.status,
        Finding.port, Finding.protocol, Finding.first_seen, Finding.last_seen,
    ).join(Asset, and_(Asset.id == Finding.asset_id, Asset.tenant_id == tenant_id)
    ).join(Environment, and_(Environment.id == Finding.environment_id,
                             Environment.tenant_id == tenant_id)
    ).where(Finding.tenant_id == tenant_id)
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
    if search and search.strip():
        pattern = _literal_like(search)
        stmt = stmt.where(or_(Finding.rule_title.ilike(pattern, escape='\\'),
                              Finding.rule_id.ilike(pattern, escape='\\'),
                              Finding.description.ilike(pattern, escape='\\')))
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = db.execute(
        stmt.order_by(Finding.last_seen.desc(), Finding.id.desc())
        .limit(limit).offset(offset)).mappings().all()
    return {"items": [dict(row) for row in rows], "total": total,
            "limit": limit, "offset": offset}


def _import_summary(db: Session, import_id: Optional[str]) -> Optional[dict[str, Any]]:
    if not import_id:
        return None
    row = db.get(ScanImport, import_id)
    if not row:
        return None
    return {"id": str(row.id), "filename": row.filename, "scanner": row.scanner,
            "status": row.status, "created_at": row.created_at,
            "environment_id": str(row.environment_id)}


@router.get("/findings/{finding_id}")
def get_finding(finding_id: int, tenant_id: uuid.UUID, db: Session = Depends(get_db)):
    """Full individual-finding view: asset context, provenance, history, comments."""
    finding = require_finding(db, finding_id, tenant_id)
    asset = db.execute(select(Asset).where(
        Asset.id == finding.asset_id, Asset.tenant_id == tenant_id)).scalar_one()
    environment = db.execute(select(Environment).where(
        Environment.id == finding.environment_id,
        Environment.tenant_id == tenant_id)).scalar_one()
    history = db.execute(
        select(FindingStatusHistory).where(FindingStatusHistory.finding_id == finding_id)
        .order_by(FindingStatusHistory.changed_at.desc(),
                  FindingStatusHistory.id.desc())).scalars().all()
    comments = db.execute(
        select(FindingComment).where(FindingComment.finding_id == finding_id)
        .order_by(FindingComment.created_at.desc(),
                  FindingComment.id.desc())).scalars().all()
    return {
        "finding": finding,
        "asset": {"id": str(asset.id), "environment_id": str(asset.environment_id),
                  "ip": str(asset.ip) if asset.ip else None,
                  "fqdn": asset.fqdn, "hostname_netbios": asset.hostname_netbios,
                  "os": asset.os, "criticality": asset.criticality,
                  "tags": asset.tags},
        "environment": {"id": str(environment.id), "name": environment.name,
                        "kind": environment.kind},
        "provenance": {"last_import": _import_summary(db, finding.last_import_id),
                       "closed_by_import": _import_summary(db, finding.closed_by_import_id)},
        "history": history,
        "comments": comments,
    }


@router.post("/findings/{finding_id}/status")
def change_status(finding_id: int, tenant_id: uuid.UUID, payload: StatusIn,
                  db: Session = Depends(get_db)):
    """Transitions: Active / Mitigated / False Positive / Risk Accepted
    (con data scadenza + nota obbligatoria)."""
    finding = require_finding(db, finding_id, tenant_id)
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
def add_comment(finding_id: int, tenant_id: uuid.UUID, payload: CommentIn,
                db: Session = Depends(get_db)):
    finding = require_finding(db, finding_id, tenant_id)
    comment = FindingComment(tenant_id=finding.tenant_id, finding_id=finding_id,
                             **payload.model_dump())
    db.add(comment)
    db.commit()
    return comment
