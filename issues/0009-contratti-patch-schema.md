# 0009 — Allineare PATCH e schema ORM

## Contesto
PATCH usa input di creazione e default che sovrascrivono campi omessi; modelli non riportano tutti i CHECK/indici di schema.sql.

## Riproduzione / verifica
Riferimenti e scenari dettagliati in `docs/review-piano-portale.md`.
Scrivere regressioni prima dei fix; per API/DB/worker verificare lo stack reale.

## Comportamento atteso
Schemi patch parziali, enum/IP/UUID validati, errori 404/409/422; strategia migrazioni e verifica catalogo PG. Non usare create_all come migrazione.

## Stato
- aperta
