"""Motore di rendering dei report: Executive e Technical, HTML + CSV.

Rendering stdlib-only (template string + CSS inline): gli HTML sono
print-ready (media print) e convertibili in PDF dal browser o da WeasyPrint.
Executive: solo sintesi, punteggio di postura, distribuzione rischio e
progressi di remediation — nessun dettaglio tecnico grezzo.
Technical: dettaglio per host con CVE, regola STIG, output scanner e
remediation, esportabile anche in CSV.
"""
from __future__ import annotations

import csv
import html
import io
from typing import Any

_SEV_COLORS = {"critical": "#b91c1c", "high": "#ea580c", "medium": "#ca8a04",
               "low": "#2563eb", "info": "#6b7280"}

_CSS = """
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#111827;margin:2rem}
h1{font-size:1.5rem;border-bottom:3px solid #111827;padding-bottom:.4rem}
h2{font-size:1.1rem;margin-top:2rem;color:#374151}
.kpi{display:flex;gap:1rem;flex-wrap:wrap;margin:1rem 0}
.kpi div{border:1px solid #e5e7eb;border-radius:.5rem;padding:.8rem 1.2rem;min-width:9rem}
.kpi b{display:block;font-size:1.6rem}
.bar{height:14px;border-radius:7px;background:#e5e7eb;overflow:hidden;margin:.3rem 0 1rem}
.bar span{display:block;height:100%}
table{border-collapse:collapse;width:100%;font-size:.85rem}
th,td{border:1px solid #e5e7eb;padding:.4rem .6rem;text-align:left;vertical-align:top}
th{background:#f3f4f6}
details{margin:.4rem 0}summary{cursor:pointer;font-weight:600}
pre{background:#f9fafb;padding:.6rem;white-space:pre-wrap;word-break:break-word}
.muted{color:#6b7280} .sev{font-weight:600}
@media print{.kpi div{break-inside:avoid}}
"""


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _bar(label: str, count: int, total: int, color: str) -> str:
    width = round(100 * count / total) if total else 0
    return (f'<div class="sev" style="color:{color}">{_esc(label)}: {count}</div>'
            f'<div class="bar"><span style="width:{width}%;background:{color}"></span></div>')


def _kpi(label: str, value: Any) -> str:
    return f'<div><b>{_esc(value)}</b>{_esc(label)}</div>'


# ----------------------------------------------------------------- executive
def render_executive_html(data: dict[str, Any]) -> str:
    """Report esecutivo: postura globale, distribuzione rischio, remediation."""
    severity = data.get("severity_distribution", {})
    totals = data.get("totals", {})
    total_open = sum(severity.values()) or 1
    trend = data.get("trend", [])
    closed_total = sum(row.get("closed", 0) for row in trend)

    bars = "".join(_bar(name.upper(), severity.get(name, 0), total_open, _SEV_COLORS[name])
                   for name in ["critical", "high", "medium", "low", "info"])

    trend_rows = "".join(
        f"<tr><td>{_esc(row['day'])}</td><td>{row['open']}</td><td>{row['closed']}</td></tr>"
        for row in trend[-30:])

    ad = data.get("ad_health", [])
    ad_html = "".join(
        f'<div><b>{_esc(item.get("global_score") if item.get("global_score") is not None else "n/d")}</b>'
        f'AD Health — {_esc(item["tool"])} ({_esc(item["snapshot_at"][:10])})</div>'
        for item in ad)

    return f"""<!doctype html><html lang="it"><head><meta charset="utf-8">
<title>Executive Report — {_esc(data.get('tenant_name', 'VCM'))}</title>
<style>{_CSS}</style></head><body>
<h1>Executive Security &amp; Compliance Report — {_esc(data.get('tenant_name', ''))}</h1>
<p class="muted">Ambiente: {_esc(data.get('environment_name', 'tutti'))} — generato il {_esc(data.get('generated_at', ''))}</p>
<div class="kpi">
  {_kpi('Postura (0-100)', data.get('posture_score', 'n/d'))}
  {_kpi('Finding aperti', totals.get('active', 0))}
  {_kpi('Critical + High', severity.get('critical', 0) + severity.get('high', 0))}
  {_kpi('Remediated (periodo)', closed_total)}
  {_kpi('Risk Accepted', totals.get('risk_accepted', 0))}
</div>
<h2>Distribuzione del rischio</h2>
{bars}
<div class="kpi">{ad_html}</div>
<h2>Progressi di remediation</h2>
<table><tr><th>Giorno</th><th>Aperti</><th>Chiusi</th></tr>{trend_rows}</table>
<h2>Ambiti coperti</h2>
<p>Vulnerabilità: {totals.get('vulnerabilities', 0)} aperte — Compliance (STIG/AD):
{totals.get('compliance', 0)} controlli non conformi.</p>
<p class="muted">Report di sintesi: i dettagli tecnici sono disponibili nel
Technical Report.</p>
</body></html>"""


# ----------------------------------------------------------------- technical
def render_technical_html(data: dict[str, Any]) -> str:
    """Report tecnico: dettaglio puntuale per host, CVE, STIG, remediation."""
    rows = []
    for host in data.get("hosts", []):
        findings_html = []
        for f in host.get("findings", []):
            sev_color = _SEV_COLORS.get(f.get("severity", "info"), "#6b7280")
            cves = ", ".join(f.get("cves") or []) or "—"
            extra = []
            if f.get("benchmark"):
                extra.append(f"Benchmark: {_esc(f['benchmark'])} / {_esc(f.get('profile') or '')}")
            if f.get("stig_category"):
                extra.append(f"STIG: {_esc(f['stig_category'])}")
            if f.get("result"):
                extra.append(f"Esito: {_esc(f['result'])}")
            findings_html.append(f"""
<details><summary><span class="sev" style="color:{sev_color}">[{_esc(f.get('severity', '').upper())}]</span>
{_esc(f.get('rule_id'))} — {_esc(f.get('rule_title'))}</summary>
<p>{' | '.join(extra)} | CVE: {_esc(cves)} | Porta: {_esc(f.get('port') or '—')}/{_esc(f.get('protocol') or '—')}</p>
<p><b>Descrizione:</b> {_esc((f.get('description') or '')[:2000])}</p>
<p><b>Remediation:</b> {_esc(f.get('solution') or 'n/d')}</p>
<pre>{_esc((f.get('scanner_output') or '')[:5000])}</pre>
</details>""")
        rows.append(f"""
<h2>Host {_esc(host.get('ip') or host.get('fqdn') or host.get('netbios'))}</h2>
<p class="muted">FQDN: {_esc(host.get('fqdn') or '—')} — NetBIOS: {_esc(host.get('netbios') or '—')} —
OS: {_esc(host.get('os') or 'n/d')} — Aperti: {len(host.get('findings', []))}</p>
{''.join(findings_html)}""")

    return f"""<!doctype html><html lang="it"><head><meta charset="utf-8">
<title>Technical Report — {_esc(data.get('tenant_name', 'VCM'))}</title>
<style>{_CSS}</style></head><body>
<h1>Technical Vulnerability &amp; Compliance Report — {_esc(data.get('tenant_name', ''))}</h1>
<p class="muted">Ambiente: {_esc(data.get('environment_name', 'tutti'))} — generato il {_esc(data.get('generated_at', ''))}</p>
{''.join(rows) if rows else '<p>Nessun finding aperto.</p>'}
</body></html>"""


def render_technical_csv(data: dict[str, Any]) -> str:
    """Esportazione CSV tecnica: una riga per finding, colonne stabili."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["asset_ip", "fqdn", "netbios", "os", "scanner", "kind", "rule_id",
                     "title", "severity", "stig_category", "result", "cves", "port",
                     "protocol", "cvss", "benchmark", "profile", "description",
                     "solution", "scanner_output", "status", "first_seen", "last_seen"])
    for host in data.get("hosts", []):
        for f in host.get("findings", []):
            writer.writerow([
                host.get("ip"), host.get("fqdn"), host.get("netbios"), host.get("os"),
                f.get("scanner"), f.get("kind"), f.get("rule_id"), f.get("rule_title"),
                f.get("severity"), f.get("stig_category"), f.get("result"),
                ";".join(f.get("cves") or []), f.get("port"), f.get("protocol"),
                f.get("cvss_score"), f.get("benchmark"), f.get("profile"),
                (f.get("description") or "")[:4000], f.get("solution"),
                (f.get("scanner_output") or "")[:4000], f.get("status"),
                f.get("first_seen"), f.get("last_seen"),
            ])
    return buffer.getvalue()
