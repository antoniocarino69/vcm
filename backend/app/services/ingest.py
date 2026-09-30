"""Motore di ingest: deduplica intelligente, lifecycle, auto-closing.

Logica pura e dipendenza-free (testabile senza database): lavora su un
protocollo ``FindingRepository`` implementato sia in memoria (test) sia via
SQLAlchemy (produzione, vedi ``app/dbrepo.py``).

Dedup hash: sha256(asset_id | rule_id | port) — univoco per ambiente grazie
all'indice ``findings_dedup_uidx``. Se il finding esiste già:
  * ``last_seen`` aggiornato
  * ``occurrence_count`` incrementato
  * nessun duplicato creato
  * se era stato chiuso (mitigated) e ricompare -> riaperto come Active
    con transizione registrata in ``finding_status_history``.

Auto-closing (flag per singola importazione): i finding aperti dello stesso
scanner su quel asset che NON compaiono nel nuovo report vengono chiusi come
``mitigated`` con ``closed_by_import_id`` = importazione corrente.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator, Optional, Protocol

from ..parsers.base import NormalizedFinding, ParsedHost


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def compute_dedup_hash(asset_id: str, rule_id: str, port: Optional[int],
                       scanner: Optional[str] = None) -> str:
    """Hash identificativo univoco del finding per l'ambiente.

    Composizione canonica (spec: asset + rule_id/plugin_id/qid + port)::

        {asset_id}|{scanner}:{rule_id}|{port or ''}   -> sha256 hexdigest

    Il prefisso ``scanner:`` qualifica il namespace di ``rule_id`` (QID Qualys,
    PluginID Nessus, Rule idref SCC, RiskId PingCastle, Indicator PK): senza,
    uno stesso numero su scanner diversi (es. QID 11219 vs PluginID 11219)
    colliderebbe sullo stesso record.
    """
    qualified_rule = f"{scanner}:{rule_id}" if scanner else str(rule_id)
    canonical = f"{asset_id}|{qualified_rule}|{port if port is not None else ''}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- repository
class FindingRepository(Protocol):
    """Minimo contratto di persistenza usato dal motore di ingest."""

    def get_or_create_asset(self, host: ParsedHost, tenant_id: str, environment_id: str) -> str: ...
    def find_finding(self, environment_id: str, dedup_hash: str) -> Optional[dict[str, Any]]: ...
    def insert_finding(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def update_finding(self, finding_id: Any, changes: dict[str, Any]) -> None: ...
    def list_open_findings(self, environment_id: str, scanner: str,
                           asset_id: Optional[str] = None) -> list[dict[str, Any]]: ...
    def record_status_change(self, finding_id: Any, from_status: Optional[str],
                             to_status: str, reason: str,
                             import_id: Optional[str], changed_by: Optional[str]) -> None: ...
    def record_ad_health(self, payload: dict[str, Any]) -> None: ...


# ------------------------------------------------------------------- results
@dataclass
class IngestStats:
    hosts: int = 0
    findings: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    reopened: int = 0
    auto_closed: int = 0
    skipped: int = 0

    def to_dict(self) -> dict[str, int]:
        return self.__dict__.copy()


@dataclass
class HostBatch:
    """Un batch di finding già associati al proprio asset (per flush a DB)."""
    asset_id: str
    entries: list[tuple[NormalizedFinding, str]] = field(default_factory=list)  # (finding, dedup_hash)


# --------------------------------------------------------------- merge logic
def merge_incoming(existing: dict[str, Any], finding: NormalizedFinding,
                   dedup_hash: str, import_id: str, now: datetime) -> dict[str, Any]:
    """Applica un finding in ingresso a uno già presente (deduplica).

    Ritorna un diff di campi da aggiornare; tocca solo ciò che cambia.
    """
    changes: dict[str, Any] = {
        "last_seen": now,
        "occurrence_count": int(existing.get("occurrence_count", 1)) + 1,
        "last_import_id": import_id,
        "updated_at": now,
    }
    # Aggiorna i campi descrittivi se il report è più ricco del record storico
    for src, dst in (("description", "description"), ("solution", "solution"),
                     ("scanner_output", "scanner_output"), ("cvss_score", "cvss_score"),
                     ("cvss_vector", "cvss_vector"), ("rule_title", "rule_title"),
                     ("severity", "severity"), ("severity_raw", "severity_raw"),
                     ("result", "result"), ("category", "category"),
                     ("stig_category", "stig_category"), ("raw", "raw")):
        incoming_value = getattr(finding, src, None)
        if incoming_value not in (None, "", [], {}) and incoming_value != existing.get(dst):
            changes[dst] = incoming_value
    if finding.cves:
        merged = sorted(set(existing.get("cves") or []) | set(finding.cves))
        if merged != (existing.get("cves") or []):
            changes["cves"] = merged
    if finding.affected_objects:
        merged = sorted(set(existing.get("affected_objects") or []) | set(finding.affected_objects))
        if merged != (existing.get("affected_objects") or []):
            changes["affected_objects"] = merged

    # Riapertura: un finding mitigato che ricompare torna Active
    if existing.get("status") and existing["status"] != "active":
        changes.update({
            "status": "active",
            "closed_at": None,
            "closed_by_import_id": None,
            "status_reason": "Rilevato nuovamente: riaperto automaticamente",
        })
    return changes


def new_finding_payload(tenant_id: str, environment_id: str, asset_id: str,
                        finding: NormalizedFinding, dedup_hash: str,
                        import_id: str, now: datetime) -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "asset_id": asset_id,
        "environment_id": environment_id,
        "kind": finding.kind,
        "scanner": finding.scanner,
        "rule_id": finding.rule_id,
        "rule_title": finding.rule_title,
        "category": finding.category,
        "severity": finding.severity,
        "severity_raw": finding.severity_raw,
        "stig_category": finding.stig_category,
        "cvss_score": finding.cvss_score,
        "cvss_vector": finding.cvss_vector,
        "cves": finding.cves,
        "port": finding.port,
        "protocol": finding.protocol,
        "benchmark": finding.benchmark,
        "profile": finding.profile,
        "result": finding.result,
        "affected_objects": finding.affected_objects,
        "description": finding.description,
        "solution": finding.solution,
        "scanner_output": finding.scanner_output,
        "dedup_hash": dedup_hash,
        "status": "active",
        "first_seen": now,
        "last_seen": now,
        "occurrence_count": 1,
        "last_import_id": import_id,
        "raw": finding.raw,
        "updated_at": now,
    }


def plan_auto_close(open_findings: Iterable[dict[str, Any]],
                    seen_hashes: set[str], scanner: str,
                    import_id: str, now: datetime) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Elenca le chiusure automatiche: (finding, changes).

    Solo finding aperti dello stesso ``scanner`` non presenti nel nuovo report.
    """
    closures: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for existing in open_findings:
        if existing.get("scanner") != scanner:
            continue
        if existing.get("dedup_hash") in seen_hashes:
            continue
        closures.append((existing, {
            "status": "mitigated",
            "closed_at": now,
            "closed_by_import_id": import_id,
            "status_reason": f"Non più rilevato (auto-close import {import_id})",
            "updated_at": now,
        }))
    return closures


# -------------------------------------------------------------- orchestrator
def ingest_stream(repo: FindingRepository,
                  hosts: Iterator[ParsedHost],
                  tenant_id: str,
                  environment_id: str,
                  import_id: str,
                  auto_close: bool = False,
                  batch_size: int = 500,
                  match_key: str = "ip",
                  now: Optional[datetime] = None) -> IngestStats:
    """Consuma lo stream dei parser in batch e applica dedup + lifecycle.

    Procedura per host:
      1. riconciliazione asset (get_or_create secondo ``match_key``);
      2. upsert di ogni finding tramite ``dedup_hash``;
      3. se ``auto_close``: chiude i finding aperti dello stesso scanner su
         quell'asset non presenti nel report corrente.
    """
    now = now or utcnow()
    stats = IngestStats()
    pending: list[HostBatch] = []
    # (asset_id, scanner) -> set(dedup_hash) visti in questa importazione
    seen_by_asset: dict[tuple[str, str], set[str]] = {}

    def flush() -> None:
        for batch in pending:
            for finding, dedup_hash in batch.entries:
                existing = repo.find_finding(environment_id, dedup_hash)
                if existing is None:
                    payload = new_finding_payload(tenant_id, environment_id, batch.asset_id,
                                                  finding, dedup_hash, import_id, now)
                    repo.insert_finding(payload)
                    stats.created += 1
                else:
                    changes = merge_incoming(existing, finding, dedup_hash, import_id, now)
                    reopened = "status" in changes and changes["status"] == "active"
                    repo.update_finding(existing["id"], changes)
                    stats.updated += 1
                    if reopened:
                        stats.reopened += 1
                        repo.record_status_change(
                            existing["id"], existing.get("status"), "active",
                            "Rilevato nuovamente: riaperto automaticamente", import_id, None)
        pending.clear()

    for host in hosts:
        asset_id = repo.get_or_create_asset(host, tenant_id, environment_id)
        stats.hosts += 1
        # Snapshot postura AD (PingCastle global score / Purple Knight score)
        if host.metadata.get("tool") and (
                host.metadata.get("global_score") is not None
                or host.metadata.get("category_scores")):
            repo.record_ad_health({
                "tenant_id": tenant_id,
                "environment_id": environment_id,
                "asset_id": asset_id,
                "tool": host.metadata.get("tool"),
                "global_score": host.metadata.get("global_score"),
                "category_scores": host.metadata.get("category_scores") or {},
                "import_id": import_id,
                "raw": {"rule_count": host.metadata.get("rule_count")},
            })
        batch = HostBatch(asset_id=asset_id)
        for finding in host.findings:
            dedup_hash = compute_dedup_hash(asset_id, finding.rule_id, finding.port,
                                            scanner=finding.scanner)
            seen_by_asset.setdefault((asset_id, finding.scanner), set()).add(dedup_hash)
            batch.entries.append((finding, dedup_hash))
            stats.findings += 1
        pending.append(batch)
        if len(pending) >= batch_size:
            flush()

    flush()

    if auto_close:
        for (asset_id, scanner), seen_hashes in seen_by_asset.items():
            stats.auto_closed += auto_close_asset(repo, environment_id, asset_id,
                                                  scanner, seen_hashes, import_id, now)

    return stats


def auto_close_asset(repo: FindingRepository, environment_id: str, asset_id: str,
                     scanner: str, seen_hashes: set[str], import_id: str,
                     now: Optional[datetime] = None) -> int:
    """Chiude i finding aperti (dello scanner dato) non visti nell'ultimo report."""
    now = now or utcnow()
    open_findings = repo.list_open_findings(environment_id, scanner=scanner, asset_id=asset_id)
    closed = 0
    for existing, changes in plan_auto_close(open_findings, seen_hashes, scanner, import_id, now):
        repo.update_finding(existing["id"], changes)
        repo.record_status_change(existing["id"], existing.get("status"), "mitigated",
                                  changes["status_reason"], import_id, None)
        closed += 1
    return closed


# ------------------------------------------------------- manual status changes
def transition_status(repo: FindingRepository, finding: dict[str, Any], new_status: str,
                      reason: Optional[str], risk_accepted_until: Optional[str],
                      import_id: Optional[str], changed_by: Optional[str],
                      now: Optional[datetime] = None) -> dict[str, Any]:
    """Transizioni manuali: false_positive / risk_accepted / mitigated / active."""
    if new_status not in ("active", "mitigated", "false_positive", "risk_accepted"):
        raise ValueError(f"Stato non valido: {new_status}")
    if new_status == "risk_accepted" and not reason:
        raise ValueError("Risk Accepted richiede una nota motivazionale")
    now = now or utcnow()
    changes: dict[str, Any] = {"status": new_status, "updated_at": now, "status_reason": reason}
    if new_status == "active":
        changes.update({"closed_at": None, "closed_by_import_id": None})
    else:
        changes["closed_at"] = now
    if new_status == "risk_accepted":
        changes["risk_accepted_until"] = risk_accepted_until
    repo.update_finding(finding["id"], changes)
    repo.record_status_change(finding["id"], finding.get("status"), new_status,
                              reason or "", import_id, changed_by)
    return changes
