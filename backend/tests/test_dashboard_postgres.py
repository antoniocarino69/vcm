"""Regressioni dashboard/report su PostgreSQL, isolate in una transazione.

Esecuzione opt-in: VCM_TEST_DATABASE_URL=<url PostgreSQL> python -m pytest ...
Non richiedono un database per la normale suite parser/ingest.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Iterator

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.dashboards import dashboard
from app.api.reports import _bundle
from app.dbrepo import SqlAlchemyRepository
from app.models import ADHealthSnapshot, Environment, ScanImport, Tenant
from app.parsers.base import NormalizedFinding, ParsedHost
from app.services.ingest import ingest_stream


@pytest.fixture
def scoped_data() -> Iterator[tuple[Session, list[Tenant], list[Environment]]]:
    """Crea due clienti e tre ambienti senza rendere persistenti i dati di test."""
    url = os.environ.get("VCM_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Impostare VCM_TEST_DATABASE_URL per la regressione PostgreSQL")
    engine = create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection)
        try:
            tenants = [Tenant(slug=f"review-{uuid.uuid4().hex}", name=f"Review {n}")
                       for n in range(2)]
            session.add_all(tenants)
            session.flush()
            envs = [Environment(tenant_id=tenants[n].id, name=f"Review env {i}")
                    for i, n in enumerate((0, 0, 1))]
            session.add_all(envs)
            session.flush()
            now = datetime.now(timezone.utc)
            for i, env in enumerate(envs):
                scan = ScanImport(tenant_id=env.tenant_id, environment_id=env.id,
                                  scanner="tenable_nessus", filename="fixture.nessus",
                                  content_sha256=f"{i:064x}", storage_path="/test-only")
                session.add(scan)
                session.flush()
                finding = NormalizedFinding(
                    kind="vulnerability", scanner="tenable_nessus",
                    rule_id=f"scope-{i}", rule_title=f"Scope rule {i}", severity="high")
                ingest_stream(SqlAlchemyRepository(session), iter([
                    ParsedHost(ip=f"192.0.2.{i + 1}", findings=[finding])]),
                    str(env.tenant_id), str(env.id), str(scan.id))
                # Ripetizioni recenti non devono nascondere altri ambienti/tool.
                for sample in range(2 if i == 1 else 25):
                    session.add(ADHealthSnapshot(
                        tenant_id=env.tenant_id, environment_id=env.id,
                        tool="pingcastle", global_score=10 * (i + 1) + sample,
                        snapshot_at=now + timedelta(seconds=(100 if i == 1 else 300 + i * 100) + sample)))
            session.flush()
            yield session, tenants, envs
        finally:
            session.close()
            transaction.rollback()
    engine.dispose()


@pytest.mark.parametrize("scope", ["tenant", "environment", "both", "mismatch"])
def test_dashboard_scopes_every_section(scoped_data, scope: str) -> None:
    """Top host e postura AD rispettano anche scope ambiente e combinazioni vuote."""
    session, tenants, envs = scoped_data
    tenant_id = tenants[0].id if scope != "environment" else None
    environment_id = None if scope == "tenant" else envs[2 if scope == "mismatch" else 0].id
    expected = {0, 1} if scope == "tenant" else (set() if scope == "mismatch" else {0})
    result = dashboard(tenant_id=tenant_id, environment_id=environment_id, db=session)
    assert {host["ip"] for host in result["top_hosts"]} == {
        f"192.0.2.{i + 1}" for i in expected}
    assert {row["rule_id"] for row in result["top_rules"]} == {f"scope-{i}" for i in expected}
    assert {row["environment_id"] for row in result["ad_health"]} == {
        str(envs[i].id) for i in expected}
    assert {row["global_score"] for row in result["ad_health"]} == {
        (34 if i == 0 else 21) for i in expected}
    assert result["totals"]["active"] == len(expected)


def test_report_bundle_preserves_scope(scoped_data) -> None:
    """Il report Executive riceve solo score del cliente e ambiente richiesti."""
    session, tenants, envs = scoped_data
    result = _bundle(tenants[0].id, envs[0].id, session)
    assert {host["ip"] for host in result["hosts"]} == {"192.0.2.1"}
    assert {host["ip"] for host in result["top_hosts"]} == {"192.0.2.1"}
    assert len(result["ad_health"]) == 1
    assert result["ad_health"][0]["global_score"] == 34
