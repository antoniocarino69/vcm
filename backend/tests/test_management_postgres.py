"""Partial PATCH contract regressions for clients, environments and assets.

Opt-in PostgreSQL suite (VCM_TEST_DATABASE_URL) rolled back like the other
*_postgres regressions. Covers #0009: partial edits must not reset omitted
fields, conflicts and invalid values must produce meaningful 4xx errors.
"""
from __future__ import annotations

import os
import uuid
from typing import Iterator

import pytest

pytest.importorskip("sqlalchemy")
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.tenants import (AssetIn, AssetPatch, EnvironmentIn, EnvironmentPatch,
                             TenantIn, TenantPatch, create_asset, create_environment,
                             create_tenant, update_asset, update_environment,
                             update_tenant)
from app.models import Asset, Environment, Tenant


@pytest.fixture
def management_data() -> Iterator[tuple]:
    url = os.environ.get("VCM_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set VCM_TEST_DATABASE_URL for management contract tests")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    engine = create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        db = Session(bind=connection)
        try:
            tenants = [create_tenant(TenantIn(slug=f"patch-{uuid.uuid4().hex}",
                                              name=f"Patch client {i}"), db)
                       for i in range(2)]
            env_a1 = create_environment(tenants[0].id, EnvironmentIn(
                name="Production", kind="production",
                tags={"tier": "critical"}, match_key="ip"), db)
            env_a2 = create_environment(tenants[0].id, EnvironmentIn(
                name="DMZ", kind="dmz"), db)
            env_b = create_environment(tenants[1].id, EnvironmentIn(
                name="Production", kind="production"), db)
            asset = create_asset(env_a1.id, tenants[0].id, AssetIn(
                ip="192.0.2.10", fqdn="web.example.test",
                os="Windows Server 2019", criticality=2, tags={"role": "web"}), db)
            yield db, tenants[0], tenants[1], env_a1, env_a2, env_b, asset
        finally:
            db.close()
            transaction.rollback()
    engine.dispose()


def test_partial_patch_preserves_omitted_fields(management_data: tuple) -> None:
    db, tenant_a, _, env_a1, _, _, asset = management_data
    edited = update_tenant(tenant_a.id, TenantPatch(description="Edited"), db)
    assert edited.description == "Edited"
    assert edited.name == tenant_a.name and edited.slug == tenant_a.slug

    renamed = update_environment(env_a1.id, tenant_a.id, EnvironmentPatch(name="Renamed"), db)
    assert renamed.name == "Renamed"
    assert renamed.kind == "production" and renamed.match_key == "ip"
    assert renamed.tags == {"tier": "critical"}

    refreshed = update_asset(asset.id, tenant_a.id, AssetPatch(os="Windows Server 2022"), db)
    assert refreshed.os == "Windows Server 2022"
    assert refreshed.criticality == 2 and refreshed.tags == {"role": "web"}
    assert refreshed.fqdn == "web.example.test" and str(refreshed.ip) == "192.0.2.10"


def test_patch_conflicts_and_missing_targets(management_data: tuple) -> None:
    db, tenant_a, tenant_b, _, env_a2, env_b, asset = management_data
    with pytest.raises(HTTPException) as conflict:
        update_tenant(tenant_a.id, TenantPatch(slug=tenant_b.slug), db)
    assert conflict.value.status_code == 409
    with pytest.raises(HTTPException) as conflict:
        update_environment(env_a2.id, tenant_a.id, EnvironmentPatch(name="Production"), db)
    assert conflict.value.status_code == 409
    # The same environment name under another client is not a conflict.
    renamed = update_environment(env_b.id, tenant_b.id, EnvironmentPatch(name="DMZ"), db)
    assert renamed.name == "DMZ"

    missing = uuid.uuid4()
    for route, args, payload in (
            (update_tenant, (missing,), TenantPatch(name="Missing")),
            (update_environment, (missing, tenant_a.id), EnvironmentPatch(name="Missing")),
            (update_asset, (missing, tenant_a.id), AssetPatch(os="Missing"))):
        with pytest.raises(HTTPException) as error:
            route(*args, payload, db)
        assert error.value.status_code == 404


def test_empty_patch_is_rejected(management_data: tuple) -> None:
    db, tenant_a, _, env_a1, _, _, asset = management_data
    for route, args, payload in (
            (update_tenant, (tenant_a.id,), TenantPatch()),
            (update_environment, (env_a1.id, tenant_a.id), EnvironmentPatch()),
            (update_asset, (asset.id, tenant_a.id), AssetPatch())):
        with pytest.raises(HTTPException) as error:
            route(*args, payload, db)
        assert error.value.status_code == 422


def test_validation_rejects_invalid_values() -> None:
    with pytest.raises(ValidationError):
        EnvironmentPatch(kind="bogus")
    with pytest.raises(ValidationError):
        EnvironmentPatch(match_key="hostname")
    with pytest.raises(ValidationError):
        EnvironmentPatch(name="   ")
    with pytest.raises(ValidationError):
        EnvironmentPatch(tags={"key": 3})  # type: ignore[dict-item]
    with pytest.raises(ValidationError):
        AssetPatch(ip="999.2.3.4")
    with pytest.raises(ValidationError):
        AssetPatch(ip="192.0.2.0/24")  # an identity is an address, not a network
    with pytest.raises(ValidationError):
        AssetPatch(criticality=6)
    with pytest.raises(ValidationError):
        TenantPatch(slug="Invalid Slug!")
    with pytest.raises(ValidationError):
        TenantPatch(name="")

    with pytest.raises(ValidationError):
        TenantIn(slug="Bad Slug", name="x")
    with pytest.raises(ValidationError):
        EnvironmentIn(name="x", kind="bogus")
    with pytest.raises(ValidationError):
        AssetIn(ip="300.1.1.1")
    with pytest.raises(ValidationError):
        AssetIn(criticality=0)


def test_creation_conflicts_and_missing_targets(management_data: tuple) -> None:
    db, tenant_a, tenant_b, _, _, _, _ = management_data
    with pytest.raises(HTTPException) as conflict:
        create_tenant(TenantIn(slug=tenant_b.slug, name="Duplicate"), db)
    assert conflict.value.status_code == 409
    with pytest.raises(HTTPException) as conflict:
        create_environment(tenant_a.id, EnvironmentIn(name="Production"), db)
    assert conflict.value.status_code == 409
    with pytest.raises(HTTPException) as missing:
        create_environment(uuid.uuid4(), EnvironmentIn(name="Orphan"), db)
    assert missing.value.status_code == 404
    with pytest.raises(HTTPException) as missing:
        create_asset(uuid.uuid4(), tenant_a.id, AssetIn(ip="192.0.2.50"), db)
    assert missing.value.status_code == 404
