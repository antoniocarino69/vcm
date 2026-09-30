"""Test del motore di ingest: deduplica, occurrence_count, auto-closing,
riapertura, transizioni di stato. Repository in memoria (no DB)."""
import copy

from conftest import fixture

from app.parsers import get_parser
from app.parsers.base import NormalizedFinding, ParsedHost
from app.services.ingest import (compute_dedup_hash, ingest_stream,
                                 plan_auto_close, transition_status)


class InMemoryRepo:
    """Implementazione in memoria del protocollo FindingRepository."""

    def __init__(self):
        self.findings: dict[str, dict] = {}
        self.assets: dict[str, ParsedHost] = {}
        self.status_history: list[dict] = []
        self._next_id = 1

    def get_or_create_asset(self, host, tenant_id, environment_id):
        key = (host.ip or host.fqdn or host.hostname_netbios).lower()
        self.assets.setdefault(key, host)
        return f"asset-{key}"

    def find_finding(self, environment_id, dedup_hash):
        row = self.findings.get(dedup_hash)
        return copy.deepcopy(row) if row else None

    def insert_finding(self, payload):
        payload = dict(payload)
        payload["id"] = self._next_id
        self._next_id += 1
        self.findings[payload["dedup_hash"]] = payload
        return copy.deepcopy(payload)

    def update_finding(self, finding_id, changes):
        for row in self.findings.values():
            if row["id"] == finding_id:
                row.update(changes)

    def list_open_findings(self, environment_id, scanner, asset_id=None):
        return [copy.deepcopy(r) for r in self.findings.values()
                if r["status"] == "active" and r["scanner"] == scanner
                and (asset_id is None or r["asset_id"] == asset_id)]

    def record_status_change(self, finding_id, from_status, to_status, reason,
                             import_id, changed_by):
        self.status_history.append({"finding_id": finding_id, "from": from_status,
                                    "to": to_status, "reason": reason})

    def record_ad_health(self, payload):
        pass


def _finding(rule_id, port=None, scanner="qualys_vmdr", severity="high"):
    return NormalizedFinding(kind="vulnerability", scanner=scanner, rule_id=rule_id,
                             rule_title=f"Rule {rule_id}", severity=severity, port=port)


def _host(ip, *findings):
    return ParsedHost(ip=ip, findings=list(findings))


TENANT, ENV = "t1", "e1"


def test_dedup_hash_is_stable_and_scanner_namespaced():
    a = compute_dedup_hash("asset-1", "1234", 443, scanner="qualys_vmdr")
    b = compute_dedup_hash("asset-1", "1234", 443, scanner="qualys_vmdr")
    c = compute_dedup_hash("asset-1", "1234", 443, scanner="tenable_nessus")
    d = compute_dedup_hash("asset-1", "1234", 8443, scanner="qualys_vmdr")
    assert a == b and len(a) == 64
    assert a != c, "stesso rule_id su scanner diversi non deve collidere"
    assert a != d, "porta diversa = finding diverso"


def test_dedup_updates_last_seen_and_occurrence_count():
    repo = InMemoryRepo()
    stats1 = ingest_stream(repo, iter([_host("10.0.0.1", _finding("Q1", 443))]),
                           TENANT, ENV, "import-1")
    assert stats1.created == 1 and stats1.updated == 0

    stats2 = ingest_stream(repo, iter([_host("10.0.0.1", _finding("Q1", 443))]),
                           TENANT, ENV, "import-2")
    assert stats2.created == 0 and stats2.updated == 1
    row = next(iter(repo.findings.values()))
    assert row["occurrence_count"] == 2
    assert str(row["last_import_id"]) == "import-2"
    assert row["first_seen"] <= row["last_seen"]


def test_occurrence_count_scales_over_three_scans():
    repo = InMemoryRepo()
    for i in range(3):
        ingest_stream(repo, iter([_host("10.0.0.1", _finding("Q1", 22))]),
                      TENANT, ENV, f"import-{i}")
    row = next(iter(repo.findings.values()))
    assert row["occurrence_count"] == 3


def test_auto_close_closes_missing_findings_only():
    repo = InMemoryRepo()
    # scan 1: Q1(443), Q2(22) su 10.0.0.1 + Q3 su 10.0.0.2
    ingest_stream(repo, iter([
        _host("10.0.0.1", _finding("Q1", 443), _finding("Q2", 22)),
        _host("10.0.0.2", _finding("Q3", 445)),
    ]), TENANT, ENV, "import-1")

    # scan 2 (auto_close): su 10.0.0.1 resta solo Q1; 10.0.0.2 non compare affatto
    stats = ingest_stream(repo, iter([
        _host("10.0.0.1", _finding("Q1", 443)),
    ]), TENANT, ENV, "import-2", auto_close=True)

    by_rule = {r["rule_id"]: r for r in repo.findings.values()}
    assert by_rule["Q1"]["status"] == "active"
    assert by_rule["Q2"]["status"] == "mitigated"
    assert by_rule["Q2"]["closed_at"] is not None
    assert by_rule["Q2"]["closed_by_import_id"] == "import-2"
    # host assente dal report: non viene toccato (auto-close è per-host)
    assert by_rule["Q3"]["status"] == "active"
    assert stats.auto_closed == 1


def test_auto_close_respects_scanner_scope():
    repo = InMemoryRepo()
    ingest_stream(repo, iter([
        _host("10.0.0.1", _finding("Q1", 443, scanner="qualys_vmdr"),
              _finding("N1", 443, scanner="tenable_nessus")),
    ]), TENANT, ENV, "import-1")

    ingest_stream(repo, iter([_host("10.0.0.1", _finding("Q1", 443, scanner="qualys_vmdr"))]),
                  TENANT, ENV, "import-2", auto_close=True)
    by_rule = {r["rule_id"]: r for r in repo.findings.values()}
    assert by_rule["N1"]["status"] == "active", "Nessus non deve essere chiuso da un import Qualys"
    assert by_rule["Q1"]["status"] == "active"


def test_reopen_on_reappearance():
    repo = InMemoryRepo()
    ingest_stream(repo, iter([_host("10.0.0.1", _finding("Q1", 443))]),
                  TENANT, ENV, "import-1")
    ingest_stream(repo, iter([_host("10.0.0.1", _finding("Q9", 999))]),
                  TENANT, ENV, "import-2", auto_close=True)
    row = next(r for r in repo.findings.values() if r["rule_id"] == "Q1")
    assert row["status"] == "mitigated"

    stats = ingest_stream(repo, iter([_host("10.0.0.1", _finding("Q1", 443))]),
                          TENANT, ENV, "import-3")
    row = next(r for r in repo.findings.values() if r["rule_id"] == "Q1")
    assert row["status"] == "active" and row["closed_at"] is None
    assert stats.reopened == 1
    assert repo.status_history[-1]["to"] == "active"


def test_plan_auto_close_pure():
    open_findings = [
        {"id": 1, "scanner": "qualys_vmdr", "dedup_hash": "a", "status": "active"},
        {"id": 2, "scanner": "qualys_vmdr", "dedup_hash": "b", "status": "active"},
        {"id": 3, "scanner": "pingcastle", "dedup_hash": "c", "status": "active"},
    ]
    from datetime import datetime, timezone
    closures = plan_auto_close(open_findings, {"a"}, "qualys_vmdr", "imp", datetime.now(timezone.utc))
    assert [f["id"] for f, _ in closures] == [2]


def test_manual_transitions():
    repo = InMemoryRepo()
    ingest_stream(repo, iter([_host("10.0.0.1", _finding("Q1", 443))]),
                  TENANT, ENV, "import-1")
    row = next(iter(repo.findings.values()))

    # risk accepted senza nota -> rifiutato
    try:
        transition_status(repo, row, "risk_accepted", None, "2026-12-31", None, "auditor")
        assert False, "doveva sollevare ValueError"
    except ValueError:
        pass

    changes = transition_status(repo, row, "risk_accepted", "Accettato dal CISO",
                                "2026-12-31", None, "auditor")
    assert changes["status"] == "risk_accepted" and changes["risk_accepted_until"] == "2026-12-31"
    row = next(iter(repo.findings.values()))
    assert row["closed_at"] is not None

    transition_status(repo, row, "active", "Riaperto dopo remediation", None, None, "auditor")
    row = next(iter(repo.findings.values()))
    assert row["status"] == "active" and row["closed_at"] is None


def test_identity_fallback_for_domain_wide_reports(tmp_path):
    """Report AD domain-wide (solo hostname sintetico) con match_key=fqdn:
    l'identità degrada invece di fallire."""
    from app.services.assets import identity_of
    from app.parsers.base import ParsedHost as PH
    host = PH(hostname_netbios="purple-knight-scan")
    ident = identity_of(host, "fqdn")
    assert ident is not None and ident.match_key == "netbios"
    assert identity_of(PH(), "ip") is None


def test_full_qualys_pipeline_with_fixtures():
    """Ingest end-to-end su entrambi i report Qualys di esempio."""
    repo = InMemoryRepo()
    hosts1 = get_parser("qualys_vmdr").parse(fixture("qualys_scan.xml"))
    stats1 = ingest_stream(repo, hosts1, TENANT, ENV, "imp-scan")
    assert stats1.hosts == 2 and stats1.created == 4

    hosts2 = get_parser("qualys_vmdr").parse(fixture("qualys_asset_data_report.xml"))
    stats2 = ingest_stream(repo, hosts2, TENANT, ENV, "imp-adr")
    assert stats2.hosts == 2 and stats2.created == 3
    # 10.10.1.11 (solo in qualys_scan.xml) resta aperto: auto-close è per-host
    assert len(repo.findings) == 7
