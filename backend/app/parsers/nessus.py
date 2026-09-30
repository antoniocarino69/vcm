"""Parser Tenable Nessus — file ``.nessus`` (XML) ed export CSV.

Il formato XML ``NessusClientData_v2`` viene consumato in streaming su eventi
``start``/``end``: si bufferizza un solo ``ReportHost`` alla volta e lo si
emette appena chiuso, quindi la memoria resta costante anche su scansioni con
centinaia di migliaia di ReportItem.
"""
from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from typing import Iterator, Optional

from .base import (BaseParser, NormalizedFinding, ParsedHost, extract_cves,
                   local_tag, normalize_severity, _clean)


def _first_text(elem: ET.Element, *names: str) -> Optional[str]:
    wanted = {n.lower() for n in names}
    for child in elem:
        if local_tag(child.tag).lower() in wanted and child.text and child.text.strip():
            return child.text.strip()
    return None


def _float(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _int(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


class NessusParser(BaseParser):
    scanner = "tenable_nessus"
    name = "Tenable Nessus (.nessus XML / CSV export)"
    extensions = (".nessus", ".xml", ".csv")

    @classmethod
    def sniff(cls, head: str) -> bool:
        lowered = head[:8192].lower()
        return "nessusclientdata" in lowered or "<reporthost" in lowered or "<report_item" in lowered

    def parse(self, path: str) -> Iterator[ParsedHost]:
        if path.lower().endswith(".csv") or self._looks_like_csv(path):
            yield from self._parse_csv(path)
        else:
            yield from self._parse_nessus_xml(path)

    # ------------------------------------------------------------- .nessus XML
    def _parse_nessus_xml(self, path: str) -> Iterator[ParsedHost]:
        host: Optional[ParsedHost] = None
        host_props: dict[str, str] = {}

        for event, elem in ET.iterparse(path, events=("start", "end")):
            tag = local_tag(elem.tag)

            if event == "start" and tag == "ReportHost":
                host_props = {}
                host = ParsedHost(source_id=elem.attrib.get("name"))

            elif event == "end" and tag == "tag" and host is not None:
                name = elem.attrib.get("name", "")
                if name and elem.text:
                    host_props[name.lower()] = elem.text.strip()
                elem.clear()

            elif event == "end" and tag == "ReportItem" and host is not None:
                finding = self._item_to_finding(elem)
                if finding is not None:
                    host.findings.append(finding)
                elem.clear()

            elif event == "end" and tag == "ReportHost" and host is not None:
                host.ip = host_props.get("host-ip")
                host.fqdn = host_props.get("host-fqdn") or host.hostname_netbios if False else host_props.get("host-fqdn")
                host.hostname_netbios = host_props.get("netbios-name")
                host.os = host_props.get("operating-system")
                if not host.fqdn and host.source_id and "." in (host.source_id or ""):
                    host.fqdn = host.source_id
                if host.has_findings or host.identity():
                    yield host
                host = None
                elem.clear()

    def _item_to_finding(self, item: ET.Element) -> Optional[NormalizedFinding]:
        plugin_id = item.attrib.get("pluginID")
        if not plugin_id:
            return None
        title = item.attrib.get("pluginName") or f"Nessus plugin {plugin_id}"
        family = item.attrib.get("pluginFamily")
        severity_raw = item.attrib.get("severity", "0")
        port = _int(item.attrib.get("port"))
        protocol = item.attrib.get("protocol")

        risk_factor = _first_text(item, "risk_factor")
        synopsis = _clean(_first_text(item, "synopsis"))
        description = _clean(_first_text(item, "description", "see_also"))
        solution = _clean(_first_text(item, "solution"))
        plugin_output = _clean(_first_text(item, "plugin_output"))

        cvss = _float(_first_text(item, "cvss3_base_score", "cvss_base_score", "cvss_score"))
        cvss_vector = _first_text(item, "cvss3_vector", "cvss_vector")

        cves: list[str] = []
        for child in item:
            if local_tag(child.tag).lower() == "cve" and child.text:
                cves.append(child.text.strip())
        cves = cves or extract_cves(description, plugin_output, title)

        style = "nessus" if risk_factor else "numeric"
        severity = normalize_severity(risk_factor or severity_raw, style=style)

        raw = {local_tag(c.tag): (c.text or "").strip() for c in item if (c.text or "").strip()}
        raw["pluginFamily"] = family
        raw["risk_factor"] = risk_factor

        return NormalizedFinding(
            kind="vulnerability",
            scanner=self.scanner,
            rule_id=str(plugin_id),
            rule_title=title,
            severity=severity,
            severity_raw=risk_factor or f"severity={severity_raw}",
            category=family,
            cvss_score=cvss,
            cvss_vector=cvss_vector,
            cves=cves,
            port=port,
            protocol=protocol,
            description=synopsis or description,
            solution=solution,
            scanner_output=plugin_output,
            raw=raw,
        )

    # ---------------------------------------------------------------- CSV export
    @staticmethod
    def _looks_like_csv(path: str) -> bool:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            head = handle.read(2048)
        return "," in head.splitlines()[0] if head else False

    def _parse_csv(self, path: str) -> Iterator[ParsedHost]:
        """Export CSV "Export Results" di Nessus. Le righe sono tipicamente
        raggruppate per host: si emette un host quando l'identità cambia."""
        aliases = {
            "plugin id": "plugin_id", "pluginid": "plugin_id",
            "plugin name": "name", "name": "name",
            "risk": "risk", "risk factor": "risk",
            "cve": "cve", "cves": "cve",
            "cvss": "cvss", "cvss v3.0 base score": "cvss", "cvss base score": "cvss",
            "cvss v3.0 vector": "cvss_vector", "cvss vector": "cvss_vector",
            "host": "host", "host ip": "host", "dns name": "dns", "netbios name": "netbios",
            "ip address": "host", "operating system": "os",
            "protocol": "protocol", "port": "port",
            "synopsis": "synopsis", "description": "description",
            "solution": "solution", "plugin output": "plugin_output",
            "plugin family": "family", "see also": "see_also",
        }

        current_host: Optional[ParsedHost] = None
        current_key: Optional[str] = None

        with open(path, "r", encoding="utf-8-sig", newline="", errors="ignore") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                mapped = {aliases.get(k.strip().lower()): (v or "").strip()
                          for k, v in row.items() if k}
                host_value = mapped.get("host") or mapped.get("dns") or mapped.get("netbios") or ""
                if not host_value:
                    continue

                ip = host_value if _looks_ip(host_value) else (mapped.get("host") if _looks_ip(mapped.get("host", "")) else None)
                fqdn = mapped.get("dns") or (host_value if not ip else None)
                if current_key != host_value:
                    if current_host is not None:
                        yield current_host
                    current_key = host_value
                    current_host = ParsedHost(
                        ip=ip, fqdn=fqdn, hostname_netbios=mapped.get("netbios"),
                        os=mapped.get("os") or None, source_id=host_value,
                    )

                severity_raw = mapped.get("risk") or "info"
                cves = [c.strip().upper() for c in mapped.get("cve", "").split(",") if c.strip()]
                current_host.findings.append(NormalizedFinding(
                    kind="vulnerability",
                    scanner=self.scanner,
                    rule_id=mapped.get("plugin_id") or mapped.get("name") or "unknown",
                    rule_title=mapped.get("name") or f"Nessus plugin {mapped.get('plugin_id')}",
                    severity=normalize_severity(severity_raw, style="nessus"),
                    severity_raw=severity_raw,
                    category=mapped.get("family") or None,
                    cvss_score=_float(mapped.get("cvss")),
                    cvss_vector=mapped.get("cvss_vector") or None,
                    cves=cves or extract_cves(mapped.get("description"), mapped.get("plugin_output")),
                    port=_int(mapped.get("port")),
                    protocol=mapped.get("protocol") or None,
                    description=_clean(mapped.get("synopsis") or mapped.get("description")),
                    solution=_clean(mapped.get("solution")),
                    scanner_output=_clean(mapped.get("plugin_output")),
                    raw=mapped,
                ))

        if current_host is not None:
            yield current_host


def _looks_ip(value: Optional[str]) -> bool:
    if not value:
        return False
    parts = value.split(".")
    return len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)
