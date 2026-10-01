# Implementation status

Updated: 2026-10-01. Product text and new documentation use English.

The active product checklist is [portal-next-steps.md](portal-next-steps.md).
It includes sidebar redesign, individual asset/finding workflows, optional
scan dates/tags, OS/tag filters and separate VA/remediation campaigns.

Origin is configured to `git@github.com:antoniocarino69/vcm.git`. Initial
publication succeeded through the existing authorized SSH key (#0024).
All six completed working branches are published with upstream tracking;
remote main was not overwritten. The published plan is on `docs/0018-operational-portal-checklist`.
GitHub state reconciled on 2026-09-30: PR #1 (`docs/0018-operational-portal-checklist`)
and PR #2 (`feature/0013-scoped-asset-inventory`) were merged into `main` as
merge commit `19c3d69`. Sidebar, client/environment management, asset inventory
and read-only asset detail are therefore on `main`; the inventory branch is no
longer pending review.

## Completed increments

| Issue | Result | Verification |
|---|---|---|
| #0002 | Reimports preserve risk acceptance and false-positive decisions; mitigated findings still reopen | Four regression cases; included in the rebuilt API/worker |
| #0003 | Dashboard top hosts and AD snapshots respect tenant/environment scope, including the Executive report data | Five PostgreSQL regression cases; real upload → completed import → findings → dashboard → report with two tenants |
| #0011 P1a | Client/environment creation and selection at `/clients.html` | Real Chromium browser creation and refresh against the live API; mobile layout; separate mocked browser regression for errors, safe text and stale responses |
| #0008 | Dashboard uses safe text rendering and refreshes environment/import context when switching clients; unscoped report links are disabled | Browser regression failed before the fix, then passed; late import responses cannot replace the selected client's data |
| #0017 | Dashboard and generated report labels use English | Rebuilt API/worker; live HTML reports checked |

The portal is published on `0.0.0.0:8080`. No authentication was added.
Client/environment editing is delivered (#0011 P1b); client archiving behavior
is defined but intentionally not exposed yet. Individual finding triage is delivered on the current working branch. Basic
report upload is delivered by the increment below; campaigns and optional
import metadata remain open. These later branches are not merged into main.

## Verification commands

The standard suite does not require a database:

```sh
.venv/bin/python -m pytest backend/tests -q
```

PostgreSQL regressions are opt-in and roll back their fixture data. Use the
development database URL configured for your stack:

```sh
VCM_TEST_DATABASE_URL='<development database URL>' .venv/bin/python -m pytest backend/tests -q
```

Browser regressions require an existing Playwright/Chromium installation and
the portal running on port 8080. They mock API data and do not create database
records or add application runtime dependencies:

```sh
NODE_PATH=/root/pw-tools/node_modules node frontend/tests/clients.browser.cjs
NODE_PATH=/root/pw-tools/node_modules node frontend/tests/clients-edit.browser.cjs
NODE_PATH=/root/pw-tools/node_modules node frontend/tests/dashboard.browser.cjs
```

For another URL, set `VCM_PORTAL_URL`. API/worker changes were checked with:

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

## Known remaining constraints

API scope hardening and database tenant constraints are delivered (#0004).
Creation and edits use validated endpoints with 404/409/422 handling (#0009);
portal editing UI is delivered (#0011 P1b). AD fallback, upload robustness and
compliance lifecycle fixes remain #0005–#0007. No milestone is marked complete
solely because its first increment is delivered.

## Shared shell increment (#0019)

Overview and Clients & environments now share a desktop sidebar and mobile menu.
Client/environment context is retained between these pages; Overview offers an
explicit all-client summary and validates environment ownership before applying
its dashboard/import/report filter. Chart.js 4.4.8 is served locally.
See [design, provenance and synthetic previews](portal-shell-design.md).

Backend suite: 24 passed, 5 optional PostgreSQL tests skipped. All three browser
scripts passed. Live two-client Nessus/Qualys upload/import/finding/dashboard/
report checks and mobile navigation passed; temporary fixture records removed.
Implementation published as `c4346e0` on `feature/0019-shared-portal-shell`
with the remote hash verified. Asset/finding UI and
broader #0019 acceptance remain open. During rebuild, nginx needed a restart to
resolve the recreated API's address; deployment follow-up is tracked in #0025.

## Scoped asset inventory increment (#0013, #0021)

The shared sidebar now includes Assets. `/assets.html` supports client/current-
environment scope, server-side OS/identity/asset-tag filters, stable sorting,
counts and pagination. `/asset.html` shows identities/current attributes, retained
finding snapshots, environment moves and proven latest/closure import references.
Returning restores the list query/page/focus. See [contract and previews](asset-inventory.md).

Standard suite: 24 passed / 9 optional DB cases skipped; PostgreSQL suite: 33 passed.
Four mocked browser suites and the real two-client Nessus/Qualys upload → completed
import → assets/findings → dashboard/report flow passed, including live asset
browser navigation and HTTP scope/validation checks. Temporary test clients removed.
Implementation published as `790c70b` on `feature/0013-scoped-asset-inventory`; remote branch hash verified.
Asset mutations, finding decisions, complete observation history and broader
OS/tag/export filtering remain separate increments.

Draft PR creation for the inventory increment failed with GitHub connector HTTP
403 (`Resource not accessible by integration`), tracked in #0026. A PR was later
created and merged as PR #2 (`19c3d69`); the connector limitation remains worth
monitoring for future PRs.

## Partial PATCH contract increment (#0009)

`PATCH /api/tenants/{id}` (new), `PATCH /api/environments/{id}` and
`PATCH /api/assets/{id}` now apply only the fields explicitly provided: omitted
metadata (name, slug, kind, match_key, tags, criticality, identities, OS) is
preserved. Input schemas validate slug/name text, environment kind/match_key,
asset IP (single address, not a network), criticality 1-5 and string tag maps.
Duplicate tenant slugs and duplicate environment names within one client give
409; missing targets give 404; empty PATCH bodies and invalid values give 422.
Creation endpoints gained the same validation and 409 handling instead of 500.
Client status/archiving is deliberately not editable yet.

Verification: test regressions written first (observed failing), standard suite
25 passed / 13 optional DB cases skipped, PostgreSQL suite 38 passed, and 29
live HTTP checks against the rebuilt stack with two temporary clients
(including cross-client same-name environments). Temporary client records were
removed after verification. Portal editing UI remains a separate increment
(#0011 P1b); versioned migrations and ORM constraint alignment are delivered
with #0004.

## Tenant scope and consistency increment (#0004, #0009 remainder)

Every list/detail/comment/transition/mutation route now requires an explicit
`tenant_id` and answers 404 for environment, asset, import or finding IDs that
belong to another client (`backend/app/api/scope.py`). Child rows (asset moves,
finding status history, finding comments) carry `tenant_id` NOT NULL and all
child tables gained composite `(id, tenant_id)` foreign keys; helper unique
indexes support the composite targets. `db/migrations/0002_tenant_consistency.sql`
backfills legacy rows on populated volumes and is idempotent;
`db/migrations/README.md` records the versioned-migration policy (schema.sql
stays the fresh-install truth). `models.py` is aligned 1:1 with schema.sql
(CHECK, UNIQUE and named composite FKs) and
`test_schema_orm_parity_postgres.py` compares both catalogs automatically.

Verification: regressions written first (observed failing: 4 failed + 4 errors),
then standard suite 25 passed / 18 optional DB cases skipped and PostgreSQL
suite 43 passed (migration on a reshaped populated volume with legacy
history/comments/moves, idempotent re-run, cross-tenant child rejection, ORM
catalog parity). Migration applied to the real development volume: backfill
verified and the FK catalog matched a fresh schema.sql database exactly.
Two-tenant live end-to-end run passed 25/25 checks (upload → import completed →
scoped findings/dashboard/report; cross-scope 4xx; per-finding decisions leave
the other client untouched); temporary clients removed afterwards. Known issue
#0025 reproduced live (502 after API recreation) and recovered with
`docker compose restart frontend`; its fix remains a separate increment.

## Client/environment editing increment (#0011 P1b)

`/clients.html` gained an "Edit selected client" form (name, key, description)
and per-row environment editing (name, type, match key). Saving sends truly
partial PATCH bodies with only the changed fields; duplicates report the server
409 message inline, invalid values report 422, and a save without changes
answers "No changes to save." without any request. Scope guards hold: a late
PATCH response or a late environment creation never updates the client selected
in the meantime. Client archiving is defined (status-only transition; history
stays readable; archived clients receive nothing new; explicit filter; no
deletion) and deliberately not exposed yet.

Verification: `frontend/tests/clients-edit.browser.cjs` written first and
observed failing, then passing; the four existing browser suites pass after
form-scoped selector updates; a live UI↔API flow on the real stack created,
edited and re-read a temporary client and environment (including mobile at
390px); temporary records removed.

## Individual finding workflow increment (#0014 P3b)

`/vulnerabilities.html` lists one row per finding/asset/port with client/
environment scope, text/status/severity/scanner/type filters applied before
pagination, and return-position preservation. `/finding.html` renders the
asset context and tags, normalized plus scanner severity, CVSS/CVEs,
description and solution, raw scanner evidence, first/last observation,
proven latest/closure imports, comments and full status history. The decision
form supports Open/Mitigated/False positive/Risk accepted on the existing
status values with a reason (mandatory for risk acceptance) and an optional
acceptance expiry; each decision targets exactly one finding ID.

Verification: backend regressions written first and observed failing (3
failed: list shape, filters, detail provenance), then 48 passed with
PostgreSQL including per-asset and per-port decision independence; the new
`frontend/tests/findings.browser.cjs` and all five existing browser suites
pass; a live run uploaded a real Qualys export and accepted QID 105575 on one
server through the portal while the sibling server's finding stayed active.
Bulk actions remain a separate increment (#0014 P3c).

## Basic report upload increment (#0012)

`/imports.html` is accessible from Scan imports in the shared sidebar. Select
a client/environment, scanner or automatic detection, and a report file.
Auto-close is off by default. The page polls asynchronous imports, shows
completion statistics and worker errors, lists import history, and links to
the selected environment's assets/findings. Late upload responses are discarded
after a scope change; recoverable upload errors retain file/settings.

Verification on 2026-10-01: new browser regression failed before implementation,
then passed scoped multipart fields, opt-in auto-close, completion/error states,
stale upload isolation and mobile layout. Six existing browser suites pass;
backend standard suite 25 passed / 23 skipped and PostgreSQL suite 48 passed.
Real stack rebuilt; live Chromium Nessus upload completed through Celery, with
findings/dashboard/history and duplicate 409 verified. Temporary clients removed.
Optional date/tag metadata and #0005–#0007 prerequisites remain open; this is a
completed basic UI increment, not completion of the entire upload milestone.

[Repository/publication audit and focused review](review-2026-10-01.md).

Published implementation: `1fec063` on `feature/0012-report-upload`; remote
branch hash matches the local commit. Main was not changed.
