"""Test dei parser: parsing reale dei fixture per tutti e cinque gli scanner."""
from conftest import fixture

from app.parsers import get_parser, detect_and_parse
from app.parsers.base import sniff_file


def _findings(path: str):
    hosts = list(get_parser(sniff_file(path)).parse(path))
    findings = [f for h in hosts for f in h.findings]
    return hosts, findings


# ------------------------------------------------------------------- Qualys
def test_qualys_scan_parser():
    hosts, findings = _findings(fixture("qualys_scan.xml"))
    assert len(hosts) == 2
    web = hosts[0]
    assert web.ip == "10.10.1.10"
    assert web.fqdn == "web01.corp.local"
    assert web.hostname_netbios == "WEB01"
    assert len(web.findings) == 3

    tls = next(f for f in web.findings if f.rule_id == "38658")
    assert tls.kind == "vulnerability"
    assert tls.severity == "high"                # SEVERITY 4
    assert tls.severity_raw == "4"
    assert tls.cves == ["CVE-2011-3389", "CVE-2014-3566"]
    assert tls.cvss_score == 7.4
    assert tls.port == 443 and tls.protocol == "tcp"
    assert "Disable TLSv1.0" in tls.solution
    assert "TLSv1.0" in tls.scanner_output

    rce = next(f for f in web.findings if f.rule_id == "90394")
    assert rce.severity == "critical"            # SEVERITY 5
    assert rce.port == 3389
    assert rce.cves == ["CVE-2021-34527"]

    smb = hosts[1].findings[0]
    assert smb.severity == "low" and smb.cvss_score == 4.3
    assert sniff_file(fixture("qualys_scan.xml")) == "qualys_vmdr"


def test_qualys_asset_data_report_parser():
    hosts, findings = _findings(fixture("qualys_asset_data_report.xml"))
    assert len(hosts) == 2
    dc = hosts[0]
    assert dc.ip == "10.10.2.20" and dc.fqdn == "dc01.corp.local"
    assert dc.source_id == "11122233"
    assert len(dc.findings) == 2

    zero = next(f for f in dc.findings if f.rule_id == "105575")
    assert zero.severity == "high"
    assert zero.cves == ["CVE-2020-1472"]
    assert zero.port == 445 and zero.protocol == "tcp"
    assert zero.cvss_score == 10.0

    info = next(f for f in dc.findings if f.rule_id == "90456")
    assert info.severity == "info"

    # stesso QID anche sul secondo host
    fs = hosts[1].findings[0]
    assert fs.rule_id == "105575" and fs.port == 445


def test_qualys_parser_is_streaming_generator():
    import inspect
    from app.parsers.qualys import QualysParser
    assert inspect.isgeneratorfunction(QualysParser.parse)


# -------------------------------------------------------------------- Nessus
def test_nessus_xml_parser():
    hosts, findings = _findings(fixture("nessus_scan.nessus"))
    assert len(hosts) == 2
    web = hosts[0]
    assert web.ip == "10.10.1.10" and web.fqdn == "web01.corp.local"
    assert web.os == "Windows Server 2019"
    assert len(web.findings) == 3

    cert = next(f for f in web.findings if f.rule_id == "35291")
    assert cert.severity == "medium"             # Risk Factor: Medium
    assert cert.severity_raw == "Medium"
    assert cert.cves == ["CVE-2020-0601"]
    assert cert.cvss_score == 6.5
    assert cert.category == "General"
    assert cert.scanner_output == "Broken chain found"

    info = next(f for f in web.findings if f.rule_id == "19506")
    assert info.severity == "info"

    lnx = hosts[1].findings[0]
    assert lnx.severity == "high" and lnx.cves == ["CVE-2023-38408"]


def test_nessus_csv_parser(tmp_path):
    csv_file = tmp_path / "nessus_export.csv"
    csv_file.write_text(
        "Plugin ID,CVE,CVSS,Risk,Host,Protocol,Port,Name,Synopsis,Description,Solution,Plugin Output\n"
        "11219,CVE-2001-0444,,None,10.0.0.5,tcp,80,HTTP TRACE / TRACK Methods,"
        "XST is enabled.,The remote server supports TRACE.,Disable TRACE.,TRACE / HTTP/1.1\n"
        "51192,,5.0,Medium,10.0.0.5,tcp,443,SSL Weak Cipher Suites,"
        "Weak ciphers supported.,Weak ciphers.,Disable weak ciphers.,TLS_RSA_WITH_NULL_SHA\n",
        encoding="utf-8")
    hosts = list(get_parser("tenable_nessus").parse(str(csv_file)))
    assert len(hosts) == 1 and hosts[0].ip == "10.0.0.5"
    assert [f.severity for f in hosts[0].findings] == ["info", "medium"]
    assert hosts[0].findings[0].rule_id == "11219"


# ----------------------------------------------------------------------- SCC
def test_scc_xccdf_parser():
    hosts, findings = _findings(fixture("scc_xccdf_results.xml"))
    assert len(hosts) == 1 and len(findings) == 4
    host = hosts[0]
    assert host.ip == "10.10.2.20" and host.fqdn == "dc01.corp.local"

    fail = [f for f in findings if f.result == "fail"]
    assert len(fail) == 2
    rule = next(f for f in findings if "SV-235870" in f.rule_id)
    assert rule.kind == "compliance"
    assert rule.stig_category == "CAT_I"         # severity=high
    assert rule.severity == "critical"
    assert rule.result == "fail"
    assert rule.benchmark and "Windows Server 2019" in rule.benchmark
    assert "HKLM" in (rule.description or "")

    cat2 = next(f for f in findings if "SV-235871" in f.rule_id)
    assert cat2.stig_category == "CAT_II" and cat2.result == "pass"

    nr = next(f for f in findings if "SV-235872" in f.rule_id)
    assert nr.stig_category == "CAT_III" and nr.result == "not_reviewed"


# ----------------------------------------------------------------- PingCastle
def test_pingcastle_xml_parser():
    hosts, findings = _findings(fixture("pingcastle_ad_hc.xml"))
    assert len(hosts) == 1 and len(findings) == 4
    host = hosts[0]
    assert host.fqdn == "corp.local"
    assert host.metadata["global_score"] == 52.0
    assert host.metadata["category_scores"]["Domain Trust"] == 25.0

    trust = next(f for f in findings if f.rule_id == "TRUST-FOREIGN")
    assert trust.kind == "compliance"
    assert trust.category == "Domain Trust"
    assert trust.severity == "critical"          # 25 punti
    assert "SID filtering" in trust.solution

    deleg = next(f for f in findings if f.rule_id == "DELEG-CONSTRAINED")
    assert deleg.severity == "high"
    assert "SRV-FILE01" in deleg.affected_objects

    priv = next(f for f in findings if f.rule_id == "PRIV-ADMINCOUNT")
    assert priv.severity == "high" and priv.result == "fail"


# --------------------------------------------------------------- Purple Knight
def test_purple_knight_csv_parser():
    hosts, findings = _findings(fixture("purple_knight_indicators.csv"))
    assert len(hosts) == 1 and len(findings) == 6
    host = hosts[0]
    assert host.metadata["tool"] == "purple_knight"

    deleg = next(f for f in findings if f.rule_id == "Unconstrained Delegation")
    assert deleg.severity == "critical"
    assert deleg.kind == "compliance"
    assert "IOE" in deleg.category and "AD Delegation" in deleg.category
    assert deleg.affected_objects == ["SRV-APP03", "SRV-FILE01"]

    ioc = next(f for f in findings if f.rule_id.startswith("Suspicious Golden"))
    assert "IOC" in ioc.category and ioc.severity == "high"
    assert "krbtgt" in ioc.solution


# ------------------------------------------------------------- sniff & dispatch
def test_sniff_detects_all_formats():
    assert sniff_file(fixture("qualys_scan.xml")) == "qualys_vmdr"
    assert sniff_file(fixture("qualys_asset_data_report.xml")) == "qualys_vmdr"
    assert sniff_file(fixture("nessus_scan.nessus")) == "tenable_nessus"
    assert sniff_file(fixture("scc_xccdf_results.xml")) == "scc_xccdf"
    assert sniff_file(fixture("pingcastle_ad_hc.xml")) == "pingcastle"
    assert sniff_file(fixture("purple_knight_indicators.csv")) == "purple_knight"


def test_detect_and_parse_end_to_end():
    hosts = list(detect_and_parse(fixture("qualys_scan.xml")))
    assert sum(len(h.findings) for h in hosts) == 4
