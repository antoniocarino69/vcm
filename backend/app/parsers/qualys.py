"""Parser Qualys VMDR — export XML ``SCAN`` e ``ASSET_DATA_REPORT``.

Punti chiave:
  * parsing **streaming** con ``xml.etree.ElementTree.iterparse`` su eventi
    ``end`` del nodo ``HOST``: la RAM resta costante (~ pochi MB) anche su file
    XML da centinaia di MB tipici di un ASSET_DATA_REPORT;
  * ogni HOST viene svuotato (``elem.clear()`` + rimozione dal padre) appena
    emesso, quindi l'albero non cresce con il numero di host;
  * il parser è un generatore: il worker asincrono può scrivere a DB in batch
    mentre il file viene ancora letto;
  * output normalizzato ``NormalizedFinding`` con QID, CVE, CVSS, diagnosi,
    soluzione, porta/protocollo e payload grezzo (JSONB) conservato per audit.

Formati gestiti
---------------
1) ``SCAN`` (QualysGuard scan results / report "Scan Results"):
   HOST -> IP, DNS, NETBIOS, OS, SERVICES -> SERVICE -> PORT/PROTOCOL
           -> VULNS -> VULN (QID, SEVERITY, VULN_TITLE, DIAGNOSIS, SOLUTION,
           CVE_ID_LIST/CVE_ID, CVSS_BASE/CVSS3_BASE, RESULTS, FIRST/LAST_FOUND)
2) ``ASSET_DATA_REPORT``:
   HOST -> HOST_ID, IP, DNS, NETBIOS, OS,
          VULN_INFO_LIST -> VULN_INFO (QID, TYPE, SEVERITY, PORT, PROTOCOL, SSL,
          VULN -> CVE_ID_LIST/CVE_ID, TITLE, DIAGNOSIS, SOLUTION, RESULTS,
          FIRST_FOUND/LAST_FOUND)
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Iterator, Optional

from .base import BaseParser, NormalizedFinding, ParsedHost, extract_cves, local_tag, normalize_severity, _clean


def _text(elem: Optional[ET.Element], *names: str) -> Optional[str]:
    """Primo figlio con tag tra ``names`` (case-insensitive), testo ripulito."""
    if elem is None:
        return None
    wanted = {n.lower() for n in names}
    for child in elem:
        if local_tag(child.tag).lower() in wanted:
            if child.text and child.text.strip():
                return child.text.strip()
            # a volte il valore è in un figlio <VALUE>
            for sub in child:
                if local_tag(sub.tag).lower() == "value" and sub.text:
                    return sub.text.strip()
    return None


def _children(elem: ET.Element, *names: str) -> list[ET.Element]:
    wanted = {n.lower() for n in names}
    return [c for c in elem if local_tag(c.tag).lower() in wanted]


def _all(elem: ET.Element, name: str) -> list[ET.Element]:
    return [node for node in elem.iter() if local_tag(node.tag).lower() == name.lower()]


def _float(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return float(str(value).replace(",", ".").strip())
    except ValueError:
        return None


def _port(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    try:
        number = int(str(value).strip())
        return number if 0 <= number <= 65535 else None
    except ValueError:
        return None


class QualysParser(BaseParser):
    scanner = "qualys_vmdr"
    name = "Qualys VMDR (XML SCAN / ASSET_DATA_REPORT)"
    extensions = (".xml",)

    @classmethod
    def sniff(cls, head: str) -> bool:
        lowered = head[:8192].lower()
        if "qualys" not in lowered:
            return False
        return any(marker in lowered for marker in
                   ("<scan ", "<scan>", "asset_data_report", "<asset_data_report",
                    "qualys_vmdr", "<host_list", "doc_type>scan", "doc_type>asset_data_report"))

    # ---------------------------------------------------------------- parsing
    def parse(self, path: str) -> Iterator[ParsedHost]:
        context = ET.iterparse(path, events=("end",))
        for _event, elem in context:
            if local_tag(elem.tag) != "HOST":
                continue
            host = self._parse_host(elem)
            if host is not None:
                yield host
            # memoria costante: svuota l'HOST appena processato
            elem.clear()
            parent = self._parent_map(context, elem)
            if parent is not None:
                try:
                    parent.remove(elem)
                except (ValueError, TypeError):
                    pass

    @staticmethod
    def _parent_map(context: ET.iterparse, elem: ET.Element) -> Optional[ET.Element]:
        """iterparse non espone il padre: lo ricostruiamo via root, senza
        costruire mappe costose (l'albero resta piccolo grazie ai clear())."""
        root = context.root
        if root is None or root is elem:
            return None
        for node in root.iter():
            for child in node:
                if child is elem:
                    return node
        return None

    def _parse_host(self, host_elem: ET.Element) -> Optional[ParsedHost]:
        ip = _text(host_elem, "IP", "ADDRESS")
        dns = _text(host_elem, "DNS", "FQDN", "DNS_NAME")
        netbios = _text(host_elem, "NETBIOS", "NETBIOS_NAME", "HOSTNAME")
        os_name = _text(host_elem, "OS", "OPERATING_SYSTEM")
        host_id = _text(host_elem, "HOST_ID", "ID")

        host = ParsedHost(ip=ip, fqdn=dns, hostname_netbios=netbios, os=os_name, source_id=host_id)
        if not host.identity():
            return None

        # --- shape 1: SCAN (servizi -> vuln) ---------------------------------
        for service in _all(host_elem, "SERVICE"):
            s_port = _port(_text(service, "PORT"))
            s_proto = _text(service, "PROTOCOL")
            for vuln in _all(service, "VULN"):
                finding = self._vuln_to_finding(vuln, port=s_port, protocol=s_proto)
                if finding:
                    host.findings.append(finding)

        # --- shape 2: ASSET_DATA_REPORT (VULN_INFO_LIST) ---------------------
        for info in _all(host_elem, "VULN_INFO"):
            qid = _text(info, "QID")
            if not qid:
                continue
            sev = _text(info, "SEVERITY")
            i_port = _port(_text(info, "PORT"))
            i_proto = _text(info, "PROTOCOL")
            vtype = _text(info, "TYPE") or "VULN"
            # alcuni export annidano i dettagli in <VULN>, altri li mettono su VULN_INFO
            details = _children(info, "VULN") or [info]
            for vuln in details:
                finding = self._vuln_to_finding(
                    vuln,
                    port=i_port,
                    protocol=i_proto,
                    qid_override=qid,
                    severity_override=sev,
                    category_override=vtype,
                )
                if finding:
                    host.findings.append(finding)

        return host

    def _vuln_to_finding(
        self,
        vuln: ET.Element,
        port: Optional[int],
        protocol: Optional[str],
        qid_override: Optional[str] = None,
        severity_override: Optional[str] = None,
        category_override: Optional[str] = None,
    ) -> Optional[NormalizedFinding]:
        qid = qid_override or _text(vuln, "QID")
        if not qid:
            return None
        severity_raw = severity_override or _text(vuln, "SEVERITY") or "0"
        title = _text(vuln, "VULN_TITLE", "TITLE", "NAME") or f"Qualys QID {qid}"
        diagnosis = _clean(_text(vuln, "DIAGNOSIS", "THREAT", "DESCRIPTION"))
        solution = _clean(_text(vuln, "SOLUTION", "CORRECTION", "RECOMMENDATION"))
        results = _clean(_text(vuln, "RESULTS", "RESULT", "IMPACT"))

        cvss = _float(_text(vuln, "CVSS3_BASE", "CVSS3.1_BASE", "CVSS_BASE", "CVSS_SCORE"))
        cvss_vector = _text(vuln, "CVSS3_VECTOR", "CVSS3.1_VECTOR", "CVSS_VECTOR")
        bugtraq = _text(vuln, "BUGTRAQ_ID")
        vendor_refs = _text(vuln, "VENDOR_REFERENCE")

        cve_nodes: list[str] = []
        for list_node in _all(vuln, "CVE_ID_LIST"):
            for cve_node in _all(list_node, "CVE_ID"):
                if cve_node.text:
                    cve_nodes.append(cve_node.text.strip())
        cves = cve_nodes or extract_cves(diagnosis, title, bugtraq, vendor_refs)

        category = category_override or _text(vuln, "TYPE", "CATEGORY") or "Vuln"

        # payload grezzo completo per audit/JSONB (tag -> testo)
        raw: dict[str, Any] = {local_tag(child.tag): (child.text or "").strip()
                               for child in vuln if (child.text or "").strip()}

        return NormalizedFinding(
            kind="vulnerability",
            scanner=self.scanner,
            rule_id=str(qid),
            rule_title=title,
            severity=normalize_severity(severity_raw, style="numeric"),
            severity_raw=severity_raw,
            category=category,
            cvss_score=cvss,
            cvss_vector=cvss_vector,
            cves=cves,
            port=port,
            protocol=protocol,
            description=diagnosis,
            solution=solution,
            scanner_output=results,
            raw=raw,
        )
