# 0009 — Allineare PATCH e schema ORM

## Contesto
PATCH usa input di creazione e default che sovrascrivono campi omessi; modelli non riportano tutti i CHECK/indici di schema.sql.

## Riproduzione / verifica
Riferimenti e scenari dettagliati in `docs/review-piano-portale.md`.
Scrivere regressioni prima dei fix; per API/DB/worker verificare lo stack reale.

## Comportamento atteso
Schemi patch parziali, enum/IP/UUID validati, errori 404/409/422; strategia migrazioni e verifica catalogo PG. Non usare create_all come migrazione.

## Stato
- chiusa
- branch: fix/0009-patch-contracts (PATCH parziali) e
  fix/0004-tenant-scope-migrations (migrazioni + allineamento schema/ORM)
- Chiusa da: `9c1631d` (PATCH/4xx), `3ef1d37` (migrazioni + modelli 1:1),
  `401920c` (regressioni, incl. parità catalogo)
- Consegnato: schemi di patch parziali (clienti/ambienti/asset),
  validazione slug/nome/kind/match_key/IP/criticality/tags, 404/409/422
  significativi su creazione e modifica. Strategia migrazioni versionata in
  `db/migrations/` (README + 0002 idempotente) senza usare create_all come
  migrazione; modelli allineati 1:1 a schema.sql (CHECK, UNIQUE, FK composte
  con gli stessi nomi) e verifica catalogo PG automatizzata.
- Evidenze: regressioni PostgreSQL 38 passed all'epoca dei contratti PATCH e
  43 passed a incremento completato; 29 verifiche HTTP live su due clienti
  temporanei per i contratti, 25/25 per l'end-to-end scoped; catalogo del
  volume migrato identico a uno schema.sql fresco (FK e CHECK).
