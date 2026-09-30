"""Parser SCC (SCAP Compliance Checker, DISA/DoD) — report XCCDF e ARF.

Forme gestite:
  * **XCCDF TestResult** (``...-XCCDF-results.xml``): ogni ``rule-result``
    diventa un ``NormalizedFinding(kind='compliance')`` con Rule ID (idref
    ``..._rule`` -> STIG ID ``SV-xxxxx``), severity XCCDF -> CAT I/II/III,
    result -> pass/fail/not_reviewed/not_applicable/error.
  * **ARF** (Asset Reporting Format, ``...-ARF.xml``): nodi
    ``report-assertion`` con esito dell'assertion, associati all'asset.

Il parsing è streaming su ``iterparse``: i ``rule-result`` vengono svuotati
appena processati, i file SCC multi-benchmark restano a memoria costante.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Iterator, Optional

from .base import (BaseParser, NormalizedFinding, ParsedHost, local_tag,
                   normalize_severity, normalize_stig_category, _clean)

_XCCDF_NS = ("http://checklists.nist.gov/xccdf/1.2",
             "http://checklists.nist.gov/xccdf/1.1",
             "http://nsc.nist.gov/schema/xccdf/1.1")

_SV_RE = re.compile(r"(SV-\d{3,}(r\d+)?)", re.IGNORECASE)
_V_RE = re.compile(r"\bV-\d{3,}(r\d+)?\b", re.IGNORECASE)
_SRG_RE = re.compile(r"(SRG-[A-Z0-9\-]+)", re.IGNORECASE)

_RESULT_MAP = {
    "pass": "pass", "fail": "fail",
    "notchecked": "not_reviewed", "notapplicable": "not_applicable",
    "unknown": "not_reviewed", "error": "error",
}


class SCCParser(BaseParser):
    scanner = "scc_xccdf"
    name = "DISA SCC — XCCDF results / ARF"
    extensions = (".xml")

    @classmethod
    def sniff(cls, head: str) -> bool:
        lowered = head[:8192].lower()
        return ("xccdf" in lowered or "asset-report-collection" in lowered
                or "report-assertion" in lowered or "checklists.nist.gov" in lowered
                or ("<benchmark" in lowered and "rule-result" in lowered))

    def parse(self, path: str) -> Iterator[ParsedHost]:
        benchmark_title: Optional[str] = None
        profile_name: Optional[str] = None
        host = ParsedHost()
        saw_content = False

        for event, elem in ET.iterparse(path, events=("start", "end")):
            tag = local_tag(elem.tag)

            if event == "start" and tag in ("TestResult", "test-result"):
                profile_name = elem.attrib.get("idref") or profile_name

            if event == "end" and tag == "title" and benchmark_title is None and elem.text:
                text = elem.text.strip()
                if text:
                    benchmark_title = text

            if event == "end" and tag == "benchmark" and elem.text and elem.text.strip():
                benchmark_title = elem.text.strip()

            # identità asset nei report SCC -------------------------------------
            if event == "end" and tag == "target":
                value = (elem.text or "").strip()
                if value:
                    if _looks_ip(value):
                        host.ip = host.ip or value
                    elif "." in value:
                        host.fqdn = host.fqdn or value
                    else:
                        host.hostname_netbios = host.hostname_netbios or value
                elem.clear()

            if event == "end" and tag in ("target-address",):
                if elem.text:
                    host.ip = host.ip or elem.text.strip()
                elem.clear()

            if event == "end" and tag in ("target-id-ref",):
                if elem.text and "urn:xccdf:fact:asset:identifier" in (elem.attrib.get("system") or "localhost"):
                    host.fqdn = host.fqdn or elem.text.strip()
                elem.clear()

            # XCCDF rule-result ---------------------------------------------------
            if event == "end" and tag in ("rule-result", "rule_result"):
                finding = self._rule_result_to_finding(elem, benchmark_title, profile_name)
                if finding:
                    host.findings.append(finding)
                    saw_content = True
                elem.clear()

            # ARF report-assertion ----------------------------------------------
            if event == "end" and tag == "report-assertion":
                finding = self._assertion_to_finding(elem, benchmark_title, profile_name)
                if finding:
                    host.findings.append(finding)
                    saw_content = True
                elem.clear()

        if saw_content:
            yield host

    # ------------------------------------------------------------- XCCDF rules
    def _rule_result_to_finding(self, rr: ET.Element, benchmark: Optional[str],
                                profile: Optional[str]) -> Optional[NormalizedFinding]:
        idref = rr.attrib.get("idref", "")
        if not idref:
            return None
        weight = rr.attrib.get("weight")
        severity_raw = rr.attrib.get("severity", "unknown")

        result_raw = "unknown"
        message = None
        check_content_ref = None
        ident_systems: list[str] = []
        title = None

        for child in rr:
            tag = local_tag(child.tag).lower()
            if tag == "result":
                result_raw = (child.text or "unknown").strip().lower()
            elif tag == "title" and child.text:
                title = child.text.strip()
            elif tag == "message" and child.text and message is None:
                message = child.text.strip()
            elif tag == "ident":
                if child.text:
                    ident_systems.append(f"{child.attrib.get('system', '')}={child.text.strip()}")
            elif tag == "check":
                for sub in child:
                    if local_tag(sub.tag).lower() == "check-content-ref":
                        check_content_ref = sub.attrib.get("href")

        rule_title = title or self._humanize_rule_id(idref)
        stig_id = self._extract_stig_id(idref, ident_systems, message)
        cat = normalize_stig_category(severity_raw)

        raw = {
            "idref": idref, "weight": weight, "severity": severity_raw,
            "result": result_raw, "idents": ident_systems,
            "check_content_ref": check_content_ref, "message": message,
        }

        return NormalizedFinding(
            kind="compliance",
            scanner=self.scanner,
            rule_id=idref,
            rule_title=rule_title,
            severity=normalize_severity(severity_raw, style="stig"),
            severity_raw=f"CAT: {severity_raw}",
            stig_category=cat,
            category=self._category_from_rule_id(idref),
            benchmark=benchmark,
            profile=profile,
            result=_RESULT_MAP.get(result_raw, "not_reviewed"),
            description=_clean(message),
            scanner_output=None,
            raw=raw,
        )

    # ---------------------------------------------------------- ARF assertions
    def _assertion_to_finding(self, node: ET.Element, benchmark: Optional[str],
                              profile: Optional[str]) -> Optional[NormalizedFinding]:
        result_raw = "unknown"
        description = None
        rule_id = node.attrib.get("idref") or ""
        for child in node:
            tag = local_tag(child.tag).lower()
            if tag == "result" and child.text:
                result_raw = child.text.strip().lower()
            elif tag == "description" and child.text and description is None:
                description = child.text.strip()
            elif tag in ("title",) and child.text and not rule_id:
                rule_id = child.text.strip()

        if not rule_id:
            return None
        stig_id = self._extract_stig_id(rule_id, [], description)
        return NormalizedFinding(
            kind="compliance",
            scanner=self.scanner,
            rule_id=stig_id or rule_id,
            rule_title=self._humanize_rule_id(rule_id),
            severity="medium",
            severity_raw="from assertion",
            stig_category=normalize_stig_category("medium"),
            benchmark=benchmark,
            profile=profile,
            result=_RESULT_MAP.get(result_raw, "not_reviewed"),
            description=_clean(description),
            raw={"idref": rule_id, "result": result_raw},
        )

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _extract_stig_id(idref: str, idents: list[str], text: Optional[str]) -> Optional[str]:
        for source in (idref, " ".join(idents), text or ""):
            match = _SV_RE.search(source) or _V_RE.search(source)
            if match:
                return match.group(1).upper() if match.group(0).upper().startswith("SV") else match.group(0).upper()
            srg = _SRG_RE.search(source)
            if srg:
                return srg.group(1).upper()
        return None

    @staticmethod
    def _humanize_rule_id(idref: str) -> str:
        return idref.rsplit("_rule", 1)[0].replace("_", " ") if idref else "Unnamed rule"

    @staticmethod
    def _category_from_rule_id(idref: str) -> str:
        lowered = idref.lower()
        for marker, label in (("windows", "Windows STIG"), ("linux", "Linux STIG"),
                              ("active_directory", "Active Directory STIG"),
                              ("iis", "IIS STIG"), ("sql", "SQL Server STIG"),
                              ("office", "Office STIG"), ("browser", "Browser STIG"),
                              ("firewall", "Firewall STIG")):
            if marker in lowered:
                return label
        return "STIG"


def _looks_ip(value: str) -> bool:
    parts = value.split(".")
    return len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)
