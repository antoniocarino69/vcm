"""Individual finding workflow regressions (#0014).

Opt-in PostgreSQL suite (VCM_TEST_DATABASE_URL). Covers the vulnerability list
contract (enriched paginated rows, filters applied before pagination), the
individual finding detail (asset context, provenance imports, history,
comments) and the decision unit: one decision applies to one finding of one
asset and one port — the same rule on another asset or another port must not
change.
"""
from __future__ import annotations

import os
import uuid
from typing import Iterator

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.tenants import get_db
from app.dbrepo import SqlAlchemyRepository
from app.main import app
from app.models import Environment, Finding, FindingStatusHistory, ScanImport, Tenant
from app.parsers.base import NormalizedFinding, ParsedHost
from app.services.ingest import ingest_stream

RULE = "shared-rule-42"


@pytest.fixture
def workflow() -> Iterator[tuple]:
    url = os.environ.get("VCM_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set VCM_TEST_DATABASE_URL for finding workflow tests")
    engine = create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        db = Session(bind=connection)
        try:
            data = {}
            for label, base in (("a", "192.0.2.1"), ("b", "192.0.2.2")):
                tenant = Tenant(slug=f"workflow-{label}-{uuid.uuid4().hex}",
                                name=f"Workflow {label}")
                db.add(tenant)
                db.flush()
                env = Environment(tenant_id=tenant.id, name="Production")
                db.add(env)
                db.flush()
                scan = ScanImport(tenant_id=tenant.id, environment_id=env.id,
                                  scanner="tenable_nessus", filename=f"{label}.nessus",
                                  content_sha256=uuid.uuid4().hex * 2,
                                  storage_path="/test-only", status="completed")
                db.add(scan)
                db.flush()
                # One asset, same rule on two ports: decisions are per port.
                ingest_stream(SqlAlchemyRepository(db), iter([ParsedHost(
                    ip=base, os="Windows Server 2022",
                    findings=[
                        NormalizedFinding(kind="vulnerability", scanner="tenable_nessus",
                                          rule_id=RULE, rule_title="Shared TLS weakness",
                                          severity="high", port=443, protocol="tcp",
                                          cves=["CVE-2026-0001"]),
                        NormalizedFinding(kind="vulnerability", scanner="tenable_nessus",
                                          rule_id=RULE, rule_title="Shared TLS weakness",
                                          severity="high", port=8443, protocol="tcp",
                                          cves=["CVE-2026-0001"]),
                    ])]), str(tenant.id), str(env.id), str(scan.id))
                findings = db.scalars(select(Finding).where(
                    Finding.tenant_id == tenant.id).order_by(Finding.port)).all()
                data[label] = {"tenant": tenant, "env": env, "scan": scan,
                               "findings": findings}
            db.flush()
            app.dependency_overrides[get_db] = lambda: db
            client = TestClient(app)
            yield db, data, client
            app.dependency_overrides.clear()
        finally:
            db.close()
            transaction.rollback()
    engine.dispose()


def _by_port(entry: dict, port: int) -> Finding:
    return next(f for f in entry["findings"] if f.port == port)


def test_list_rows_carry_asset_and_environment_context(workflow: tuple) -> None:
    db, data, client = workflow
    a = data["a"]
    response = client.get("/api/findings", params={"tenant_id": a["tenant"].id})
    assert response.status_code == 200
    page = response.json()
    assert set(page) == {"items", "total", "limit", "offset"}
    assert page["total"] == 2
    row = page["items"][0]
    for key in ("id", "environment_name", "asset_id", "asset_os", "asset_tags",
                "rule_id", "rule_title", "cves", "severity", "severity_raw",
                "status", "scanner", "port", "protocol", "first_seen", "last_seen"):
        assert key in row, key
    assert row["environment_name"] == "Production"
    assert row["asset_os"] == "Windows Server 2022"
    assert row["rule_id"] == RULE
    assert row["cves"] == ["CVE-2026-0001"]


def test_filters_apply_before_pagination(workflow: tuple) -> None:
    db, data, client = workflow
    a = data["a"]
    base = {"tenant_id": a["tenant"].id}
    page = client.get("/api/findings", params={**base, "severity": ["low"]}).json()
    assert page["total"] == 0 and page["items"] == []
    page = client.get("/api/findings", params={**base, "severity": ["high"]}).json()
    assert page["total"] == 2
    page = client.get("/api/findings", params={**base, "search": "TLS"}).json()
    assert page["total"] == 2
    page = client.get("/api/findings", params={**base, "search": "nothing-here"}).json()
    assert page["total"] == 0
    # limit slices the filtered set; total still reports the filtered count
    page = client.get("/api/findings", params={**base, "limit": 1}).json()
    assert page["total"] == 2 and len(page["items"]) == 1
    # compliance filter: no compliance rows exist yet
    page = client.get("/api/findings", params={**base, "kind": "compliance"}).json()
    assert page["total"] == 0


def test_decision_reaches_one_asset_one_port(workflow: tuple) -> None:
    db, data, client = workflow
    a, b = data["a"], data["b"]
    target = _by_port(a, 443)
    response = client.post(f"/api/findings/{target.id}/status",
                           params={"tenant_id": a["tenant"].id},
                           json={"status": "risk_accepted", "reason": "Compensating control",
                                 "risk_accepted_until": "2027-06-30", "changed_by": "analyst"})
    assert response.status_code == 200
    db.refresh(target)
    assert target.status == "risk_accepted"
    assert target.status_reason == "Compensating control"

    same_asset_other_port = _by_port(a, 8443)
    db.refresh(same_asset_other_port)
    assert same_asset_other_port.status == "active"
    assert same_asset_other_port.status_reason is None

    other_asset_same_rule = _by_port(b, 443)
    db.refresh(other_asset_same_rule)
    assert other_asset_same_rule.status == "active"
    assert other_asset_same_rule.status_reason is None

    history = db.scalars(select(FindingStatusHistory).where(
        FindingStatusHistory.tenant_id == a["tenant"].id)).all()
    assert [row.finding_id for row in history] == [target.id]


def test_risk_acceptance_requires_reason(workflow: tuple) -> None:
    db, data, client = workflow
    target = _by_port(data["a"], 8443)
    response = client.post(f"/api/findings/{target.id}/status",
                           params={"tenant_id": data["a"]["tenant"].id},
                           json={"status": "risk_accepted"})
    assert response.status_code == 422
    db.refresh(target)
    assert target.status == "active"


def test_detail_exposes_context_provenance_history_and_comments(workflow: tuple) -> None:
    db, data, client = workflow
    a = data["a"]
    target = _by_port(a, 443)
    assert client.post(f"/api/findings/{target.id}/status",
                       params={"tenant_id": a["tenant"].id},
                       json={"status": "mitigated", "reason": "Patched 2026-10",
                             "changed_by": "ops"}).status_code == 200
    assert client.post(f"/api/findings/{target.id}/comments",
                       params={"tenant_id": a["tenant"].id},
                       json={"author": "ops", "body": "Patch verified"}).status_code == 201

    detail = client.get(f"/api/findings/{target.id}",
                        params={"tenant_id": a["tenant"].id}).json()
    assert detail["finding"]["id"] == target.id
    assert detail["asset"]["os"] == "Windows Server 2022"
    assert detail["environment"]["name"] == "Production"
    assert detail["provenance"]["last_import"]["filename"] == "a.nessus"
    assert detail["provenance"]["last_import"]["id"] == str(a["scan"].id)
    assert [row["body"] for row in detail["comments"]] == ["Patch verified"]
    assert detail["history"][0]["to_status"] == "mitigated"
    assert detail["history"][0]["reason"] == "Patched 2026-10"
