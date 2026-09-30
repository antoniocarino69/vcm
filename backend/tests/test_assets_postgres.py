"""Tenant-scoped inventory regressions, rolled back on a real PostgreSQL database."""
from __future__ import annotations

import os
import uuid
from typing import Iterator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.api.assets import inventory, get_asset, asset_findings, asset_moves, asset_imports
from app.dbrepo import SqlAlchemyRepository
from app.models import Asset, AssetMove, Environment, ScanImport, Tenant
from app.parsers.base import NormalizedFinding, ParsedHost
from app.services.ingest import ingest_stream


@pytest.fixture
def inventory_data() -> Iterator[tuple]:
    url = os.environ.get('VCM_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Set VCM_TEST_DATABASE_URL for PostgreSQL inventory tests')
    engine = create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        db = Session(bind=connection)
        try:
            tenants = [Tenant(slug=f'inventory-{uuid.uuid4().hex}', name=f'Inventory {i}') for i in range(2)]
            db.add_all(tenants); db.flush()
            envs = [Environment(tenant_id=tenants[n].id, name=f'Environment {i}') for i, n in enumerate([0,0,1])]
            db.add_all(envs); db.flush()
            assets = []
            scans = []
            for i, (os_text, env) in enumerate(zip(['Windows Server 2022','Ubuntu 24.04',None,'\t \n','Windows Server 2022'], [envs[0],envs[0],envs[0],envs[1],envs[2]])):
                scan = ScanImport(tenant_id=env.tenant_id, environment_id=env.id, scanner='tenable_nessus', filename=f'asset-{i}.nessus', content_sha256=f'{i:064x}', storage_path='/test-only', status='completed')
                db.add(scan); db.flush(); scans.append(scan)
                ingest_stream(SqlAlchemyRepository(db), iter([ParsedHost(ip=f'192.0.2.{i+1}',fqdn=f'host-{i}.example.test',os=os_text,findings=[
                    NormalizedFinding(kind='vulnerability',scanner='tenable_nessus',rule_id='same-rule',rule_title='Shared rule',severity='high',port=443),
                    NormalizedFinding(kind='vulnerability',scanner='tenable_nessus',rule_id='info-rule',rule_title='Information',severity='info')
                ])]), str(env.tenant_id),str(env.id),str(scan.id))
                asset = db.scalar(select(Asset).where(Asset.tenant_id == env.tenant_id, Asset.ip == f'192.0.2.{i+1}'))
                asset.tags = {'tier':'critical' if i in (0,4) else 'standard'}
                assets.append(asset)
            db.add(AssetMove(tenant_id=assets[0].tenant_id,asset_id=assets[0].id,from_environment_id=envs[0].id,to_environment_id=envs[1].id,reason='Retain snapshots'))
            assets[0].environment_id = envs[1].id
            db.flush()
            yield db, tenants, envs, assets, scans
        finally:
            db.close(); transaction.rollback()
    engine.dispose()


def listing(db: Session, tenant_id: uuid.UUID, **kwargs: object) -> dict:
    params = dict(environment_id=None, search=None, os_search=None, os_family=None, tag=None, sort='ip', direction='asc', limit=50, offset=0)
    params.update(kwargs)
    return inventory(tenant_id=tenant_id, db=db, **params)


def test_inventory_filters_before_pagination(inventory_data: tuple) -> None:
    db, tenants, envs, assets, _ = inventory_data
    result = listing(db, tenants[0].id, os_family='windows', limit=1)
    assert result['total'] == 1 and result['items'][0]['id'] == assets[0].id
    assert result['items'][0]['open_findings'] == 2
    assert result['items'][0]['open_critical_high'] == 1
    assert result['items'][0]['environment_id'] == envs[1].id
    assert listing(db, tenants[0].id, os_family='linux')['total'] == 1
    assert listing(db, tenants[0].id, os_family='unknown')['total'] == 2
    assert listing(db, tenants[0].id, os_search='server 2022')['total'] == 1
    assert listing(db, tenants[0].id, os_search='%')['total'] == 0
    assert listing(db, tenants[0].id, tag=['tier:critical'])['total'] == 1
    assert listing(db, tenants[0].id, tag=['tier:critical','missing'])['total'] == 0
    assert listing(db, tenants[0].id, search='host-1')['total'] == 1
    assert listing(db, tenants[0].id, environment_id=envs[0].id)['total'] == 2
    assert listing(db, tenants[0].id, offset=999)['total'] == 4
    assert listing(db, tenants[0].id, offset=999)['items'] == []


def test_stable_sorting_and_tenant_scope(inventory_data: tuple) -> None:
    db, tenants, envs, assets, _ = inventory_data
    first = listing(db, tenants[0].id, sort='open_findings', direction='desc', limit=2)
    second = listing(db, tenants[0].id, sort='open_findings', direction='desc', limit=2, offset=2)
    assert len({row['id'] for row in first['items'] + second['items']}) == 4
    assert all(row['tenant_id'] == tenants[0].id for row in first['items'] + second['items'])
    with pytest.raises(HTTPException) as error:
        listing(db, tenants[0].id, environment_id=envs[2].id)
    assert error.value.status_code == 404
    # Existing schemas permit inconsistent pairs; the read join must reject them.
    db.add(Asset(tenant_id=tenants[0].id,environment_id=envs[2].id,fqdn='invalid.example.test'))
    db.flush()
    assert listing(db, tenants[0].id)['total'] == 4


def test_detail_preserves_asset_and_snapshot_context(inventory_data: tuple) -> None:
    db, tenants, envs, assets, scans = inventory_data
    detail = get_asset(assets[0].id, tenants[0].id, db)
    assert detail['environment_id'] == envs[1].id
    findings = asset_findings(assets[0].id, tenants[0].id, limit=1, offset=0, db=db)
    assert findings['total'] == 2
    assert findings['items'][0]['environment_id'] == envs[0].id
    moves = asset_moves(assets[0].id, tenants[0].id, limit=20, offset=0, db=db)
    assert moves['items'][0]['from_environment_id'] == envs[0].id
    assert moves['items'][0]['to_environment_id'] == envs[1].id
    imports = asset_imports(assets[0].id, tenants[0].id, limit=20, offset=0, db=db)
    assert imports['total'] == 1 and imports['items'][0]['id'] == scans[0].id
    assert 'storage_path' not in imports['items'][0]
    for endpoint, extra in [(get_asset,{}),(asset_findings,{'limit':20,'offset':0}),(asset_moves,{'limit':20,'offset':0}),(asset_imports,{'limit':20,'offset':0})]:
        with pytest.raises(HTTPException) as error:
            endpoint(assets[4].id, tenants[0].id, db=db, **extra)
        assert error.value.status_code == 404


def test_import_references_do_not_invent_older_observations(inventory_data: tuple) -> None:
    db, tenants, envs, assets, scans = inventory_data
    newer = ScanImport(tenant_id=tenants[0].id,environment_id=envs[0].id,scanner='tenable_nessus',filename='repeat.nessus',content_sha256='f'*64,storage_path='/test-only',status='completed')
    db.add(newer); db.flush()
    ingest_stream(SqlAlchemyRepository(db), iter([ParsedHost(ip='192.0.2.2',findings=[
        NormalizedFinding(kind='vulnerability',scanner='tenable_nessus',rule_id='same-rule',rule_title='Shared rule',severity='high',port=443),
        NormalizedFinding(kind='vulnerability',scanner='tenable_nessus',rule_id='info-rule',rule_title='Information',severity='info')
    ])]),str(tenants[0].id),str(envs[0].id),str(newer.id))
    imports = asset_imports(assets[1].id,tenants[0].id,limit=50,offset=0,db=db)
    assert imports['total'] == 1 and imports['items'][0]['id'] == newer.id
    assert imports['coverage'] == 'latest_and_closure_references_only'
    assert scans[1].id != newer.id
    assert asset_findings(assets[1].id,tenants[0].id,limit=50,offset=0,db=db)['total'] == 2
