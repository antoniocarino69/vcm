"""API: tenant, ambienti, asset (CRUD + spostamento) — nessuna auth (fase 1)."""
from __future__ import annotations

import ipaddress
import re
import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AfterValidator, BaseModel, Field
from sqlalchemy import cast, select, Text
from sqlalchemy.exc import IntegrityError
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

# --------------------------------------------------------------- validation
_SLUG_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")


def _clean_slug(value: str) -> str:
    text = value.strip()
    if not _SLUG_RE.match(text):
        raise ValueError("slug must be 1-64 characters of letters, digits, "
                         "dot, dash or underscore")
    return text


def _bounded_text(value: str, field: str, max_len: int) -> str:
    text = value.strip()
    if not text:
        raise ValueError(f"{field} must not be empty")
    if len(text) > max_len:
        raise ValueError(f"{field} must be at most {max_len} characters")
    return text


def _clean_name(value: str) -> str:
    return _bounded_text(value, "name", 200)


def _clean_optional_text(value: str, field: str, max_len: int) -> str:
    if not value.strip():
        raise ValueError(f"{field} must not be blank")
    if len(value) > max_len:
        raise ValueError(f"{field} must be at most {max_len} characters")
    return value


def _clean_tags(value: dict[str, str]) -> dict[str, str]:
    for key, item in value.items():
        if not key.strip() or len(key) > 100:
            raise ValueError("tag keys must be 1-100 characters")
        if len(item) > 500:
            raise ValueError("tag values must be at most 500 characters")
    return value


def _clean_ip(value: str) -> str:
    """An asset identity is a single address, never a network or hostname."""
    text = value.strip()
    try:
        ipaddress.ip_address(text)
    except ValueError as exc:
        raise ValueError("ip must be a single IPv4 or IPv6 address") from exc
    return text


Slug = Annotated[str, AfterValidator(_clean_slug)]
Name = Annotated[str, AfterValidator(_clean_name)]
Description = Annotated[str, AfterValidator(
    lambda v: _clean_optional_text(v, "description", 2000))]
Tags = Annotated[dict[str, str], AfterValidator(_clean_tags)]
IpValue = Annotated[str, AfterValidator(_clean_ip)]
Criticality = Annotated[int, Field(ge=1, le=5)]
EnvironmentKind = Literal["production", "dmz", "active_directory", "staging",
                          "cloud", "ot", "other"]
MatchKey = Literal["ip", "fqdn", "netbios"]

# --------------------------------------------------------------- schemi
class TenantIn(BaseModel):
    slug: Slug
    name: Name
    description: Optional[Description] = None


class TenantPatch(BaseModel):
    """Partial edit: only the fields explicitly present are applied."""
    slug: Optional[Slug] = None
    name: Optional[Name] = None
    description: Optional[Description] = None


class EnvironmentIn(BaseModel):
    name: Name
    kind: EnvironmentKind = "other"
    tags: Tags = Field(default_factory=dict)
    match_key: MatchKey = "ip"


class EnvironmentPatch(BaseModel):
    name: Optional[Name] = None
    kind: Optional[EnvironmentKind] = None
    tags: Optional[Tags] = None
    match_key: Optional[MatchKey] = None


class AssetIn(BaseModel):
    ip: Optional[IpValue] = None
    fqdn: Optional[str] = Field(None, max_length=255)
    hostname_netbios: Optional[str] = Field(None, max_length=255)
    os: Optional[str] = Field(None, max_length=500)
    criticality: Criticality = 3
    tags: Tags = Field(default_factory=dict)


class AssetPatch(BaseModel):
    ip: Optional[IpValue] = None
    fqdn: Optional[str] = Field(None, max_length=255)
    hostname_netbios: Optional[str] = Field(None, max_length=255)
    os: Optional[str] = Field(None, max_length=500)
    criticality: Optional[Criticality] = None
    tags: Optional[Tags] = None


class MoveIn(BaseModel):
    to_environment_id: uuid.UUID
    reason: Optional[str] = None


def _changes(payload: BaseModel) -> dict:
    """Apply only fields the caller actually sent (partial PATCH contract)."""
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, "No updatable fields provided")
    return changes


def _apply(target: object, changes: dict) -> None:
    for key, value in changes.items():
        setattr(target, key, value)
    target.updated_at = datetime.now(timezone.utc)  # type: ignore[attr-defined]


# --------------------------------------------------------------- tenants
@router.post("/tenants", status_code=201)
def create_tenant(payload: TenantIn, db: Session = Depends(get_db)):
    if db.execute(select(Tenant.id).where(Tenant.slug == payload.slug)).first():
        raise HTTPException(409, "A client with this slug already exists")
    tenant = Tenant(**payload.model_dump())
    db.add(tenant)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A client with this slug already exists")
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


@router.patch("/tenants/{tenant_id}")
def update_tenant(tenant_id: uuid.UUID, payload: TenantPatch,
                  db: Session = Depends(get_db)):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Client not found")
    changes = _changes(payload)
    if "slug" in changes and db.execute(select(Tenant.id).where(
            Tenant.slug == changes["slug"], Tenant.id != tenant_id)).first():
        raise HTTPException(409, "A client with this slug already exists")
    _apply(tenant, changes)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A client with this slug already exists")
    db.refresh(tenant)
    return tenant


# ----------------------------------------------------------- environments
@router.post("/tenants/{tenant_id}/environments", status_code=201)
def create_environment(tenant_id: uuid.UUID, payload: EnvironmentIn,
                       db: Session = Depends(get_db)):
    if not db.get(Tenant, tenant_id):
        raise HTTPException(404, "Client not found")
    if db.execute(select(Environment.id).where(
            Environment.tenant_id == tenant_id,
            Environment.name == payload.name)).first():
        raise HTTPException(409, "An environment with this name already exists "
                                 "for this client")
    env = Environment(tenant_id=str(tenant_id), **payload.model_dump())
    db.add(env)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An environment with this name already exists "
                                 "for this client")
    db.refresh(env)
    return env


@router.get("/tenants/{tenant_id}/environments")
def list_environments(tenant_id: uuid.UUID, db: Session = Depends(get_db)):
    stmt = select(Environment).where(Environment.tenant_id == tenant_id).order_by(Environment.name)
    return db.execute(stmt).scalars().all()


@router.patch("/environments/{env_id}")
def update_environment(env_id: uuid.UUID, payload: EnvironmentPatch,
                       db: Session = Depends(get_db)):
    env = db.get(Environment, env_id)
    if not env:
        raise HTTPException(404, "Ambiente non trovato")
    changes = _changes(payload)
    if "name" in changes and db.execute(select(Environment.id).where(
            Environment.tenant_id == env.tenant_id,
            Environment.name == changes["name"],
            Environment.id != env_id)).first():
        raise HTTPException(409, "An environment with this name already exists "
                                 "for this client")
    _apply(env, changes)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An environment with this name already exists "
                                 "for this client")
    db.refresh(env)
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
def update_asset(asset_id: uuid.UUID, payload: AssetPatch,
                 db: Session = Depends(get_db)):
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(404, "Asset non trovato")
    _apply(asset, _changes(payload))
    db.commit()
    db.refresh(asset)
    return asset


@router.post("/assets/{asset_id}/move")
def move_asset(asset_id: uuid.UUID, payload: MoveIn, db: Session = Depends(get_db)):
    """Sposta l'asset in un altro ambiente preservando storico scansioni e
    commenti (findings/scan_imports mantengono environment_id dello snapshot)."""
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(404, "Asset non trovato")
    target = db.get(Environment, payload.to_environment_id)
    if not target or str(target.tenant_id) != str(asset.tenant_id):
        raise HTTPException(422, "Ambiente di destinazione non valido per questo cliente")
    if str(asset.environment_id) == str(payload.to_environment_id):
        raise HTTPException(422, "L'asset è già in questo ambiente")
    db.add(AssetMove(asset_id=str(asset.id),
                     from_environment_id=str(asset.environment_id),
                     to_environment_id=str(payload.to_environment_id),
                     reason=payload.reason))
    asset.environment_id = str(payload.to_environment_id)
    db.commit()
    return {"asset_id": str(asset.id),
            "environment_id": str(payload.to_environment_id),
            "history_preserved": True}
