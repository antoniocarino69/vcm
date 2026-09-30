"""Explicit tenant scope helpers: cross-client targets stay hidden (404).

Every list, detail, comment, status transition and mutation must name the
client it acts for; a record owned by another client is indistinguishable from
a missing one (#0004).
"""
from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import Asset, Environment, Finding, ScanImport, Tenant


def require_tenant(db: Session, tenant_id: uuid.UUID) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Client not found")
    return tenant


def require_environment(db: Session, environment_id: uuid.UUID,
                        tenant_id: uuid.UUID) -> Environment:
    require_tenant(db, tenant_id)
    environment = db.get(Environment, environment_id)
    if not environment or str(environment.tenant_id) != str(tenant_id):
        raise HTTPException(404, "Environment not found for this client")
    return environment


def require_asset(db: Session, asset_id: uuid.UUID, tenant_id: uuid.UUID) -> Asset:
    require_tenant(db, tenant_id)
    asset = db.get(Asset, asset_id)
    if not asset or str(asset.tenant_id) != str(tenant_id):
        raise HTTPException(404, "Asset not found for this client")
    return asset


def require_finding(db: Session, finding_id: int, tenant_id: uuid.UUID) -> Finding:
    require_tenant(db, tenant_id)
    finding = db.get(Finding, finding_id)
    if not finding or str(finding.tenant_id) != str(tenant_id):
        raise HTTPException(404, "Finding not found for this client")
    return finding


def require_import(db: Session, import_id: uuid.UUID, tenant_id: uuid.UUID) -> ScanImport:
    require_tenant(db, tenant_id)
    scan_import = db.get(ScanImport, import_id)
    if not scan_import or str(scan_import.tenant_id) != str(tenant_id):
        raise HTTPException(404, "Import not found for this client")
    return scan_import
