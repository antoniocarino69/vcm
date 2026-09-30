# Shared portal shell — first increment (#0019)

Reviewed and verified on 2026-09-30. This increment covers the existing Overview
and Clients & environments pages. Asset/finding list and detail pages remain
separate increments; there are no placeholder navigation destinations.

## Reference inspection and provenance

| Reference | Revision / edition | Inspected material | Decision |
|---|---|---|---|
| DefectDojo | OSS, `8b12d80ae30904fed44f5a84ff71f28da14bebaf` | [`dojo/templates/base.html`](https://github.com/DefectDojo/django-DefectDojo/blob/8b12d80ae30904fed44f5a84ff71f28da14bebaf/dojo/templates/base.html), especially sidebar navigation and content offset | Persistent desktop sidebar, current-page indication and separate content context. VCM keeps its asset-centric hierarchy and native static frontend. |
| Faraday | OSS server, `2ccc12a2b6309c87bf5f83f5b11c64ec1b8c1c06` | [`hosts_base.py`](https://github.com/infobyte/faraday/blob/2ccc12a2b6309c87bf5f83f5b11c64ec1b8c1c06/faraday/server/api/modules/hosts_base.py) and [`hosts_workspaced.py`](https://github.com/infobyte/faraday/blob/2ccc12a2b6309c87bf5f83f5b11c64ec1b8c1c06/faraday/server/api/modules/hosts_workspaced.py) | Scope belongs to the query, not only a visual heading. Preserve client/environment in URL navigation. |
| Faraday documentation | Official live documentation inspected 2026-09-30; screenshot has no source commit | [Vulnerability management](https://docs.faradaysec.com/Vulns/) and [list screenshot](https://docs.faradaysec.com/images/status_report/status_report-v4.png) | Compact aligned tables, search above results, severity and asset context. The screenshot contains integration/owner features; it is not evidence that every illustrated feature exists in OSS. |

DefectDojo's inspected source uses the BSD 3-Clause terms in
[`LICENSE.md`](https://github.com/DefectDojo/django-DefectDojo/blob/8b12d80ae30904fed44f5a84ff71f28da14bebaf/LICENSE.md).
Faraday's repository uses [GPL v3](https://github.com/infobyte/faraday/blob/2ccc12a2b6309c87bf5f83f5b11c64ec1b8c1c06/LICENSE).
VCM uses interaction ideas; no upstream implementation, screenshot or icon was
copied into the application. Its shell CSS/JavaScript was written for VCM.
Chart.js 4.4.8 is the official UMD distribution served locally under MIT;
its license is retained in `frontend/vendor/Chart.js-LICENSE.md`.

## Layout and behavior

The 224px desktop sidebar contains operational links with an active-page marker.
The top bar names the active client and environment, or explicitly names the
all-client summary. Below 751px, a Menu button toggles the sidebar; the scope
remains visible, Escape closes navigation and returns focus to the button.
A skip link provides keyboard access to content. Tables retain aligned columns;
summary metrics are compact and charts have a bounded height.

Overview validates an environment URL against the selected client's environment
list before loading data or enabling exports. A client change resets environment
selection. Dashboard, imports and report links share the selected environment.
Navigation between existing pages preserves validated scope through query
parameters; late responses cannot replace the newly selected client's content.
Failure to load environments leaves scoped exports disabled and shows an error.

## Reviewable previews and checks

The following Chromium captures use synthetic example data only. They show the
current layout for review before extending the shell to asset/finding workflows.
Desktop and mobile captures were visually inspected. Error, empty and loading
states are exercised by browser tests; the existing client page table/form also
passes its narrow-screen workflow.

- [Desktop preview](previews/0019-desktop.png)
- [Mobile preview](previews/0019-mobile.png)

Verification:

- Backend suite: 24 passed, 5 optional PostgreSQL cases skipped.
- `frontend/tests/shell.browser.cjs`: navigation, environment validation,
  dashboard/report query scope, pending-client responses, API error state,
  mobile menu, Escape/focus and no external runtime requests.
- Existing client and dashboard browser regressions passed.
- Real stack rebuilt; nginx restarted after stale upstream resolution (#0025).
- Real Nessus and Qualys fixture uploads for two temporary clients completed;
  findings/dashboard/report isolation checks passed. Chromium verified live
  environment totals, Executive/Technical HTML and CSV requests, cross-page
  scope, local charts and mobile navigation without JavaScript errors.
  Temporary fixture client data was removed; files remained in Docker storage.

The asset/finding layout review, their list/detail return state and broader
navigation remain open under #0019/#0013/#0014. Authentication stays deferred.
