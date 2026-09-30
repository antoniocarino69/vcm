# Asset inventory and retained snapshots (#0013, #0021)

Verified on 2026-09-30. This read-only increment adds `/assets.html` and
`/asset.html` to the shared shell. Select a client, optionally an environment,
apply filters, open an asset and return to the same filtered list/page/position.
Each row shows IP, FQDN/NetBIOS, current OS, current environment, criticality,
asset tags, last observation and open finding counts. Sorting is stable, with
asset ID breaking ties; null values sort last in either direction. The View
column stays visible while the table scrolls horizontally. Table regions are
keyboard-focusable; client switching invalidates pending requests.

## Filter contract

`GET /api/assets` requires `tenant_id`. It validates environment ownership and
joins the asset's current environment under the same tenant. Filters run in SQL
before total count and pagination. Defaults: 50 rows, maximum 200; offset must
be nonnegative. Sort choices: ip, fqdn, os, environment, criticality, last_seen,
open_findings; direction asc/desc. Search terms treat `%` and `_` literally.

- `search`: substring in IP, FQDN or NetBIOS.
- `os_search`: case-insensitive substring in the original current OS text.
- `os_family=windows`: OS text contains Windows.
- `os_family=linux`: case-insensitive word markers Linux, Ubuntu, Debian, RHEL,
  Red Hat, CentOS, Fedora, Rocky Linux, AlmaLinux, SUSE or openSUSE. This is an
  explicit text classification, not evidence inferred from hostnames or scores.
- `os_family=unknown`: null OS or text containing only spaces, tabs or line breaks.
- Repeated `tag`: existing asset JSONB key or key:value matching. All tags and
  different fields combine with AND. The UI accepts one tag per line; it names
  Asset as the source and does not combine environment or scan-import tags.

Original OS text and asset tags are returned unchanged. The inventory's
environment filter is the asset's current location. Open counts include all
active finding snapshots of that asset under its client, including previous
environments. The UI labels this distinction explicitly. Only submitted filters
apply to pagination; editing a field requires Apply filters. Applied filters,
sort and pagination are retained in the URL and the detail/back links.

## Asset detail and history limits

All new detail paths require `tenant_id`; another client's asset returns 404.
The detail includes identities, current OS/tags/criticality/location, first/last
observation, associated findings with their retained snapshot environments,
recorded environment moves and referenced imports. History lists have separate
bounded pagination. Finding summaries show rule, kind, severity, status, scanner,
port/protocol and dates, without loading large raw evidence for every row.

`/api/assets/{asset_id}/imports` uses only `last_import_id` and
`closed_by_import_id` references, deduplicated by a scoped EXISTS query. It does
not reconstruct earlier observations. Its `coverage` value is
`latest_and_closure_references_only`, and the UI calls out the gap. Complete
observation links and import metadata remain #0020. Import storage paths are
not returned by these new endpoints.

Editing/moving assets, individual finding detail/decisions and filtered exports
remain separate increments. Existing legacy API routes have not been replaced;
this work is not completion of #0004 tenant/database hardening.

## Reference inspection and design review

The source/edition/license record in [shell design](portal-shell-design.md)
applies. For this increment, the inspected Faraday OSS revision
`2ccc12a2b6309c87bf5f83f5b11c64ec1b8c1c06`,
[`hosts_base.py`](https://github.com/infobyte/faraday/blob/2ccc12a2b6309c87bf5f83f5b11c64ec1b8c1c06/faraday/server/api/modules/hosts_base.py),
was reviewed for HostSchema identities/OS/severity counts and HostView filtering,
pagination and sort order. DefectDojo OSS revision
`8b12d80ae30904fed44f5a84ff71f28da14bebaf`,
[`base.html`](https://github.com/DefectDojo/django-DefectDojo/blob/8b12d80ae30904fed44f5a84ff71f28da14bebaf/dojo/templates/base.html),
was reviewed for the scoped content area and search/label patterns. The official
[Faraday list screenshot](https://docs.faradaysec.com/images/status_report/status_report-v4.png)
provided the dense-table reference; illustrated commercial/integration behavior
is not assumed available in OSS or in VCM. No upstream code or artwork was copied.

Synthetic previews were visually reviewed at 1440px and 390px before broader
finding workflow work. They include deliberately literal HTML-like text used to
verify safe rendering; no customer data is included.

- [Inventory desktop](previews/0013-assets-desktop.png)
- [Inventory mobile](previews/0013-assets-mobile.png)
- [Asset detail desktop](previews/0013-asset-detail.png)
- [Asset detail mobile](previews/0013-asset-detail-mobile.png)

## Verification

- Standard suite: 24 passed, 9 opt-in PostgreSQL cases skipped.
- With the development PostgreSQL URL: 33 passed, including four new inventory
  cases for two tenants, moved assets, blank/distribution OS, tag/search filters,
  stable pages, inconsistent existing asset/environment pairs and proven import
  references after reimport. Fixture transactions rolled back.
- All four mocked Chromium browser suites passed. Inventory regressions cover
  URL pagination, unapplied filter edits, detail/back focus, literal external
  text, snapshots, empty/error/retry, late responses, mobile tables and a rejected
  detail scope. `assets.live.browser.cjs` supports read-only checks against an
  explicitly selected populated fixture client via `VCM_TEST_TENANT_ID`.
- Compose API/worker rebuilt. Nginx restarted for known #0025 upstream recovery.
  Two temporary clients received Nessus/Qualys uploads; imports completed and
  scoped inventory/findings/dashboard/reports were checked on the real stack.
  HTTP checks rejected missing scope, invalid pagination/sorts and cross-client
  environment/detail requests. Live Chromium checked inventory, Windows filtering,
  finding/import details and mobile/back navigation. Temporary client records
  were removed; uploaded fixtures remained only in Docker storage.

Publication is tracked with the issue and active portal checklist.
