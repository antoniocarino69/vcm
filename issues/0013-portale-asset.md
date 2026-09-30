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

## Inventory increment — 2026-09-30

- In progress on `feature/0013-scoped-asset-inventory`, based on the published
  #0019 shell branch while prior increments await PR review.
- Add a read-only tenant-scoped inventory API/UI with filters before pagination,
  current OS text/Windows/Linux/Unknown, stable sorting, asset tags, open counts,
  and asset detail with bounded findings/moves/referenced-import lists.
- Preserve current environment versus finding snapshot distinctions and list URL
  state on return. Imports are only proven references until #0020 observations.
- Editing/moving assets and finding decisions are separate increments.

## Verification

- Inventory and read-only detail implemented; see `docs/asset-inventory.md` for
  contract, provenance, synthetic previews and history coverage limits.
- Backend: 24 passed / 9 opt-in cases skipped normally; 33 passed with PostgreSQL.
- Four browser suites passed; live two-client Nessus/Qualys ingest, asset filter/
  detail, dashboard/report and HTTP scope/validation checks passed. Fixture data
  removed. No schema, lifecycle, legacy mutation routes or authentication changes.
- Published implementation: `790c70b`; remote branch hash verified. Asset editing/moving and full observation history remain open.
- Draft PR creation was rejected by the GitHub integration (HTTP 403,
  `Resource not accessible by integration`); tracked in #0026. Branch publication
  succeeded. No PR or merge is claimed.
