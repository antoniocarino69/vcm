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
