# 0002 — Reimport annulla risk acceptance e false positive

## Contesto
Review del 2026-09-30. `merge_incoming` riapre qualsiasi stato diverso da
`active`, mentre AGENTS.md richiede la riapertura dei mitigati ricomparsi.

## Riproduzione
Importare un finding, marcarlo `risk_accepted` o `false_positive`, importare
nuovamente la stessa regola sullo stesso asset: lo stato diventa `active`.

## Comportamento atteso
Il reimport aggiorna evidenze e conteggio ma conserva decisione, motivazione,
scadenza e storico. Solo `mitigated` viene riaperto automaticamente.
La gestione della scadenza dell'accettazione resta una milestone separata.

## Stato
- chiusa
- branch: fix/0002-preserva-triage-import
- chiusa dal commit `fix(#0002): preserva il triage manuale nei reimport`
- verifica: quattro regressioni fallite prima del fix; suite completa 24 passed
