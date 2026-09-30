"""API dashboard: overview cliente (cross-ambiente) e per singolo ambiente.

Metriche esposte:
  * distribuzione severità (Critical..Info e CAT I/II/III);
  * trend temporale aperti vs chiusi;
  * Top 10 vulnerabilità più diffuse / Top 10 host più vulnerabili;
  * AD Health Score (ultimi snapshot PingCastle/Purple Knight) come gauge;
  * punteggio di postura globale (0-100) per l'executive report.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..models import (ADHealthSnapshot, Asset, Finding, ScanImport)
from .scope import require_environment
from .tenants import get_db

router = APIRouter(prefix="/api")

SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]
SEVERITY_WEIGHT = {"critical": 10, "high": 7, "medium": 4, "low": 2, "info": 0}


def _scope(stmt, tenant_id, environment_id, model=Finding):
    if tenant_id:
        stmt = stmt.where(model.tenant_id == tenant_id)
    if environment_id:
        stmt = stmt.where(model.environment_id == environment_id)
    return stmt


@router.get("/dashboard")
def dashboard(tenant_id: Optional[uuid.UUID] = None,
              environment_id: Optional[uuid.UUID] = None,
              db: Session = Depends(get_db)):
    if environment_id and tenant_id:
        require_environment(db, environment_id, tenant_id)
    base = select(Finding)
    base = _scope(base, tenant_id, environment_id)

    # 1) distribuzione severità (aperti) + compliance per categoria STIG
    sev_rows = db.execute(
        _scope(select(Finding.severity, Finding.kind, func.count()).group_by(
            Finding.severity, Finding.kind), tenant_id, environment_id)
        .where(Finding.status == "active")).all()
    severity = {s: 0 for s in SEVERITY_ORDER}
    compliance = {"CAT_I": 0, "CAT_II": 0, "CAT_III": 0, "untagged": 0}
    vuln_total = comp_total = 0
    for sev, kind, count in sev_rows:
        severity[sev] = severity.get(sev, 0) + count
        if kind == "vulnerability":
            vuln_total += count
        else:
            comp_total += count
    stig_rows = db.execute(
        _scope(select(Finding.stig_category, func.count()).group_by(Finding.stig_category),
               tenant_id, environment_id).where(Finding.status == "active",
                                                Finding.kind == "compliance")).all()
    for cat, count in stig_rows:
        compliance[cat or "untagged"] = count

    # 2) totali e trend aperti vs chiusi (ultimi 30 giorni, per giorno)
    totals = db.execute(
        _scope(select(Finding.status, func.count()).group_by(Finding.status),
               tenant_id, environment_id)).all()
    by_status = {status: count for status, count in totals}

    trend_rows = db.execute(
        _scope(select(func.date_trunc("day", Finding.last_seen).label("day"),
                      func.count(case((Finding.status == "active", 1))),
                      func.count(case((Finding.status == "mitigated", 1))))
               .group_by("day").order_by("day"), tenant_id, environment_id)).all()
    trend = [{"day": day.date().isoformat(), "open": int(opened), "closed": int(closed)}
             for day, opened, closed in trend_rows]

    # 3) Top 10 regole più diffuse e host più vulnerabili
    top_rules = db.execute(
        _scope(select(Finding.scanner, Finding.rule_id, Finding.rule_title, Finding.severity,
                      func.count(func.distinct(Finding.asset_id)).label("assets"))
               .where(Finding.status == "active")
               .group_by(Finding.scanner, Finding.rule_id, Finding.rule_title, Finding.severity)
               .order_by(func.count(func.distinct(Finding.asset_id)).desc())
               .limit(10), tenant_id, environment_id)).all()
    top_hosts = db.execute(
        _scope(select(Asset.id, Asset.ip, Asset.fqdn, Asset.hostname_netbios,
               func.count(Finding.id).label("open_findings"),
               func.count(case((Finding.severity.in_(["critical", "high"]), 1))).label("crit_high"))
        .join(Finding, Finding.asset_id == Asset.id)
        .where(Finding.status == "active")
        .group_by(Asset.id)
        .order_by(func.count(case((Finding.severity.in_(["critical", "high"]), 1))).desc(),
                  func.count(Finding.id).desc())
        .limit(10), tenant_id, environment_id)).all()

    # 4) AD Health Score: ultimi snapshot per tool
    # Seleziona l'ultimo snapshot per coppia tool/ambiente prima di leggere i dati.
    latest_ad = _scope(
        select(ADHealthSnapshot.id, func.row_number().over(
            partition_by=(ADHealthSnapshot.tool, ADHealthSnapshot.environment_id),
            order_by=(ADHealthSnapshot.snapshot_at.desc(), ADHealthSnapshot.id.desc()),
        ).label("position")), tenant_id, environment_id, ADHealthSnapshot).subquery()
    ad_rows = db.execute(
        select(ADHealthSnapshot).join(latest_ad, latest_ad.c.id == ADHealthSnapshot.id)
        .where(latest_ad.c.position == 1)
        .order_by(ADHealthSnapshot.snapshot_at.desc(), ADHealthSnapshot.id.desc())).scalars().all()
    seen_tools: dict[str, dict] = {}
    for snap in ad_rows:
        key = f"{snap.tool}:{snap.environment_id}"
        if key not in seen_tools:
            seen_tools[key] = {
                "tool": snap.tool, "environment_id": str(snap.environment_id),
                "global_score": float(snap.global_score) if snap.global_score is not None else None,
                "category_scores": snap.category_scores,
                "snapshot_at": snap.snapshot_at.isoformat(),
            }

    posture = _posture_score(severity)

    return {
        "scope": {"tenant_id": str(tenant_id) if tenant_id else None,
                  "environment_id": str(environment_id) if environment_id else None},
        "totals": {"active": by_status.get("active", 0),
                   "mitigated": by_status.get("mitigated", 0),
                   "false_positive": by_status.get("false_positive", 0),
                   "risk_accepted": by_status.get("risk_accepted", 0),
                   "vulnerabilities": vuln_total, "compliance": comp_total},
        "severity_distribution": severity,
        "stig_distribution": compliance,
        "trend": trend,
        "top_rules": [{"scanner": s, "rule_id": r, "title": t, "severity": sev, "affected_assets": int(a)}
                      for s, r, t, sev, a in top_rules],
        "top_hosts": [{"asset_id": str(i), "ip": str(ip) if ip else None, "fqdn": fqdn,
                       "netbios": netbios, "open_findings": int(of), "open_crit_high": int(ch)}
                      for i, ip, fqdn, netbios, of, ch in top_hosts],
        "ad_health": list(seen_tools.values()),
        "posture_score": posture,
    }


def _posture_score(severity: dict[str, int]) -> int:
    """Punteggio di postura 0-100: 100 = nessun finding aperto critico/alto."""
    open_total = sum(severity.values()) or 1
    weighted = sum(SEVERITY_WEIGHT[s] * n for s, n in severity.items())
    return max(0, min(100, round(100 - 100 * weighted / (10 * open_total))))


@router.get("/dashboard/compliance")
def compliance_overview(tenant_id: Optional[uuid.UUID] = None,
                        environment_id: Optional[uuid.UUID] = None,
                        db: Session = Depends(get_db)):
    """Vista compliance: esiti SCC (pass/fail/NR) e regole AD per categoria."""
    if environment_id and tenant_id:
        require_environment(db, environment_id, tenant_id)
    results = db.execute(
        _scope(select(Finding.result, func.count()).group_by(Finding.result),
               tenant_id, environment_id)
        .where(Finding.kind == "compliance")).all()
    categories = db.execute(
        _scope(select(Finding.scanner, Finding.category, func.count()).group_by(
            Finding.scanner, Finding.category), tenant_id, environment_id)
        .where(Finding.kind == "compliance")).all()
    return {
        "results": {result: count for result, count in results},
        "categories": [{"scanner": s, "category": c, "total": int(n)} for s, c, n in categories],
    }
