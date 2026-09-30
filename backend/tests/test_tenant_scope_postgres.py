"""Two-tenant scope regressions for findings, imports and management routes.

Opt-in PostgreSQL suite (VCM_TEST_DATABASE_URL). Routes are exercised through
the FastAPI test client so HTTP semantics (422 missing scope, 404 hidden
cross-client targets) are verified exactly as the portal sees them (#0004).
"""
from __future__ import annotations

import os
import uuid
from typing import Iterator

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.tenants import get_db
from app.dbrepo import SqlAlchemyRepository
from app.main import app
from app.models import (Asset, AssetMove, Environment, Finding,
                        FindingComment, FindingStatusHistory, ScanImport, Tenant)
from app.parsers.base import NormalizedFinding, ParsedHost
from app.services.ingest import ingest_stream


@pytest.fixture
def two_tenants() -> Iterator[tuple]:
    url = os.environ.get("VCM_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set VCM_TEST_DATABASE_URL for tenant scope tests")
    engine = create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        db = Session(bind=connection)
        try:
            data = {}
            for label, address in (("a", "192.0.2.1"), ("b", "192.0.2.2")):
                tenant = Tenant(slug=f"scope-{label}-{uuid.uuid4().hex}",
                                name=f"Scope {label}")
                db.add(tenant)
                db.flush()
                env = Environment(tenant_id=tenant.id, name="Production")
                db.add(env)
                db.flush()
                extra_env = Environment(tenant_id=tenant.id, name="DMZ")
                db.add(extra_env)
                scan = ScanImport(tenant_id=tenant.id, environment_id=env.id,
                                  scanner="tenable_nessus", filename=f"{label}.nessus",
                                  content_sha256=uuid.uuid4().hex * 2,
                                  storage_path="/test-only", status="completed")
                db.add(scan)
                db.flush()
                ingest_stream(SqlAlchemyRepository(db), iter([ParsedHost(
                    ip=address, findings=[
                        NormalizedFinding(kind="vulnerability", scanner="tenable_nessus",
                                          rule_id="shared-rule", rule_title="Shared rule",
                                          severity="high", port=443),
                        NormalizedFinding(kind="vulnerability", scanner="tenable_nessus",
                                          rule_id="port-22", rule_title="SSH",
                                          severity="low", port=22)])]),
                    str(tenant.id), str(env.id), str(scan.id))
                asset = db.scalar(select(Asset).where(Asset.tenant_id == tenant.id))
                findings = db.execute(select(Finding).where(
                    Finding.tenant_id == tenant.id).order_by(Finding.id)).scalars().all()
                data[label] = {"tenant": tenant, "env": env, "extra_env": extra_env,
                               "scan": scan, "asset": asset, "findings": findings}
            db.flush()
            app.dependency_overrides[get_db] = lambda: db
            client = TestClient(app)
            yield db, data, client
        finally:
            app.dependency_overrides.clear()
            db.close()
            transaction.rollback()
    engine.dispose()


def test_reads_require_and_enforce_tenant(two_tenants: tuple) -> None:
    db, data, client = two_tenants
    a, b = data["a"], data["b"]

    assert client.get("/api/findings").status_code == 422
    page = client.get("/api/findings", params={"tenant_id": a["tenant"].id}).json()
    assert {row["id"] for row in page["items"]} == {f.id for f in a["findings"]}
    assert page["total"] == len(a["findings"])

    assert client.get(f"/api/findings/{b['findings'][0].id}",
                      params={"tenant_id": a["tenant"].id}).status_code == 404
    detail = client.get(f"/api/findings/{a['findings'][0].id}",
                        params={"tenant_id": a["tenant"].id})
    assert detail.status_code == 200
    assert detail.json()["finding"]["id"] == a["findings"][0].id

    assert client.get(f"/api/imports/{b['scan'].id}",
                      params={"tenant_id": a["tenant"].id}).status_code == 404
    assert client.get(f"/api/imports/{b['scan'].id}",
                      params={"tenant_id": b["tenant"].id}).status_code == 200

    assert client.get(f"/api/environments/{b['env'].id}/imports",
                      params={"tenant_id": a["tenant"].id}).status_code == 404
    listing = client.get(f"/api/environments/{a['env'].id}/imports",
                         params={"tenant_id": a["tenant"].id}).json()
    assert [row["id"] for row in listing] == [str(a["scan"].id)]

    assert client.get(f"/api/environments/{b['env'].id}/assets",
                      params={"tenant_id": a["tenant"].id}).status_code == 404
    assert client.get("/api/imports/{}".format(uuid.uuid4()),
                      params={"tenant_id": a["tenant"].id}).status_code == 404


def test_mutations_enforce_tenant(two_tenants: tuple) -> None:
    db, data, client = two_tenants
    a, b = data["a"], data["b"]
    finding_b = next(f for f in b["findings"] if f.rule_id == "shared-rule")

    response = client.post(f"/api/findings/{finding_b.id}/status",
                           params={"tenant_id": a["tenant"].id},
                           json={"status": "risk_accepted", "reason": "Cross client"})
    assert response.status_code == 404
    db.refresh(finding_b)
    assert finding_b.status == "active"

    response = client.post(f"/api/findings/{finding_b.id}/status",
                           params={"tenant_id": b["tenant"].id},
                           json={"status": "risk_accepted", "reason": "Accepted for test",
                                 "risk_accepted_until": "2027-01-01"})
    assert response.status_code == 200

    assert client.post(f"/api/findings/{a['findings'][0].id}/comments",
                       params={"tenant_id": b["tenant"].id},
                       json={"body": "wrong client"}).status_code == 404
    response = client.post(f"/api/findings/{a['findings'][0].id}/comments",
                           params={"tenant_id": a["tenant"].id},
                           json={"author": "ops", "body": "checked"})
    assert response.status_code == 201

    assert client.patch(f"/api/assets/{b['asset'].id}",
                        params={"tenant_id": a["tenant"].id},
                        json={"os": "x"}).status_code == 404
    assert client.patch(f"/api/environments/{b['env'].id}",
                        params={"tenant_id": a["tenant"].id},
                        json={"name": "x"}).status_code == 404
    assert client.post(f"/api/environments/{b['env'].id}/assets",
                       params={"tenant_id": a["tenant"].id},
                       json={"ip": "192.0.2.99"}).status_code == 404

    response = client.post(f"/api/assets/{b['asset'].id}/move",
                           params={"tenant_id": a["tenant"].id},
                           json={"to_environment_id": str(a["env"].id)})
    assert response.status_code == 404
    assert db.execute(select(AssetMove).where(
        AssetMove.asset_id == b["asset"].id)).scalars().all() == []
    # With the right scope, a cross-client target is still rejected.
    response = client.post(f"/api/assets/{b['asset'].id}/move",
                           params={"tenant_id": b["tenant"].id},
                           json={"to_environment_id": str(a["env"].id)})
    assert response.status_code == 422

    response = client.post(f"/api/environments/{b['env'].id}/imports",
                           files={"file": ("x.nessus", b"<NessusClientData_v2/>")},
                           data={"scanner": "auto",
                                 "tenant_id": str(a["tenant"].id)})
    assert response.status_code == 404

    assert client.get("/api/reports/executive",
                      params={"tenant_id": a["tenant"].id,
                              "environment_id": b["env"].id}).status_code == 404
    assert client.get("/api/dashboard",
                      params={"tenant_id": a["tenant"].id,
                              "environment_id": b["env"].id}).status_code == 404
    assert client.get("/api/dashboard/compliance",
                      params={"tenant_id": a["tenant"].id,
                              "environment_id": b["env"].id}).status_code == 404


def test_child_rows_carry_tenant_and_reject_mismatch(two_tenants: tuple) -> None:
    db, data, client = two_tenants
    a, b = data["a"], data["b"]
    finding = a["findings"][0]

    assert client.post(f"/api/findings/{finding.id}/status",
                       params={"tenant_id": a["tenant"].id},
                       json={"status": "false_positive", "reason": "Checked manually"},
                       ).status_code == 200
    assert client.post(f"/api/findings/{finding.id}/comments",
                       params={"tenant_id": a["tenant"].id},
                       json={"author": "ops", "body": "evidence reviewed"}).status_code == 201
    response = client.post(f"/api/assets/{a['asset'].id}/move",
                           params={"tenant_id": a["tenant"].id},
                           json={"to_environment_id": str(a["extra_env"].id),
                                 "reason": "relocated"})
    assert response.status_code == 200

    history = db.execute(select(FindingStatusHistory).where(
        FindingStatusHistory.finding_id == finding.id)).scalars().all()
    assert history and all(row.tenant_id == a["tenant"].id for row in history)
    comments = db.execute(select(FindingComment).where(
        FindingComment.finding_id == finding.id)).scalars().all()
    assert comments and all(row.tenant_id == a["tenant"].id for row in comments)
    moves = db.execute(select(AssetMove).where(
        AssetMove.asset_id == a["asset"].id)).scalars().all()
    assert moves and all(row.tenant_id == a["tenant"].id for row in moves)

    for statement, params in (
            ("INSERT INTO finding_comments (tenant_id, finding_id, author, body) "
             "VALUES (:tenant, :finding, 'x', 'y')",
             {"tenant": b["tenant"].id, "finding": finding.id}),
            ("INSERT INTO finding_status_history (tenant_id, finding_id, to_status) "
             "VALUES (:tenant, :finding, 'active')",
             {"tenant": b["tenant"].id, "finding": finding.id}),
            ("INSERT INTO asset_moves (tenant_id, asset_id, to_environment_id) "
             "VALUES (:tenant, :asset, :env)",
             {"tenant": b["tenant"].id, "asset": a["asset"].id,
              "env": a["extra_env"].id})):
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.execute(text(statement), params)
