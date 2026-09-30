"""Migration regressions for db/migrations/0002_tenant_consistency.sql (#0004).

Opt-in PostgreSQL suite. The migration is executed inside a rolled-back
transaction against a database temporarily reshaped like a populated
pre-migration volume: tenant_id columns are dropped, historical child rows are
inserted without them, then the migration must backfill and constrain them
without losing rows. A second execution must be idempotent.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pytest

pytest.importorskip("sqlalchemy")
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.dbrepo import SqlAlchemyRepository
from app.models import Asset, Environment, Finding, ScanImport, Tenant
from app.parsers.base import NormalizedFinding, ParsedHost
from app.services.ingest import ingest_stream

MIGRATION = Path(__file__).resolve().parents[2] / "db" / "migrations" / "0002_tenant_consistency.sql"

CHILD_TABLES = ("asset_moves", "finding_status_history", "finding_comments")

EXPECTED_CONSTRAINTS = {
    "asset_moves": ["asset_moves_tenant_fkey", "asset_moves_asset_tenant_fkey",
                    "asset_moves_from_environment_tenant_fkey",
                    "asset_moves_to_environment_tenant_fkey"],
    "finding_status_history": ["finding_status_history_tenant_fkey",
                               "finding_status_history_finding_tenant_fkey",
                               "finding_status_history_import_tenant_fkey"],
    "finding_comments": ["finding_comments_tenant_fkey",
                         "finding_comments_finding_tenant_fkey"],
    "findings": ["findings_asset_tenant_fkey", "findings_environment_tenant_fkey",
                 "findings_last_import_tenant_fkey",
                 "findings_closed_by_import_tenant_fkey"],
    "scan_imports": ["scan_imports_environment_tenant_fkey"],
    "ad_health_snapshots": ["ad_health_environment_tenant_fkey",
                            "ad_health_asset_tenant_fkey",
                            "ad_health_import_tenant_fkey"],
}

EXPECTED_INDEXES = ["environments_id_tenant_uidx", "assets_id_tenant_uidx",
                    "scan_imports_id_tenant_uidx", "findings_id_tenant_uidx"]


@pytest.fixture
def populated_volume() -> Iterator[tuple]:
    url = os.environ.get("VCM_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set VCM_TEST_DATABASE_URL for migration tests")
    engine = create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        db = Session(bind=connection)
        try:
            tenant = Tenant(slug="migration-fixture", name="Migration fixture")
            db.add(tenant)
            db.flush()
            env = Environment(tenant_id=tenant.id, name="Production")
            db.add(env)
            db.flush()
            scan = ScanImport(tenant_id=tenant.id, environment_id=env.id,
                              scanner="tenable_nessus", filename="m.nessus",
                              content_sha256="a" * 64, storage_path="/test-only",
                              status="completed")
            db.add(scan)
            db.flush()
            ingest_stream(SqlAlchemyRepository(db), iter([ParsedHost(
                ip="192.0.2.55", findings=[NormalizedFinding(
                    kind="vulnerability", scanner="tenable_nessus", rule_id="m-rule",
                    rule_title="Migration rule", severity="high", port=443)])]),
                str(tenant.id), str(env.id), str(scan.id))
            asset = db.scalar(select(Asset).where(Asset.tenant_id == tenant.id))
            finding = db.scalar(select(Finding).where(Finding.tenant_id == tenant.id))
            db.flush()
            yield db, connection, tenant, env, scan, asset, finding
        finally:
            db.close()
            transaction.rollback()
    engine.dispose()


def test_migration_backfills_and_constrains_populated_rows(populated_volume: tuple) -> None:
    db, connection, tenant, env, scan, asset, finding = populated_volume
    script = MIGRATION.read_text()

    # Reshape like a pre-migration volume and add historical child rows.
    connection.execute(text(script))  # ensures schema_migrations exists
    for table in CHILD_TABLES:
        connection.execute(text(f"ALTER TABLE {table} DROP COLUMN tenant_id"))
    connection.execute(text(
        "INSERT INTO finding_comments (finding_id, author, body) "
        "VALUES (:finding, 'legacy', 'historical note')"), {"finding": finding.id})
    connection.execute(text(
        "INSERT INTO finding_status_history (finding_id, from_status, to_status, reason) "
        "VALUES (:finding, NULL, 'active', 'imported')"), {"finding": finding.id})
    connection.execute(text(
        "INSERT INTO asset_moves (asset_id, to_environment_id, reason) "
        "VALUES (:asset, :env, 'historical move')"),
        {"asset": asset.id, "env": env.id})
    connection.execute(text("DELETE FROM schema_migrations WHERE version = 2"))

    connection.execute(text(script))

    child_rows = {
        "asset_moves": ("asset_id", asset.id),
        "finding_status_history": ("finding_id", finding.id),
        "finding_comments": ("finding_id", finding.id),
    }
    for table, (column, parent) in child_rows.items():
        rows = connection.execute(text(
            f"SELECT tenant_id FROM {table} WHERE {column} = :parent"),
            {"parent": parent}).scalars().all()
        assert rows and all(str(value) == str(tenant.id) for value in rows), table
        nullable = connection.execute(text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = :table AND column_name = 'tenant_id'"),
            {"table": table}).scalar()
        assert nullable == "NO", table

    for table, names in EXPECTED_CONSTRAINTS.items():
        present = set(connection.execute(text(
            "SELECT conname FROM pg_constraint WHERE conrelid = CAST(:regclass AS regclass)"),
            {"regclass": table}).scalars().all())
        for name in names:
            assert name in present, f"{table}.{name}"
    present_indexes = set(connection.execute(text(
        "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema()"
    )).scalars().all())
    for name in EXPECTED_INDEXES:
        assert name in present_indexes, name
    recorded = connection.execute(text(
        "SELECT count(*) FROM schema_migrations WHERE version = 2")).scalar()
    assert recorded == 1

    # Idempotent: a second run keeps data and does not raise.
    connection.execute(text(script))
    counts = connection.execute(text(
        "SELECT (SELECT count(*) FROM finding_comments WHERE finding_id = :finding) + "
        "       (SELECT count(*) FROM finding_status_history WHERE finding_id = :finding) + "
        "       (SELECT count(*) FROM asset_moves WHERE asset_id = :asset)"),
        {"finding": finding.id, "asset": asset.id}).scalar()
    assert counts == 3

    # Composite keys reject cross-tenant child rows even with valid parents.
    other = Tenant(slug="migration-intruder", name="Intruder")
    db.add(other)
    db.flush()
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            connection.execute(text(
                "INSERT INTO finding_comments (tenant_id, finding_id, author, body) "
                "VALUES (:tenant, :finding, 'x', 'y')"),
                {"tenant": other.id, "finding": finding.id})
