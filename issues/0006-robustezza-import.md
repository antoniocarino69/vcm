# 0006 — Upload e dispatch degli import robusti

## Contesto
Upload legge tutto in RAM, alias scanner non canonicalizzati; commit precede dispatch Celery e catch DB generico restituisce 409 anche per altri errori. Assenti guardie per riesecuzione e concorrenza.

## Riproduzione / verifica
Riferimenti e scenari dettagliati in `docs/review-piano-portale.md`.
Scrivere regressioni prima dei fix; per API/DB/worker verificare lo stack reale.

## Comportamento atteso
Incrementi separati: chunk/limite/hash/pulizia; alias ed errori; dispatch recuperabile/idempotenza. Test broker indisponibile, import concorrenti, retry e politica file identici per ambiente.

## Stato
- aperta
