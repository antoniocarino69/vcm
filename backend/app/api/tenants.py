"""API: tenant, ambienti, asset (CRUD + spostamento) — nessuna auth (fase 1)."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import cast, select, Text
from sqlalchemy.orm import Session

from ..dbrepo import SessionLocal
from ..models import Asset, AssetMove, Environment, Tenant

router = APIRouter(prefix="/api")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --------------------------------------------------------------- schemi
class TenantIn(BaseModel):
    slug: str
    name: str
    description: Optional[str] = None


class EnvironmentIn(BaseModel):
    name: str
    kind: str = "other"
    tags: dict = Field(default_factory=dict)
    match_key: str = "ip"


class AssetIn(BaseModel):
    ip: Optional[str] = None
    fqdn: Optional[str] = None
    hostname_netbios: Optional[str] = None
    os: Optional[str] = None
    criticality: int = 3
    tags: dict = Field(default_factory=dict)


class MoveIn(BaseModel):
    to_environment_id: str
    reason: Optional[str] = None


# --------------------------------------------------------------- tenants
@router.post("/tenants", status_code=201)
def create_tenant(payload: TenantIn, db: Session = Depends(get_db)):
    tenant = Tenant(**payload.model_dump())
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


@router.get("/tenants")
def list_tenants(db: Session = Depends(get_db)):
    return db.execute(select(Tenant).order_by(Tenant.name)).scalars().all()


@router.get("/tenants/{tenant_id}")
def get_tenant(tenant_id: uuid.UUID, db: Session = Depends(get_db)):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant non trovato")
    return tenant


# ----------------------------------------------------------- environments
@router.post("/tenants/{tenant_id}/environments", status_code=201)
def create_environment(tenant_id: uuid.UUID, payload: EnvironmentIn,
                       db: Session = Depends(get_db)):
    if payload.match_key not in ("ip", "fqdn", "netbios"):
        raise HTTPException(422, "match_key deve essere ip|fqdn|netbios")
    env = Environment(tenant_id=str(tenant_id), **payload.model_dump())
    db.add(env)
    db.commit()
    db.refresh(env)
    return env


@router.get("/tenants/{tenant_id}/environments")
def list_environments(tenant_id: uuid.UUID, db: Session = Depends(get_db)):
    stmt = select(Environment).where(Environment.tenant_id == tenant_id).order_by(Environment.name)
    return db.execute(stmt).scalars().all()


@router.patch("/environments/{env_id}")
def update_environment(env_id: uuid.UUID, payload: EnvironmentIn,
                       db: Session = Depends(get_db)):
    env = db.get(Environment, env_id)
    if not env:
        raise HTTPException(404, "Ambiente non trovato")
    for key, value in payload.model_dump().items():
        setattr(env, key, value)
    db.commit()
    return env


# ----------------------------------------------------------------- assets
@router.get("/environments/{env_id}/assets")
def list_assets(env_id: uuid.UUID, tag: Optional[str] = None,
                search: Optional[str] = None, db: Session = Depends(get_db)):
    stmt = select(Asset).where(Asset.environment_id == env_id)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(Asset.fqdn.ilike(pattern) | Asset.hostname_netbios.ilike(pattern)
                          | cast(Asset.ip, Text).ilike(pattern))
    rows = db.execute(stmt.order_by(Asset.ip)).scalars().all()
    if tag:
        key, _, value = tag.partition(":")
        rows = [a for a in rows if (a.tags or {}).get(key) == value] if value else \
               [a for a in rows if key in (a.tags or {})]
    return rows


@router.post("/environments/{env_id}/assets", status_code=201)
def create_asset(env_id: uuid.UUID, payload: AssetIn, db: Session = Depends(get_db)):
    env = db.get(Environment, env_id)
    if not env:
        raise HTTPException(404, "Ambiente non trovato")
    asset = Asset(tenant_id=env.tenant_id, environment_id=str(env_id),
                  **payload.model_dump())
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@router.patch("/assets/{asset_id}")
def update_asset(asset_id: uuid.UUID, payload: AssetIn, db: Session = Depends(get_db)):
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(404, "Asset non trovato")
    for key, value in payload.model_dump().items():
        setattr(asset, key, value)
    db.commit()
    return asset


@router.post("/assets/{asset_id}/move")
def move_asset(asset_id: uuid.UUID, payload: MoveIn, db: Session = Depends(get_db)):
    """Sposta l'asset in un altro ambiente preservando storico scansioni e
    commenti (findings/scan_imports mantengono environment_id dello snapshot)."""
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(404, "Asset non trovato")
    target = db.get(Environment, uuid.UUID(payload.to_environment_id))
    if not target or str(target.tenant_id) != str(asset.tenant_id):
        raise HTTPException(422, "Ambiente di destinazione non valido per questo cliente")
    if str(asset.environment_id) == payload.to_environment_id:
        raise HTTPException(422, "L'asset è già in questo ambiente")
    db.add(AssetMove(asset_id=str(asset.id),
                     from_environment_id=str(asset.environment_id),
                     to_environment_id=payload.to_environment_id,
                     reason=payload.reason))
    asset.environment_id = payload.to_environment_id
    db.commit()
    return {"asset_id": str(asset.id), "environment_id": payload.to_environment_id,
            "history_preserved": True}
