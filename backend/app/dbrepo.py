"""Engine/session SQLAlchemy + repository concreto per l'ingest."""
from __future__ import annotations

from typing import Any, Iterator, Optional

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .models import (ADHealthSnapshot, Asset, Base, Finding,
                     FindingStatusHistory)
from .services.assets import identity_of, merge_asset

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_db() -> None:
    """In dev crea le tabelle mancanti; in produzione si usa db/schema.sql."""
    Base.metadata.create_all(engine)


class SqlAlchemyRepository:
    """Implementazione SQLAlchemy del protocollo FindingRepository."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------- asset
    def get_or_create_asset(self, host, tenant_id: str, environment_id: str) -> str:
        identity = identity_of(host, self._match_key(environment_id))
        if identity is None:
            raise ValueError(f"Host senza identità utilizzabile: {host!r}")

        asset = self._find_asset(tenant_id, environment_id, identity)
        if asset is None:
            asset = Asset(tenant_id=tenant_id, environment_id=environment_id,
                          ip=host.ip, fqdn=host.fqdn,
                          hostname_netbios=host.hostname_netbios, os=host.os)
            self.session.add(asset)
            self.session.flush()
            return str(asset.id)

        changes = merge_asset(asset.__dict__, host)
        for key, value in changes.items():
            setattr(asset, key, value)
        from datetime import datetime, timezone
        asset.last_seen = datetime.now(timezone.utc)
        self.session.flush()
        return str(asset.id)

    def _find_asset(self, tenant_id: str, environment_id: str, identity) -> Optional[Asset]:
        stmt = select(Asset).where(Asset.tenant_id == tenant_id,
                                   Asset.environment_id == environment_id)
        if identity.match_key == "fqdn":
            stmt = stmt.where(Asset.fqdn.ilike(identity.value))
        elif identity.match_key == "netbios":
            stmt = stmt.where(Asset.hostname_netbios.ilike(identity.value))
        else:
            stmt = stmt.where(Asset.ip == identity.value)
        return self.session.execute(stmt).scalar_one_or_none()

    def _match_key(self, environment_id: str) -> str:
        from .models import Environment
        env = self.session.get(Environment, environment_id)
        return (env.match_key if env else settings.default_match_key) or "ip"

    # ----------------------------------------------------------- findings
    def find_finding(self, environment_id: str, dedup_hash: str) -> Optional[dict[str, Any]]:
        stmt = select(Finding).where(Finding.environment_id == environment_id,
                                     Finding.dedup_hash == dedup_hash)
        row = self.session.execute(stmt).scalar_one_or_none()
        return self._to_dict(row) if row else None

    def insert_finding(self, payload: dict[str, Any]):
        finding = Finding(**payload)
        self.session.add(finding)
        self.session.flush()
        return self._to_dict(finding)

    def update_finding(self, finding_id: Any, changes: dict[str, Any]) -> None:
        finding = self.session.get(Finding, finding_id)
        for key, value in changes.items():
            setattr(finding, key, value)
        self.session.flush()

    def list_open_findings(self, environment_id: str, scanner: str,
                           asset_id: Optional[str] = None) -> list[dict[str, Any]]:
        stmt = select(Finding).where(Finding.environment_id == environment_id,
                                     Finding.scanner == scanner,
                                     Finding.status == "active")
        if asset_id:
            stmt = stmt.where(Finding.asset_id == asset_id)
        return [self._to_dict(row) for row in self.session.execute(stmt).scalars()]

    def record_status_change(self, finding_id, from_status, to_status, reason,
                             import_id, changed_by) -> None:
        self.session.add(FindingStatusHistory(
            finding_id=finding_id, from_status=from_status, to_status=to_status,
            reason=reason, import_id=import_id, changed_by=changed_by))
        self.session.flush()

    def record_ad_health(self, payload: dict[str, Any]) -> None:
        self.session.add(ADHealthSnapshot(**payload))
        self.session.flush()

    @staticmethod
    def _to_dict(row: Finding) -> dict[str, Any]:
        return {c.name: getattr(row, c.name) for c in row.__table__.columns}
