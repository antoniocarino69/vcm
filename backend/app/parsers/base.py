"""Contratto comune dei parser scanner.

Ogni parser trasforma un file di report (XML/CSV/HTML) in un flusso di
``ParsedHost``: un asset con la sua lista normalizzata di ``NormalizedFinding``
(vulnerabilità o compliance). Il parsing è *streaming*: i parser sono
generatori, non accumulano l'intero documento in memoria, così file XML da
centinaia di MB girano in memoria costante e possono essere consumati da un
worker Celery in batch verso il database.

Nessuna dipendenza di terze parti: solo stdlib, per restare deployabili anche
in ambienti air-gapped.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any, Iterator, Optional

SEVERITIES = ("critical", "high", "medium", "low", "info")

# Mappature comuni dai vocabolari degli scanner alla nostra severità normalizzata
NUMERIC_SEVERITY_MAP = {5: "critical", 4: "high", 3: "medium", 2: "low", 1: "info", 0: "info"}
NESSUS_RISK_MAP = {
    "critical": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "none": "info",
    "info": "info",
}
STIG_CAT_MAP = {"cat i": "CAT_I", "cat_i": "CAT_I", "high": "CAT_I",
                "cat ii": "CAT_II", "cat_ii": "CAT_II", "medium": "CAT_II",
                "cat iii": "CAT_III", "cat_iii": "CAT_III", "low": "CAT_III"}
SCC_RESULT_MAP = {
    "pass": "pass",
    "fail": "fail",
    "notchecked": "not_reviewed",
    "notchecked ": "not_reviewed",
    "notapplicable": "not_applicable",
    "unknown": "not_reviewed",
    "error": "error",
}
PK_SEVERITY_MAP = {"critical": "critical", "high": "high", "medium": "medium", "low": "low", "informational": "info", "info": "info"}

_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_CVE_RE = re.compile(r"CVE-\d{4}-\d{4,7}", re.IGNORECASE)


def normalize_severity(value: Any, style: str = "numeric") -> str:
    """Riduce i vocabolari eterogenei degli scanner a: critical|high|medium|low|info."""
    if value is None:
        return "info"
    text = str(value).strip().lower()
    if not text:
        return "info"
    if style == "numeric":
        try:
            return NUMERIC_SEVERITY_MAP.get(int(float(text)), "info")
        except ValueError:
            pass
    if style == "stig":
        mapped = STIG_CAT_MAP.get(text)
        if mapped:
            # CAT I -> critical, CAT II -> high, CAT III -> medium
            return {"CAT_I": "critical", "CAT_II": "high", "CAT_III": "medium"}[mapped]
    mapping = {"numeric": NUMERIC_SEVERITY_MAP, "nessus": NESSUS_RISK_MAP, "pk": PK_SEVERITY_MAP}.get(style, {})
    if text in mapping:
        return mapping[text] if isinstance(mapping[text], str) else "info"
    return {"critical": "critical", "high": "high", "medium": "medium", "low": "low",
            "none": "info", "info": "info", "informational": "info"}.get(text, "info")


def normalize_stig_category(value: Any) -> Optional[str]:
    if value is None:
        return None
    return STIG_CAT_MAP.get(str(value).strip().lower())


def extract_cves(*texts: Optional[str]) -> list[str]:
    found: list[str] = []
    for text in texts:
        if not text:
            continue
        for match in _CVE_RE.findall(text):
            cve = match.upper()
            if cve not in found:
                found.append(cve)
    return found


def _clean(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    text = re.sub(r"\r\n?", "\n", text).strip()
    return text or None


@dataclass
class NormalizedFinding:
    """Elemento normalizzato: vulnerabilità oppure voce di compliance STIG/AD."""

    kind: str                                   # 'vulnerability' | 'compliance'
    scanner: str                                # scanner_type enum value
    rule_id: str                                # QID / PluginID / Rule idref / RiskId / Indicator
    rule_title: str
    severity: str                               # critical|high|medium|low|info
    category: Optional[str] = None
    severity_raw: Optional[str] = None
    stig_category: Optional[str] = None         # CAT_I | CAT_II | CAT_III
    cvss_score: Optional[float] = None
    cvss_vector: Optional[str] = None
    cves: list[str] = field(default_factory=list)
    port: Optional[int] = None
    protocol: Optional[str] = None

    # Compliance
    benchmark: Optional[str] = None
    profile: Optional[str] = None
    result: Optional[str] = None                # pass|fail|not_reviewed|not_applicable|error
    affected_objects: list[str] = field(default_factory=list)

    description: Optional[str] = None
    solution: Optional[str] = None
    scanner_output: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)

    def dedup_key(self) -> tuple[str, Optional[int]]:
        """(rule_id, port) partecipa all'hash di deduplica insieme all'asset."""
        return (self.rule_id, self.port)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ParsedHost:
    """Asset visto dallo scanner + tutti i finding emessi per esso."""

    ip: Optional[str] = None
    fqdn: Optional[str] = None
    hostname_netbios: Optional[str] = None
    os: Optional[str] = None
    source_id: Optional[str] = None             # HOST_ID Qualys, asset UUID, ...
    metadata: dict[str, Any] = field(default_factory=dict)
    findings: list[NormalizedFinding] = field(default_factory=list)

    def identity(self, match_key: str = "ip") -> Optional[str]:
        if match_key == "fqdn" and self.fqdn:
            return self.fqdn.lower()
        if match_key == "netbios" and self.hostname_netbios:
            return self.hostname_netbios.lower()
        return self.ip or self.fqdn or self.hostname_netbios

    @property
    def has_findings(self) -> bool:
        return bool(self.findings)


class BaseParser(ABC):
    """Interfaccia astratta degli scanner parser.

    Contratto:
      * ``sniff(head)`` riconosce il formato dai primi KB del file;
      * ``parse(path)`` è un generatore di ``ParsedHost`` a memoria costante;
      * il parser NON accede al database né rete: puramente testabile.
    """

    scanner: str = "unknown"
    name: str = "Base parser"
    extensions: tuple[str, ...] = ()

    @classmethod
    @abstractmethod
    def sniff(cls, head: str) -> bool:
        """True se i primi byte del file sono compatibili con questo formato."""

    @abstractmethod
    def parse(self, path: str) -> Iterator[ParsedHost]:
        """Genera gli host con i relativi finding, streaming su disco."""


def local_tag(tag: str) -> str:
    """Nome del tag XML senza namespace ({ns}TAG -> TAG)."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def sniff_file(path: str, size: int = 8192) -> str:
    """Rileva lo scanner dal contenuto del file (non dall'estensione)."""
    # Late import per evitare cicli con il registry
    from . import registry
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        head = handle.read(size)
    for parser_cls in registry.ALL_PARSERS:
        if parser_cls.sniff(head):
            return parser_cls.scanner
    raise ValueError(f"Formato scanner non riconosciuto: {path}")
