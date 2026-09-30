# Implementation status

Updated: 2026-09-30. Product text and new documentation use English.

The active product checklist is [portal-next-steps.md](portal-next-steps.md).
It includes sidebar redesign, individual asset/finding workflows, optional
scan dates/tags, OS/tag filters and separate VA/remediation campaigns.

Origin is configured to `git@github.com:antoniocarino69/vcm.git`. Initial
publication succeeded through the existing authorized SSH key (#0024).
All six completed working branches are published with upstream tracking;
remote main was not overwritten. The complete current work is on
`docs/0018-operational-portal-checklist` until PR review/merge.

## Completed increments

| Issue | Result | Verification |
|---|---|---|
| #0002 | Reimports preserve risk acceptance and false-positive decisions; mitigated findings still reopen | Four regression cases; included in the rebuilt API/worker |
| #0003 | Dashboard top hosts and AD snapshots respect tenant/environment scope, including the Executive report data | Five PostgreSQL regression cases; real upload → completed import → findings → dashboard → report with two tenants |
| #0011 P1a | Client/environment creation and selection at `/clients.html` | Real Chromium browser creation and refresh against the live API; mobile layout; separate mocked browser regression for errors, safe text and stale responses |
| #0008 | Dashboard uses safe text rendering and refreshes environment/import context when switching clients; unscoped report links are disabled | Browser regression failed before the fix, then passed; late import responses cannot replace the selected client's data |
| #0017 | Dashboard and generated report labels use English | Rebuilt API/worker; live HTML reports checked |

The portal is published on `0.0.0.0:8080`. No authentication was added.
Client and environment editing/archiving remain #0011 P1b. Campaigns, finding
triage UI and upload UI remain separate planned increments.

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
NODE_PATH=/root/pw-tools/node_modules node frontend/tests/dashboard.browser.cjs
```

For another URL, set `VCM_PORTAL_URL`. API/worker changes were checked with:

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

## Known remaining constraints

API scope hardening and database tenant constraints remain #0004. Creation
uses the existing endpoints: browser duplicate checks provide immediate
feedback, but concurrent conflicting requests still need the API validation
and error handling planned in #0009. AD fallback, upload robustness and
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
