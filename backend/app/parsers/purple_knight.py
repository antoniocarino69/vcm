"""Parser Purple Knight (Semperis) — indicatori di esposizione/compromissione AD.

Forme gestite:
  * **Export CSV** degli indicatori (Indicator Name, IOE/IOC, Category,
    Severity/Score, Description, Remediation, Affected Objects);
  * **Report HTML** con tabella indicatori (fallback con parser stdlib).

Ogni indicatore diventa un ``NormalizedFinding(kind='compliance',
scanner='purple_knight')`` con lista ``affected_objects`` (utenti/computer/
deleghe colpiti) — alimenta la card "AD Health Score" e le viste AD dedicate.
"""
from __future__ import annotations

import csv
import re
from typing import Iterator, Optional

from .base import (BaseParser, NormalizedFinding, ParsedHost,
                   PK_SEVERITY_MAP, _clean)

_HEADER_ALIASES = {
    "indicator name": "name", "indicator": "name", "name": "name",
    "indicator type": "type", "type": "type",
    "ioe/ioc": "type", "ioe or ioc": "type",
    "category": "category",
    "severity": "severity", "risk level": "severity",
    "score": "score", "risk score": "score",
    "description": "description", "summary": "description",
    "remediation": "remediation", "recommendation": "remediation", "solution": "remediation",
    "affected objects": "affected", "affected": "affected",
    "impacted objects": "affected", "objects": "affected",
    "technical detail": "details", "technical details": "details", "details": "details",
}


def _score_to_severity(score: Optional[float], raw: str) -> str:
    mapped = PK_SEVERITY_MAP.get(raw.strip().lower())
    if mapped:
        return mapped
    if score is None:
        return "info"
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _float(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return float(re.sub(r"[^\d.,\-]", "", value).replace(",", "."))
    except ValueError:
        return None


def _split_objects(text: Optional[str]) -> list[str]:
    if not text:
        return []
    parts = re.split(r"[;|,\n]+", text)
    return sorted({p.strip() for p in parts if p.strip()})


class PurpleKnightParser(BaseParser):
    scanner = "purple_knight"
    name = "Purple Knight (CSV indicator export / HTML report)"
    extensions = (".csv", ".html")

    @classmethod
    def sniff(cls, head: str) -> bool:
        lowered = head[:8192].lower()
        return ("purple knight" in lowered or "purpleknight" in lowered
                or "semperis" in lowered
                or ("indicator of exposure" in lowered and "indicator of compromise" in lowered)
                or ("indicator name" in lowered and ("ioe" in lowered or "ioc" in lowered)))

    def parse(self, path: str) -> Iterator[ParsedHost]:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            head = handle.read(4096).lower()
        if "<html" in head or "<!doctype html" in head:
            yield from self._parse_html(path)
        else:
            yield from self._parse_csv(path)

    # ------------------------------------------------------------------ CSV
    def _parse_csv(self, path: str) -> Iterator[ParsedHost]:
        host = ParsedHost(hostname_netbios="purple-knight-scan")
        with open(path, "r", encoding="utf-8-sig", newline="", errors="ignore") as handle:
            sniff = handle.read(2048)
            handle.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sniff, delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(handle, dialect=dialect)
            for row in reader:
                mapped = {_HEADER_ALIASES.get(k.strip().lower()): (v or "").strip()
                          for k, v in row.items() if k}
                name = mapped.get("name") or ""
                if not name:
                    continue
                finding = self._row_to_finding(mapped, name)
                if finding:
                    host.findings.append(finding)

        host.metadata = {"tool": "purple_knight", "indicator_count": len(host.findings),
                         "global_score": self._score_from_findings(host.findings)}
        if host.findings:
            yield host

    def _row_to_finding(self, mapped: dict[str, str], name: str) -> Optional[NormalizedFinding]:
        score = _float(mapped.get("score"))
        severity_raw = mapped.get("severity") or ""
        indicator_type = (mapped.get("type") or "").strip().upper()
        category = mapped.get("category") or "Account Hygiene"
        details = _clean(mapped.get("details") or mapped.get("description"))
        description = _clean(mapped.get("description"))
        remediation = _clean(mapped.get("remediation"))
        affected = _split_objects(mapped.get("affected"))

        return NormalizedFinding(
            kind="compliance",
            scanner=self.scanner,
            rule_id=name,
            rule_title=name,
            severity=_score_to_severity(score, severity_raw),
            severity_raw=severity_raw or (f"score {score}" if score is not None else "n/d"),
            category=category if not indicator_type else f"{indicator_type}: {category}",
            result="fail",
            affected_objects=affected,
            description=description or details,
            solution=remediation,
            scanner_output=details,
            raw={k: v for k, v in mapped.items() if v},
        )

    # ----------------------------------------------------------------- HTML
    def _parse_html(self, path: str) -> Iterator[ParsedHost]:
        from .pingcastle import _TableCollector, _col

        collector = _TableCollector()
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            for chunk in iter(lambda: handle.read(65536), ""):
                collector.feed(chunk)
        collector.close()

        host = ParsedHost(hostname_netbios="purple-knight-scan")
        for table in collector.tables:
            headers = [h.strip().lower() for h in (table[0] if table else [])]
            if not any("indicator" in h for h in headers):
                continue
            idx = {key: _col(headers, *needles)
                   for key, needles in (
                       ("name", ("indicator name", "indicator", "name")),
                       ("type", ("ioe", "ioc", "type")),
                       ("category", ("category",)),
                       ("severity", ("severity", "risk level")),
                       ("score", ("score",)),
                       ("description", ("description", "summary")),
                       ("remediation", ("remediation", "recommendation")),
                       ("affected", ("affected", "impacted", "objects")),
                       ("details", ("detail",)),
                   )}
            for row in table[1:]:
                mapped = {key: (row[i].strip() if i is not None and i < len(row) else "")
                          for key, i in idx.items()}
                if mapped.get("name"):
                    finding = self._row_to_finding(mapped, mapped["name"])
                    if finding:
                        host.findings.append(finding)

        host.metadata = {"tool": "purple_knight", "indicator_count": len(host.findings),
                         "global_score": self._score_from_findings(host.findings)}
        if host.findings:
            yield host

    @staticmethod
    def _score_from_findings(findings: list[NormalizedFinding]) -> Optional[float]:
        if not findings:
            return None
        weights = {"critical": 90, "high": 70, "medium": 50, "low": 25, "info": 5}
        return round(sum(weights.get(f.severity, 5) for f in findings) / len(findings), 1)
