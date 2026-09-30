"""Task Celery: parsing asincrono dei file di report in background."""
from __future__ import annotations

from datetime import datetime, timezone

from ..config import settings
from ..dbrepo import SessionLocal, SqlAlchemyRepository
from ..models import ScanImport
from ..parsers import get_parser
from ..services.ingest import ingest_stream
from .celery_app import celery_app


@celery_app.task(name="vcm.parse_import", bind=True, max_retries=2)
def parse_import(self, import_id: str) -> dict:
    """Parsa il file associato a ``scan_imports[import_id]`` e applica ingest.

    Pipeline: parser streaming -> ingest_stream (batch) -> dedup/auto-close.
    Gli snapshot AD Health Score (PingCastle/Purple Knight) sono registrati da
    ingest_stream quando il parser espone ``host.metadata`` con lo score.
    """
    with SessionLocal() as session:
        scan_import = session.get(ScanImport, import_id)
        if scan_import is None:
            return {"error": f"import {import_id} non trovato"}
        scan_import.status = "parsing"
        scan_import.started_at = datetime.now(timezone.utc)
        session.commit()

        repo = SqlAlchemyRepository(session)
        try:
            parser = get_parser(scan_import.scanner)
            stats = ingest_stream(
                repo,
                parser.parse(scan_import.storage_path),
                tenant_id=str(scan_import.tenant_id),
                environment_id=str(scan_import.environment_id),
                import_id=str(scan_import.id),
                auto_close=scan_import.auto_close,
                batch_size=settings.ingest_batch_size,
                match_key=repo._match_key(str(scan_import.environment_id)),
            )
            scan_import.status = "completed"
            scan_import.stats = stats.to_dict()
            scan_import.finished_at = datetime.now(timezone.utc)
            session.commit()
            return stats.to_dict()
        except Exception as exc:  # noqa: BLE001 - superficie di errore del worker
            session.rollback()
            scan_import.status = "failed"
            scan_import.error = f"{type(exc).__name__}: {exc}"
            scan_import.finished_at = datetime.now(timezone.utc)
            session.commit()
            raise
