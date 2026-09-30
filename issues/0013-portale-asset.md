# 0013 — Inventario asset e storico nel portale

## Contesto
API asset presenti, GUI mostra solo top host.

## Riproduzione / verifica
Riferimenti e scenari dettagliati in `docs/review-piano-portale.md`.
Scrivere regressioni prima dei fix; per API/DB/worker verificare lo stack reale.

## Comportamento atteso
Lista paginata/filtrata, dettaglio, tag/criticità, spostamento intra-tenant con snapshot storico preservato. Dipende da scope e gestione ambienti.

## Stato
- aperta

## Updated product scope (2026-09-30)
See `docs/portal-next-steps.md`, section C. Assets and individual vulnerabilities; E. Filters — #0013, #0021.
The current request includes a shared sidebar, per-asset finding decisions,
OS/tag filtering and optional pre-upload dates/tags; proposals require scoped
API/schema increments before being presented as implemented behavior.
