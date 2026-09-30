"""API: upload report scanner -> scan_imports -> task Celery di parsing."""
from __future__ import annotations

import hashlib
import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Environment, ScanImport, Tenant
from ..parsers import sniff_file
from .scope import require_environment, require_import
from .tenants import get_db

router = APIRouter(prefix="/api")

SCANNER_MAP = {
    "qualys_vmdr": "qualys_vmdr", "qualys": "qualys_vmdr",
    "tenable_nessus": "tenable_nessus", "nessus": "tenable_nessus",
    "scc_xccdf": "scc_xccdf", "scc": "scc_xccdf",
    "pingcastle": "pingcastle", "purple_knight": "purple_knight",
    "auto": "auto",
}


@router.post("/environments/{env_id}/imports", status_code=202)
async def upload_import(
    env_id: uuid.UUID,
    file: UploadFile = File(...),
    scanner: str = Form("auto"),
    auto_close: bool = Form(False),
    created_by: Optional[str] = Form(None),
    tenant_id: uuid.UUID = Form(...),
    db: Session = Depends(get_db),
):
    """Carica un report scanner.

    * ``scanner=auto`` rileva il formato dal contenuto (Qualys/Nessus/SCC/
      PingCastle/Purple Knight);
    * ``auto_close=true`` chiude i finding non più rilevati dallo stesso
      scanner sugli host presenti nel report (flag per singola importazione);
    * il parsing avviene asincrono: la risposta 202 restituisce l'import id
      da seguire su GET /api/imports/{id}.
    """
    env = require_environment(db, env_id, tenant_id)
    if scanner not in SCANNER_MAP:
        raise HTTPException(422, f"Scanner non supportato: {scanner}")

    os.makedirs(settings.storage_dir, exist_ok=True)
    content = await file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "File oltre il limite configurato")
    digest = hashlib.sha256(content).hexdigest()
    storage_path = os.path.join(settings.storage_dir, f"{uuid.uuid4().hex}_{file.filename}")
    with open(storage_path, "wb") as handle:
        handle.write(content)

    resolved = scanner
    if SCANNER_MAP[scanner] == "auto":
        try:
            resolved = sniff_file(storage_path)
        except ValueError as exc:
            os.remove(storage_path)
            raise HTTPException(422, str(exc)) from exc

    scan_import = ScanImport(
        tenant_id=str(env.tenant_id),
        environment_id=str(env_id),
        scanner=resolved,
        filename=file.filename or "upload",
        content_sha256=digest,
        storage_path=storage_path,
        auto_close=auto_close,
        created_by=created_by,
    )
    db.add(scan_import)
    try:
        db.commit()
    except Exception:  # violazione uniq(tenant, sha256): file già importato
        db.rollback()
        os.remove(storage_path)
        raise HTTPException(409, "Questo file è già stato importato per questo cliente")

    from ..workers.tasks import parse_import
    task = parse_import.delay(str(scan_import.id))
    return {"import_id": str(scan_import.id), "scanner": resolved,
            "auto_close": auto_close, "task_id": task.id, "status": "pending"}


@router.get("/imports/{import_id}")
def get_import(import_id: uuid.UUID, tenant_id: uuid.UUID,
               db: Session = Depends(get_db)):
    return require_import(db, import_id, tenant_id)


@router.get("/environments/{env_id}/imports")
def list_imports(env_id: uuid.UUID, tenant_id: uuid.UUID,
                 db: Session = Depends(get_db)):
    require_environment(db, env_id, tenant_id)
    stmt = (select(ScanImport).where(ScanImport.environment_id == env_id)
            .order_by(ScanImport.created_at.desc()))
    return db.execute(stmt).scalars().all()
