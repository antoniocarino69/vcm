"""Registry dei parser: rilevamento formato e dispatch per scanner."""
from __future__ import annotations

from typing import Type

from .base import BaseParser, sniff_file
from .nessus import NessusParser
from .pingcastle import PingCastleParser
from .purple_knight import PurpleKnightParser
from .qualys import QualysParser
from .scc import SCCParser

ALL_PARSERS: tuple[Type[BaseParser], ...] = (
    QualysParser,
    NessusParser,
    SCCParser,
    PingCastleParser,
    PurpleKnightParser,
)

_BY_SCANNER: dict[str, Type[BaseParser]] = {p.scanner: p for p in ALL_PARSERS}


def get_parser(scanner: str) -> BaseParser:
    """Istanza del parser per lo scanner dichiarato nell'importazione."""
    try:
        return _BY_SCANNER[scanner]()
    except KeyError:
        raise ValueError(f"Scanner non supportato: {scanner!r}") from None


def detect_and_parse(path: str):
    """Sniff del formato + parsing streaming. Usato dalle importazioni 'auto'."""
    scanner = sniff_file(path)
    return get_parser(scanner).parse(path)
