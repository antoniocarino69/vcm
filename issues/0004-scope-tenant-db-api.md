# 0004 — Contratto tenant esplicito e coerenza DB

## Contesto
Finding list consente scope globale implicito; detail/status/comment e route per ID non richiedono tenant. History/comments/moves non portano tenant_id, contrariamente ad AGENTS.md.

## Riproduzione / verifica
Riferimenti e scenari dettagliati in `docs/review-piano-portale.md`.
Scrivere regressioni prima dei fix; per API/DB/worker verificare lo stack reale.

## Comportamento atteso
Definire scope obbligatorio nelle operazioni, backfill tenant_id e FK composte. Conservare environment snapshot. Regressioni cross-tenant e migrazione su volume esistente.

## Stato
- aperta
