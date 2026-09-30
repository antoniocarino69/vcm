# 0004 — Contratto tenant esplicito e coerenza DB

## Contesto
Finding list consente scope globale implicito; detail/status/comment e route per ID non richiedono tenant. History/comments/moves non portano tenant_id, contrariamente ad AGENTS.md.

## Riproduzione / verifica
Riferimenti e scenari dettagliati in `docs/review-piano-portale.md`.
Scrivere regressioni prima dei fix; per API/DB/worker verificare lo stack reale.

## Comportamento atteso
Definire scope obbligatorio nelle operazioni, backfill tenant_id e FK composte. Conservare environment snapshot. Regressioni cross-tenant e migrazione su volume esistente.

## Stato
- chiusa
- branch: fix/0004-tenant-scope-migrations (impilata su fix/0009-patch-contracts)
- Chiusa da: `401920c` (test), `3ef1d37` (DB/migrazione), `8600233` (API)
- Consegnato: scope tenant esplicito (404 cross-client) su tutte le route
  esistenti; tenant_id NOT NULL + FK composte (id, tenant_id) su tutte le
  tabelle figlie; `db/migrations/0002_tenant_consistency.sql` idempotente con
  backfill su volumi popolati; snapshot ambiente conservato (findings e
  scan_imports mantengono environment_id storico).
- Evidenze: suite PostgreSQL 43 passed (inclusa parità catalogo ORM<->
  schema.sql e migrazione su volume popolato con storico figlio legacy),
  suite standard 25 passed; applicazione migrazione sul volume reale con
  backfill verificato e catalogo identico a uno schema.sql fresco;
  end-to-end live a due clienti 25/25 (upload -> import completed ->
  findings scoping -> dashboard -> report, decisioni per singolo finding).
- Vincolo residuo: le azioni bulk non esistono ancora; il loro incremento
  dovrà validare la proprietà tenant per ogni ID selezionato (#0014 P3c).
