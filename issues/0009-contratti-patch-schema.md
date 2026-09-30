# 0009 — Allineare PATCH e schema ORM

## Contesto
PATCH usa input di creazione e default che sovrascrivono campi omessi; modelli non riportano tutti i CHECK/indici di schema.sql.

## Riproduzione / verifica
Riferimenti e scenari dettagliati in `docs/review-piano-portale.md`.
Scrivere regressioni prima dei fix; per API/DB/worker verificare lo stack reale.

## Comportamento atteso
Schemi patch parziali, enum/IP/UUID validati, errori 404/409/422; strategia migrazioni e verifica catalogo PG. Non usare create_all come migrazione.

## Stato
- in corso
- branch: fix/0009-patch-contracts
- Consegna verificata: schemi di patch parziali (clienti/ambienti/asset),
  validazione slug/nome/kind/match_key/IP/criticality/tags, 404/409/422
  significativi su creazione e modifica. Regressioni PostgreSQL (38 passed)
  e 29 verifiche HTTP live su due clienti temporanei, poi rimossi.
- Resta aperto: strategia migrazioni versionata + allineamento CHECK/indici
  ORM (senza create_all come migrazione) e verifica catalogo PG — confluisce
  nell'incremento #0004.
