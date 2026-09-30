"""API reporting: generazione Executive (HTML/PDF) e Technical (HTML/CSV)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Environment, Finding, Tenant
from ..services.reports_render import (render_executive_html,
                                       render_technical_csv,
                                       render_technical_html)
from .dashboards import dashboard
from .tenants import get_db

router = APIRouter(prefix="/api/reports")


def _bundle(tenant_id, environment_id, db: Session) -> dict:
    data = dashboard(tenant_id=tenant_id, environment_id=environment_id, db=db)
    tenant = db.get(Tenant, tenant_id) if tenant_id else None
    env = db.get(Environment, environment_id) if environment_id else None

    stmt = select(Finding).where(Finding.status == "active")
    if tenant_id:
        stmt = stmt.where(Finding.tenant_id == tenant_id)
    if environment_id:
        stmt = stmt.where(Finding.environment_id == environment_id)
    findings = db.execute(stmt.order_by(Finding.asset_id, Finding.severity)).scalars().all()

    hosts: dict[str, dict] = {}
    from ..models import Asset
    for finding in findings:
        asset = db.get(Asset, finding.asset_id)
        key = str(finding.asset_id)
        host = hosts.setdefault(key, {
            "ip": str(asset.ip) if asset and asset.ip else None,
            "fqdn": asset.fqdn if asset else None,
            "netbios": asset.hostname_netbios if asset else None,
            "os": asset.os if asset else None,
            "findings": [],
        })
        host["findings"].append({
            "scanner": finding.scanner, "kind": finding.kind, "rule_id": finding.rule_id,
            "rule_title": finding.rule_title, "severity": finding.severity,
            "stig_category": finding.stig_category, "result": finding.result,
            "cves": finding.cves, "port": finding.port, "protocol": finding.protocol,
            "cvss_score": float(finding.cvss_score) if finding.cvss_score is not None else None,
            "benchmark": finding.benchmark, "profile": finding.profile,
            "description": finding.description, "solution": finding.solution,
            "scanner_output": finding.scanner_output, "status": finding.status,
            "first_seen": finding.first_seen.isoformat() if finding.first_seen else None,
            "last_seen": finding.last_seen.isoformat() if finding.last_seen else None,
        })

    data.update({
        "tenant_name": tenant.name if tenant else "All clients",
        "environment_name": env.name if env else "all",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "hosts": list(hosts.values()),
    })
    return data


@router.get("/executive")
def executive_report(tenant_id: uuid.UUID, environment_id: Optional[uuid.UUID] = None,
                     format: str = "html", db: Session = Depends(get_db)):
    """Executive Report: sintesi alta, postura, distribuzione rischio, remediation."""
    data = _bundle(tenant_id, environment_id, db)
    body = render_executive_html(data)
    if format == "pdf":
        return _as_pdf(body, "executive")
    return HTMLResponse(body)


@router.get("/technical")
def technical_report(tenant_id: uuid.UUID, environment_id: Optional[uuid.UUID] = None,
                     format: str = "html", db: Session = Depends(get_db)):
    """Technical Report: dettaglio per host, CVE/STIG, remediation, output scanner."""
    data = _bundle(tenant_id, environment_id, db)
    if format == "csv":
        return Response(render_technical_csv(data), media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=technical_report.csv"})
    body = render_technical_html(data)
    if format == "pdf":
        return _as_pdf(body, "technical")
    return HTMLResponse(body)


def _as_pdf(body: str, kind: str) -> Response:
    """Converte l'HTML print-ready in PDF con WeasyPrint se installato;
    altrimenti restituisce l'HTML (print-ready) con 200 e un avviso header."""
    try:
        from weasyprint import HTML  # type: ignore
    except Exception:
        return HTMLResponse(body, headers={"X-PDF-Fallback":
                                          "WeasyPrint unavailable: returned print-ready HTML"})
    pdf = HTML(string=body).write_pdf()
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={kind}_report.pdf"})
