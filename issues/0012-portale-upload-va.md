# 0012 — Upload VA e monitoraggio dal portale

## Contesto
API upload 202 e dettaglio import esistenti; nessun form GUI.

## Riproduzione / verifica
Riferimenti e scenari dettagliati in `docs/review-piano-portale.md`.
Scrivere regressioni prima dei fix; per API/DB/worker verificare lo stack reale.

## Comportamento atteso
Selezione cliente/ambiente/scanner/file, auto-close off di default, polling completed/failed, errori e statistiche; verifica reale upload-finding-dashboard. Dipende da P1a e #0006/#0007.

## Stato
- aperta

## Updated product scope (2026-09-30)
See `docs/portal-next-steps.md`, section D. Scan upload, optional dating and tagging — #0012, #0020.
The current request includes a shared sidebar, per-asset finding decisions,
OS/tag filtering and optional pre-upload dates/tags; proposals require scoped
API/schema increments before being presented as implemented behavior.
