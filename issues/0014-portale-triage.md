# 0014 — Finding e triage dal portale

## Contesto
API status/comment/history disponibili, GUI assente.

## Riproduzione / verifica
Riferimenti e scenari dettagliati in `docs/review-piano-portale.md`.
Scrivere regressioni prima dei fix; per API/DB/worker verificare lo stack reale.

## Comportamento atteso
P3b elenco/dettaglio e quattro stati, note/scadenza/commenti/history. P3c bulk in incremento separato, ogni ID scoped, esiti espliciti. Dipende da #0002/#0004/#0008 e upload.

## Stato
- aperta

## Updated product scope (2026-09-30)
See `docs/portal-next-steps.md`, section C. Assets and individual vulnerabilities; E. Filters — #0014, #0021.
The current request includes a shared sidebar, per-asset finding decisions,
OS/tag filtering and optional pre-upload dates/tags; proposals require scoped
API/schema increments before being presented as implemented behavior.
