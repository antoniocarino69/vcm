"""Parser PingCastle (Active Directory Security).

Forme gestite:
  * **Export XML** (``ad_hc_*.xml`` / "Export XML" dal report): risk rules con
    ID, categoria (Privileged Accounts, Trust, Domain Trust, Anomalies, ...),
    punteggio di rischio, technical details e remediation;
  * **HTML report / data dump**: estrazione tabellare delle risk rules e del
    global score tramite parser HTML stdlib.

Il global score PingCastle (0-100, più alto = peggio) e i punteggi per
categoria alimentano ``ad_health_snapshots``; ogni risk rule diventa un
``NormalizedFinding(kind='compliance', scanner='pingcastle')``.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from typing import Any, Iterator, Optional

from .base import BaseParser, NormalizedFinding, ParsedHost, local_tag, _clean

_CATEGORY_MAP = {
    "privilege": "Privileged Accounts", "privileged": "Privileged Accounts",
    "trust": "Trust", "domain trust": "Domain Trust", "anomalies": "Anomalies",
    "anomaly": "Anomalies", "delegation": "Delegation", "kerberos": "Kerberos",
    "password": "Password", "patch": "Patching", "stale": "Stale Objects",
}

# Mappatura punteggio rischio PingCastle (Points) -> severità normalizzata
def _score_to_severity(points: Optional[float]) -> str:
    if points is None:
        return "info"
    if points >= 25:
        return "critical"
    if points >= 10:
        return "high"
    if points >= 5:
        return "medium"
    if points > 0:
        return "low"
    return "info"


def _text(elem: ET.Element, *names: str) -> Optional[str]:
    wanted = {n.lower() for n in names}
    for child in elem:
        if local_tag(child.tag).lower() in wanted and child.text and child.text.strip():
            return child.text.strip()
    for child in elem:
        if local_tag(child.tag).lower() in wanted:
            for sub in child:
                if sub.text and sub.text.strip():
                    return sub.text.strip()
    return None


def _float(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return float(re.sub(r"[^\d.,\-]", "", value).replace(",", "."))
    except ValueError:
        return None


class PingCastleParser(BaseParser):
    scanner = "pingcastle"
    name = "PingCastle (XML export / HTML report)"
    extensions = (".xml", ".html")

    @classmethod
    def sniff(cls, head: str) -> bool:
        lowered = head[:8192].lower()
        return ("pingcastle" in lowered or "healthcheckdata" in lowered
                or "healthcheckriskrule" in lowered or "healthcheck statistics" in lowered)

    def parse(self, path: str) -> Iterator[ParsedHost]:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            head = handle.read(4096).lower()
        if "<html" in head or "<!doctype html" in head:
            yield from self._parse_html(path)
        else:
            yield from self._parse_xml(path)

    # ------------------------------------------------------------------ XML
    def _parse_xml(self, path: str) -> Iterator[ParsedHost]:
        domain_host = ParsedHost()
        category_scores: dict[str, float] = {}
        global_score: Optional[float] = None
        domain_name: Optional[str] = None
        rule_tags = {"healthcheckriskrule", "riskrule", "rule"}
        count = 0

        for event, elem in ET.iterparse(path, events=("end",)):
            tag = local_tag(elem.tag).lower()

            if tag in ("domain", "domainname", "forest") and elem.text and not domain_name:
                domain_name = elem.text.strip()

            if tag in ("globalscore", "score", "staleobjectscore") and global_score is None and elem.text:
                value = _float(elem.text)
                if value is not None:
                    global_score = value

            if tag in rule_tags and len(elem):
                finding = self._rule_to_finding(elem)
                if finding is not None:
                    domain_host.findings.append(finding)
                    cat = finding.category or "Other"
                    points = _float(finding.raw.get("points"))
                    if points is not None:
                        category_scores[cat] = category_scores.get(cat, 0.0) + points
                    count += 1
                elem.clear()

        if domain_name:
            domain_host.fqdn = domain_name
        elif domain_host.findings:
            domain_host.hostname_netbios = "pingcastle-domain"

        domain_host.metadata = {
            "tool": "pingcastle",
            "global_score": global_score,
            "category_scores": category_scores,
            "rule_count": count,
        }
        if domain_host.findings or global_score is not None:
            yield domain_host

    def _rule_to_finding(self, rule: ET.Element) -> Optional[NormalizedFinding]:
        rule_id = _text(rule, "riskid", "id", "code", "riskcode", "ruleid", "name")
        if not rule_id:
            # struttura annidata <Rule><Id>..</Id> ecc. oppure attributi
            rule_id = rule.attrib.get("id") or rule.attrib.get("code")
        if not rule_id:
            return None

        title = _text(rule, "title", "rulename", "name", "model") or f"PingCastle rule {rule_id}"
        category_raw = _text(rule, "category", "categoryname", "type") or "Other"
        category = _CATEGORY_MAP.get(category_raw.strip().lower(), category_raw)
        points = _float(_text(rule, "points", "score", "riskscore", "globalpoints"))
        details = _clean(_text(rule, "technicaldetail", "technicaldetails", "details", "description", "note"))
        remediation = _clean(_text(rule, "remediation", "recommendation", "solution", "howtofix"))

        # oggetti affetti: elementi figli tipo <User>/<Computer>... oppure liste
        # di identificativi nei technical detail ("SRV-FILE01, SRV-APP03")
        affected = [el.text.strip() for el in rule.iter()
                    if el.text and el.text.strip() and local_tag(el.tag).lower()
                    in {"user", "computer", "group", "gpo", "ou", "trust", "spn", "object", "domain"}
                    and len(el) == 0]
        if details:
            for token in details.replace(";", ",").split(","):
                token = token.strip().strip('"\'()')
                if token and not any(ch.isspace() for ch in token) and 2 < len(token) < 64:
                    affected.append(token)
        affected = sorted({a for a in affected if len(a) < 256})[:100]

        raw: dict[str, Any] = {
            "rule_id": rule_id, "category": category_raw,
            "points": str(points) if points is not None else "",
        }

        return NormalizedFinding(
            kind="compliance",
            scanner=self.scanner,
            rule_id=str(rule_id),
            rule_title=title,
            severity=_score_to_severity(points),
            severity_raw=f"risk score {points}" if points is not None else "risk score n/d",
            category=category,
            result="fail",
            affected_objects=affected,
            description=details,
            solution=remediation,
            raw=raw,
        )

    # ----------------------------------------------------------------- HTML
    def _parse_html(self, path: str) -> Iterator[ParsedHost]:
        collector = _TableCollector()
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            for chunk in iter(lambda: handle.read(65536), ""):
                collector.feed(chunk)
        collector.close()

        host = ParsedHost(hostname_netbios="pingcastle-domain")
        global_score = None
        category_scores: dict[str, float] = {}

        for table in collector.tables:
            headers = [h.strip().lower() for h in (table[0] if table else [])]
            body = table[1:] if len(table) > 1 else []
            if not headers:
                continue
            if any("global score" in h or h == "score" for h in headers) and len(body) <= 1:
                for row in body:
                    for idx, cell in enumerate(row):
                        if idx < len(headers) and "score" in headers[idx]:
                            global_score = _float(cell) or global_score
                continue

            idx_rule = _col(headers, "id", "rule", "risk id")
            idx_title = _col(headers, "rule", "title", "name", "model")
            idx_cat = _col(headers, "category", "type")
            idx_score = _col(headers, "score", "points", "risk")
            idx_detail = _col(headers, "detail", "technical", "description")
            idx_fix = _col(headers, "remediation", "recommendation", "solution")
            if idx_rule is None and idx_title is None:
                continue

            for row in body:
                def get(i: Optional[int]) -> str:
                    return row[i].strip() if i is not None and i < len(row) else ""

                rule_id = get(idx_rule) or get(idx_title)
                if not rule_id:
                    continue
                points = _float(get(idx_score))
                category_raw = get(idx_cat) or "Other"
                category = _CATEGORY_MAP.get(category_raw.strip().lower(), category_raw)
                if points is not None:
                    category_scores[category] = category_scores.get(category, 0.0) + points
                host.findings.append(NormalizedFinding(
                    kind="compliance",
                    scanner=self.scanner,
                    rule_id=rule_id,
                    rule_title=get(idx_title) or f"PingCastle rule {rule_id}",
                    severity=_score_to_severity(points),
                    severity_raw=f"risk score {points}" if points is not None else "risk score n/d",
                    category=category,
                    result="fail",
                    description=_clean(get(idx_detail)) or None,
                    solution=_clean(get(idx_fix)) or None,
                    raw={"rule_id": rule_id, "category": category_raw,
                         "points": get(idx_score)},
                ))

        host.metadata = {"tool": "pingcastle", "global_score": global_score,
                         "category_scores": category_scores,
                         "rule_count": len(host.findings)}
        if host.findings or global_score is not None:
            yield host


def _col(headers: list[str], *needles: str) -> Optional[int]:
    for idx, header in enumerate(headers):
        if any(n in header for n in needles):
            return idx
    return None


class _TableCollector(HTMLParser):
    """Raccoglie le tabelle HTML come liste di righe di celle (stdlib only)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table: Optional[list[list[str]]] = None
        self._row: Optional[list[str]] = None
        self._cell: Optional[list[str]] = None

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if any(c.strip() for c in self._row):
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None
