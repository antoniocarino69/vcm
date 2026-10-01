# 0012 — Upload VA e monitoraggio dal portale

## Contesto
API upload 202 e dettaglio import esistenti; nessun form GUI.

## Riproduzione / verifica
Riferimenti e scenari dettagliati in `docs/review-piano-portale.md`.
Scrivere regressioni prima dei fix; per API/DB/worker verificare lo stack reale.

## Comportamento atteso
Selezione cliente/ambiente/scanner/file, auto-close off di default, polling completed/failed, errori e statistiche; verifica reale upload-finding-dashboard. Dipende da P1a e #0006/#0007.

## Stato
- aperta

## Updated product scope (2026-09-30)
See `docs/portal-next-steps.md`, section D. Scan upload, optional dating and tagging — #0012, #0020.
The current request includes a shared sidebar, per-asset finding decisions,
OS/tag filtering and optional pre-upload dates/tags; proposals require scoped
API/schema increments before being presented as implemented behavior.

## Upload UI increment — 2026-10-01

Implemented on `feature/0012-report-upload`: `/imports.html`, shared sidebar
entry, validated client/environment selection, scanner detection or canonical
scanner selection, file upload, auto-close off by default, asynchronous status
polling, completion statistics, worker errors, import history and links to the
environment assets/findings. Recoverable upload errors retain the file/settings.
Late upload responses cannot replace a newly selected client's status.

Verification: new Chromium regression observed failing before implementation;
passes multipart tenant/auto-close assertions, completion, worker error display,
late upload response isolation and 390px layout. All six existing browser suites
pass. Standard backend suite: 25 passed / 23 optional DB cases skipped; opt-in
PostgreSQL suite: 48 passed. Stack rebuilt; frontend restarted for known #0025.
Live Chromium: Nessus UI upload → Celery completed → findings → dashboard →
history after reload → duplicate 409. Temporary verification clients removed;
report files remain only in Docker storage.

Issue stays open: optional assessment dates/tags (#0020), all-scanner verification,
backend robustness (#0006), and AD/compliance follow-ups (#0005/#0007).

Publication: implementation `1fec063` pushed to `origin/feature/0012-report-upload`;
remote hash verified against the local commit. The branch is based on published
`dd40dc1`; merging into main remains a separate reviewed PR step.
