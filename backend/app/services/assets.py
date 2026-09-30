"""Riconciliazione asset: chiave di matching configurabile per ambiente.

La chiave (``environments.match_key``) è ``ip`` | ``fqdn`` | ``netbios``.
La stessa macchina vista da Qualys (IP+DNS) e da SCC (FQDN) converge sullo
stesso record asset; i campi identitativi mancanti vengono arricchiti via via
che gli scanner li forniscono, senza mai sovrascrivere dati già presenti con
valori vuoti.

Spostamenti tra ambienti: ``move_asset`` registra la transizione in
``asset_moves``; storico scansioni e commenti restano integri perché findings
e scan_imports conservano l'``environment_id`` dello snapshot all'epoca
dell'importazione.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from ..parsers.base import ParsedHost


@dataclass
class AssetIdentity:
    match_key: str
    value: str


def canonical(value: Optional[str]) -> Optional[str]:
    return value.strip().lower() if value and value.strip() else None


def identity_of(host: ParsedHost, match_key: str) -> Optional[AssetIdentity]:
    """Chiave di matching normalizzata dell'host appena parsato.

    Se la chiave preferita dell'ambiente non è disponibile (es. report AD
    domain-wide senza FQDN), si degrada all'identità disponibile successiva:
    l'ingest non deve fallire per report che descrivono il dominio/la postura
    complessiva invece di singoli host.
    """
    order = {"fqdn": ("fqdn", "ip", "netbios"),
             "netbios": ("netbios", "fqdn", "ip"),
             "ip": ("ip", "fqdn", "netbios")}.get(match_key, ("ip", "fqdn", "netbios"))
    for key in order:
        if key == "fqdn":
            value = canonical(host.fqdn)
        elif key == "netbios":
            value = canonical(host.hostname_netbios)
        else:
            value = host.ip or canonical(host.fqdn)
        if value:
            return AssetIdentity(match_key=key, value=value)
    return None


def merge_asset(existing: dict[str, Any], host: ParsedHost) -> dict[str, Any]:
    """Arricchisce l'asset esistente con le identità fornite dal nuovo report.

    Ritorna il diff da applicare (solo campi effettivamente migliorati).
    """
    changes: dict[str, Any] = {}
    for field_name, incoming in (("ip", host.ip), ("fqdn", canonical(host.fqdn)),
                                 ("hostname_netbios", canonical(host.hostname_netbios)),
                                 ("os", host.os)):
        if incoming and not existing.get(field_name):
            changes[field_name] = incoming
        elif incoming and field_name == "os" and existing.get(field_name) != incoming:
            # l'OS dichiarato dallo scanner più recente vince (si affina nel tempo)
            changes[field_name] = incoming
    if not changes:
        return {}
    return changes


def move_asset(asset_id: str, from_environment_id: Optional[str],
               to_environment_id: str, reason: Optional[str] = None) -> dict[str, Any]:
    """Payload della transizione di ambiente (registrata in asset_moves)."""
    if from_environment_id == to_environment_id:
        raise ValueError("L'asset è già in questo ambiente")
    return {
        "asset_id": asset_id,
        "from_environment_id": from_environment_id,
        "to_environment_id": to_environment_id,
        "reason": reason,
    }
