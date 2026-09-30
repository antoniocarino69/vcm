"""Read-only asset inventory with explicit tenant scope and bounded history views."""
from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, Text, and_, cast, func, or_, select
from sqlalchemy.orm import Session, aliased

from ..models import Asset, AssetMove, Environment, Finding, ScanImport, Tenant
from .tenants import get_db

router = APIRouter(prefix='/api/assets')
PageLimit = Annotated[int, Query(ge=1, le=200)]
PageOffset = Annotated[int, Query(ge=0)]
AssetSort = Literal['ip', 'fqdn', 'os', 'environment', 'criticality', 'last_seen', 'open_findings']


def _scope(db: Session, tenant_id: uuid.UUID, environment_id: uuid.UUID | None = None) -> None:
    """Validate the requested infrastructure boundary before querying assets."""
    if not db.scalar(select(Tenant.id).where(Tenant.id == tenant_id)):
        raise HTTPException(404, 'Client not found')
    if environment_id and not db.scalar(select(Environment.id).where(
            Environment.id == environment_id, Environment.tenant_id == tenant_id)):
        raise HTTPException(404, 'Environment not found for this client')


def _inventory(tenant_id: uuid.UUID) -> Select:
    """Count active findings across this asset's retained environment snapshots."""
    counts = select(
        Finding.asset_id,
        func.count().label('open_findings'),
        func.count().filter(Finding.severity.in_(['critical', 'high'])).label('open_critical_high'),
    ).join(Environment, and_(Environment.id == Finding.environment_id, Environment.tenant_id == tenant_id)).where(Finding.tenant_id == tenant_id, Finding.status == 'active').group_by(Finding.asset_id).subquery()
    return select(
        Asset.id, Asset.tenant_id, Asset.environment_id, Asset.ip, Asset.fqdn,
        Asset.hostname_netbios, Asset.os, Asset.criticality, Asset.tags,
        Asset.first_seen, Asset.last_seen, Environment.name.label('environment_name'),
        Environment.kind.label('environment_kind'),
        func.coalesce(counts.c.open_findings, 0).label('open_findings'),
        func.coalesce(counts.c.open_critical_high, 0).label('open_critical_high'),
    ).join(Environment, and_(Environment.id == Asset.environment_id, Environment.tenant_id == tenant_id))\
        .outerjoin(counts, counts.c.asset_id == Asset.id).where(Asset.tenant_id == tenant_id)


def _page(db: Session, stmt: Select, limit: int, offset: int) -> dict[str, Any]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = db.execute(stmt.limit(limit).offset(offset)).mappings().all()
    return {'items': [dict(row) for row in rows], 'total': total, 'limit': limit, 'offset': offset}


def _literal_like(value: str) -> str:
    """Treat user search text literally, including SQL wildcard characters."""
    return '%' + value.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'


@router.get('')
def inventory(
    tenant_id: uuid.UUID,
    environment_id: uuid.UUID | None = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    os_search: Annotated[str | None, Query(max_length=200)] = None,
    os_family: Literal['windows', 'linux', 'unknown'] | None = None,
    tag: Annotated[list[str] | None, Query(max_length=20)] = None,
    sort: AssetSort = 'ip',
    direction: Literal['asc', 'desc'] = 'asc',
    limit: PageLimit = 50,
    offset: PageOffset = 0,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Filter current asset attributes before stable, tenant-scoped pagination."""
    _scope(db, tenant_id, environment_id)
    stmt = _inventory(tenant_id)
    if environment_id:
        stmt = stmt.where(Asset.environment_id == environment_id)
    if search and search.strip():
        pattern = _literal_like(search)
        stmt = stmt.where(or_(Asset.fqdn.ilike(pattern, escape='\\'),
                              Asset.hostname_netbios.ilike(pattern, escape='\\'),
                              cast(Asset.ip, Text).ilike(pattern, escape='\\')))
    if os_search and os_search.strip():
        stmt = stmt.where(Asset.os.ilike(_literal_like(os_search), escape='\\'))
    if os_family == 'unknown':
        stmt = stmt.where(or_(Asset.os.is_(None), func.btrim(Asset.os, ' \t\r\n') == ''))
    elif os_family == 'linux':
        stmt = stmt.where(Asset.os.op('~*')(r'\m(linux|ubuntu|debian|rhel|red hat|centos|fedora|rocky linux|almalinux|suse|opensuse)\M'))
    elif os_family == 'windows':
        stmt = stmt.where(Asset.os.ilike('%windows%'))
    for label in tag or []:
        if not label.strip() or len(label) > 200:
            raise HTTPException(422, 'Asset tags must contain 1 to 200 characters')
        key, separator, value = label.partition(':')
        stmt = stmt.where(Asset.tags[key].as_string() == value if separator else Asset.tags.has_key(key))
    columns = {'environment': Environment.name, 'open_findings': stmt.selected_columns.open_findings}
    order = columns[sort] if sort in columns else getattr(Asset, sort)
    stmt = stmt.order_by((order.desc() if direction == 'desc' else order.asc()).nulls_last(), Asset.id.asc())
    return _page(db, stmt, limit, offset)


@router.get('/{asset_id}')
def get_asset(asset_id: uuid.UUID, tenant_id: uuid.UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Return an asset only when both its client and current environment agree."""
    row = db.execute(_inventory(tenant_id).where(Asset.id == asset_id)).mappings().first()
    if not row:
        raise HTTPException(404, 'Asset not found for this client')
    return dict(row)


@router.get('/{asset_id}/findings')
def asset_findings(asset_id: uuid.UUID, tenant_id: uuid.UUID,
                   limit: PageLimit = 50, offset: PageOffset = 0,
                   db: Session = Depends(get_db)) -> dict[str, Any]:
    """Retain finding snapshot environments, independently of the current asset location."""
    get_asset(asset_id, tenant_id, db)
    stmt = select(Finding.id, Finding.environment_id, Environment.name.label('environment_name'),
                  Finding.kind, Finding.scanner, Finding.rule_id, Finding.rule_title,
                  Finding.severity, Finding.status, Finding.port, Finding.protocol,
                  Finding.first_seen, Finding.last_seen).join(Environment, and_(
                      Environment.id == Finding.environment_id, Environment.tenant_id == tenant_id))\
        .where(Finding.tenant_id == tenant_id, Finding.asset_id == asset_id)\
        .order_by(Finding.last_seen.desc(), Finding.id.desc())
    return _page(db, stmt, limit, offset)


@router.get('/{asset_id}/moves')
def asset_moves(asset_id: uuid.UUID, tenant_id: uuid.UUID,
                limit: PageLimit = 50, offset: PageOffset = 0,
                db: Session = Depends(get_db)) -> dict[str, Any]:
    """Resolve movement environments under the owning asset's client scope."""
    get_asset(asset_id, tenant_id, db)
    previous, target = aliased(Environment), aliased(Environment)
    stmt = select(AssetMove.id, AssetMove.moved_at, AssetMove.reason,
                  previous.id.label('from_environment_id'), previous.name.label('from_environment_name'),
                  target.id.label('to_environment_id'), target.name.label('to_environment_name'))\
        .join(Asset, and_(Asset.id == AssetMove.asset_id, Asset.tenant_id == tenant_id))\
        .join(target, and_(target.id == AssetMove.to_environment_id, target.tenant_id == tenant_id))\
        .outerjoin(previous, and_(previous.id == AssetMove.from_environment_id, previous.tenant_id == tenant_id))\
        .where(AssetMove.asset_id == asset_id).order_by(AssetMove.moved_at.desc(), AssetMove.id.desc())
    return _page(db, stmt, limit, offset)


@router.get('/{asset_id}/imports')
def asset_imports(asset_id: uuid.UUID, tenant_id: uuid.UUID,
                  limit: PageLimit = 50, offset: PageOffset = 0,
                  db: Session = Depends(get_db)) -> dict[str, Any]:
    """Show proven latest/closure references, never reconstruct missing observations."""
    get_asset(asset_id, tenant_id, db)
    referenced = select(Finding.id).where(
        Finding.asset_id == asset_id, Finding.tenant_id == tenant_id,
        or_(Finding.last_import_id == ScanImport.id, Finding.closed_by_import_id == ScanImport.id),
    ).exists()
    stmt = select(ScanImport.id, ScanImport.environment_id, Environment.name.label('environment_name'),
                  ScanImport.filename, ScanImport.scanner, ScanImport.status, ScanImport.created_at)\
        .join(Environment, and_(Environment.id == ScanImport.environment_id, Environment.tenant_id == tenant_id))\
        .where(ScanImport.tenant_id == tenant_id, referenced)\
        .order_by(ScanImport.created_at.desc(), ScanImport.id.desc())
    result = _page(db, stmt, limit, offset)
    result['coverage'] = 'latest_and_closure_references_only'
    return result
