# Operational portal — next steps and acceptance checklist

Updated: 2026-09-30. This is the active checklist for the latest product request.
Use [implementation status](implementation-status.md) for delivered behavior
and [the original review](review-piano-portale.md) for technical findings.
This document refines the earlier plan; it does not mark missing features ready.

## How to maintain this document

Check an implementation box only after the increment has been implemented and verified.
Publication is tracked separately and is required before session handoff is complete.
Add the commit/PR and verification evidence beside the checked item. If only
part of an issue is delivered, check that part and leave the issue open for
the remainder. Ship complete workflows in small increments. Authentication
remains deferred until explicitly requested. Keep the portal on `0.0.0.0:8080`.

## Already delivered

- [x] Client creation and selection, environment creation with type/match key —
  `22ac0e6`; real browser creation/refresh and mobile verification.
- [x] Tenant/environment scope for dashboard host and AD data — `2c090cb`;
  PostgreSQL regressions and two-tenant upload/report end-to-end verification.
- [x] Dashboard safe text rendering and coherent client/import selection —
  `3da2698`; browser regressions, including delayed responses.
- [x] English dashboard/report labels — `0a6daa8`; live report verification.
- [x] Scanner/asset/rule/port deduplication and mitigation reopening exist;
  preserve manual false-positive/risk decisions on reimport — `30b2d07`;
  backend regression coverage. Deduplication is per environment and does not
  merge different servers or different scanners solely because they share a CVE.

The checkbox evidence above records completed revisions, now published to GitHub
with their original commit hashes.

- [x] Publish completed work and verify the remote branch hash — #0024;
  SSH authentication succeeded and all six completed working branches were pushed.

Remote `origin` is configured as `git@github.com:antoniocarino69/vcm.git`.
Its initial `main` contained only LICENSE with an independent history; that
commit was merged into the local working branch without changing remote main.
HTTPS CLI push initially failed due to missing HTTPS credentials; the GitHub
integration also rejected Git tree creation with HTTP 403. The existing local
SSH key was already authorized, so switching origin to SSH resolved publication
without rewriting history. Never paste private keys/tokens into chat, repository
files or command output.

## A. Shared sidebar and interface redesign — #0019

- [ ] Inspect Faraday and DefectDojo navigation, list/detail and filter patterns;
  record specific source files/screenshots, revision, edition and design choices.
- [ ] Prepare a reviewable layout for desktop and narrow screens, using realistic
  asset/finding tables and empty/error states. Review it before implementing
  the broader redesign; avoid building every page at once.
- [x] Implement a shared application shell and sidebar for the existing pages —
  `c4346e0`, published on `feature/0019-shared-portal-shell`; all three Chromium
  regressions and live API navigation passed. [Design and previews](portal-shell-design.md).
- [x] Keep the active client and environment visible throughout existing-page navigation.
  Allow all environments of one client; make an all-client summary explicit —
  `c4346e0`; validated environment URLs, pending-client responses and scoped
  dashboard/import/report requests verified in Chromium and on the real stack.
- [ ] Provide consistent breadcrumbs, page titles, row actions and keyboard access;
  collapse the sidebar on mobile without hiding the active scope.
- [ ] Preserve the selected scope, filters and list position when opening an
  asset/finding and returning to its list.
- [ ] Verify the real browser workflow at desktop/mobile sizes and publish the
  completed increment. Refactoring, new features and unrelated fixes use
  separate commits/PRs.

Target navigation, implemented as each section becomes functional:

| Sidebar section | Purpose |
|---|---|
| Overview | Scoped operational summary and drill-downs |
| Clients | Create, select, edit and eventually archive clients |
| Environments | Manage infrastructure boundaries within the selected client |
| Assets | Inventory, operating systems, tags and asset details |
| Vulnerabilities | Individual asset-associated findings, filters and triage |
| Compliance | STIG/SCC results and AD posture, retaining normalized finding data |
| Scan imports | Upload, dates/tags, progress, errors and import history |
| VA campaigns | Assessment objectives, targets and associated scan imports |
| Remediation campaigns | Action plans, finding selection, ownership and progress |
| Reports | Export results for the selected scope and filters |
| Settings | Actual supported options and tag/filter preferences |

Use a compact, practical interface for system administrators: readable dense
tables, stable column alignment, precise severity/status badges, restrained
colors and direct actions. Establish VCM typography, spacing, icons and table
patterns. Replace the repeated generic card grid and oversized KPI panels with
layouts appropriate to each task. Do not fill the sidebar with dead links or
present empty placeholder pages as completed features. Keep runtime assets
available locally for air-gapped use.

First shell increment: `c4346e0` is published. Reference source/edition/license
notes and desktop/mobile previews are in [the design record](portal-shell-design.md).
Asset/finding list/detail design, row actions and return-position state remain
unverified and open; the broader redesign is not complete.

## B. Client/environment scope and management — #0004, #0009, #0011 P1b

- [ ] Harden API scope for every list, detail, comment, status change and bulk action;
  validate that environment, asset, import and finding belong to the selected client.
- [ ] Add tenant consistency migrations and regression tests with two clients,
  including child history/comments and existing populated volumes.
- [ ] Support partial edits for client/environment metadata without resetting
  omitted fields. Handle duplicates/invalid values as meaningful 4xx responses.
- [ ] Complete client/environment editing in the portal. Define client archiving
  behavior before exposing it; preserve historical imports, findings and comments.
- [ ] Test context switching while requests are pending; never apply a late
  response or an action to the newly selected client by mistake.

## C. Assets and individual vulnerabilities — #0013, #0014

- [ ] Implement an asset inventory with pagination/sorting and columns for
  IP, FQDN/NetBIOS, **operating system**, environment, criticality, tags,
  last observation and open finding counts.
- [ ] Implement an asset detail page with identities, OS, tags, current environment,
  historical environment snapshots/moves, imports and associated findings.
- [ ] Implement a vulnerability list where each row identifies one finding on
  one asset, with client/environment, asset, OS, rule/CVE, severity, status,
  tags, scanner, port and first/last observation.
- [ ] Implement the individual finding page: asset context, rule, original/normalized
  severity, CVSS/CVEs, description, solution, scanner evidence, observation dates,
  provenance, comments, tags and status history.
- [ ] Support Open, Mitigated, False positive and Risk accepted through the existing
  status values; collect a reason and optional acceptance expiry as appropriate.
- [ ] Verify that accepting rule X on server A leaves rule X on server B unchanged.
  Also verify that changing one port-specific finding does not change another.
- [ ] Add safe bulk actions in a separate increment: explicit selected finding IDs,
  tenant checks for every ID, bounded batches and a visible outcome summary.

**Unit of decision:** an existing finding ID, tied to its asset and scanner/rule/port
identity in the environment snapshot. A CVE/rule summary can group rows for
navigation, but never becomes a global risk-acceptance switch. If the user
accepts a risk on one server, the other servers stay independently actionable.
Keep mitigated, accepted and false-positive results distinguishable in progress
and reports. Risk acceptance expiry automation remains a separate future milestone.

AD tools can describe a domain or identity object rather than a server. Preserve
that target and its affected objects; do not invent host identities or OS values
from an aggregate AD score. Add a target-type distinction where evidence warrants it.

## D. Scan upload, optional dating and tagging — #0012, #0020

- [ ] Complete upload prerequisites: streaming size/hash handling, scanner aliases,
  meaningful errors, reliable dispatch/retries and corrected AD/compliance paths
  (#0005–#0007). Keep auto-close opt-in.
- [ ] Define and migrate dedicated import metadata; align schema.sql and ORM.
  Date and tags do **not** currently exist as dedicated scan-import fields.
- [ ] Show a pre-upload form with client, environment, scanner/auto-detection, file,
  **optional assessment date/time**, **optional arbitrary tags**, optional VA campaign
  and auto-close choice. Campaign selection arrives after #0022 is functional.
- [ ] Allow creation of user-chosen labels before submission; suggest existing tags
  within the client, without requiring a predefined list or silently changing labels.
- [ ] Show upload/import progress, completion statistics, errors and a link to the
  resulting filtered assets/findings. Preserve entered metadata after recoverable errors.
- [ ] Persist and display the original filename, scanner, assessment date/source,
  upload timestamp, tags and campaign association in import history/detail.
- [ ] Verify dated/undated and tagged/untagged uploads using all supported scanner
  fixtures. Validate timezone handling and multi-target reports explicitly.

### Date semantics to implement

Upload time is ingestion provenance; assessment time is when the infrastructure
was checked. Keep both. Proposed precedence: explicit operator date/time →
scanner observation timestamp when reliably available → upload timestamp with
a visible fallback indicator. Preserve the scanner timestamp, operator override,
chosen source and original timezone/precision. A date without a time stays a
date-level observation; do not silently pretend the scanner ran at an exact hour.

Support historical imports. Test an older scan uploaded after a newer one:
it may enrich history but must not regress latest observations, overwrite newer
evidence or reopen/auto-close current findings based on stale data. Define
chronological update/auto-close rules before enabling dated lifecycle updates;
dedup_hash and existing status enums remain unchanged.

### Tags and evidence to implement

Keep manual finding labels, asset/environment labels and scan-import labels
distinct, with their source visible. Suggested UX: free-form label chips such
as `patch-window-october`, `internet-facing`, `customer-review`; existing
asset/environment key-value tags remain valid and separately identifiable.
The exact new storage contract is a proposal requiring a migration, not an
existing API field.

Add a tenant-scoped association between each successfully imported observation
and its deduplicated finding. `last_import_id` alone cannot answer whether a
finding appeared in an earlier tagged or dated scan. Use explicit observation
links so scan tags remain searchable after reimports, without duplicating findings
or overwriting manual labels. Backfill only what existing data can prove;
label historical coverage gaps instead of reconstructing imaginary observations.
Ensure failed/cancelled imports and retries cannot create misleading associations.

## E. Filters, especially operating system and tags — #0021

- [ ] Add server-side OS filters to asset and vulnerability lists. Join findings
  to the correct asset under explicit tenant scope; paginate **after** filtering.
- [ ] Provide OS value search and common family choices such as Windows/Linux,
  including **Unknown**; preserve exact scanner/asset OS text and make normalization
  rules explicit. Missing OS must remain searchable, not guessed.
- [ ] Provide filters for client, environment, asset/IP/FQDN, OS, status, severity,
  scanner, finding kind, CVE/rule ID, port/protocol, STIG category/result,
  text search, first/last observation, scan date/import and campaigns.
- [ ] Provide tag filtering with an explicit source: Finding, Asset/Environment,
  Scan import, or Any source. Support multiple user-selected tags.
- [ ] Define filter combination: AND across fields/tags; OR among selected values
  of one enum field. For multiple scan tags, match one relevant imported observation
  carrying all selected scan tags, rather than combining unrelated scans silently.
- [ ] Display active filter chips and a clear/reset action; persist filters in the
  URL and support scoped saved filters in a later, separately verified increment.
- [ ] Keep counts, table rows and exports consistent with the same filters. Use
  EXISTS/scoped joins for observation tags to avoid multiplying finding rows.
- [ ] Test two servers sharing a rule with different OS/tags, repeated imports with
  different labels, missing OS, an older tagged import, and overlapping client tags.

The OS column defaults to the asset's current known OS. Historical OS filtering
is a separate explicit mode if observation snapshots are stored; do not present
the current OS as proof of the OS at the time of an old assessment.

## F. VA and remediation campaigns — #0022, #0015

- [ ] Design VA campaigns as optional assessment coordination: objective, client,
  target environments/assets, planned/actual dates, owner and associated imports.
- [ ] Implement VA campaign schema/migration, scoped API and a complete create/list/
  detail GUI increment. A scan can be uploaded without a campaign.
- [ ] Keep campaigns as optional associations; do not introduce mandatory
  Engagement/Test containers or move finding ownership away from assets.
- [ ] Implement remediation campaign creation and explicit finding selection,
  ownership, deadlines and progress computed from the individual finding states.
- [ ] Link assessment results to remediation plans without changing finding identity.
  Completing a campaign must not automatically accept or mitigate every member.
- [ ] Verify campaigns across environments of one client, rejecting cross-client
  membership. Define progress for reopenings and historical observations.

## G. Scanner exports, templates and compatibility evidence — #0023

- [ ] Capture the exact supported export type/version for each scanner and store
  source/provenance notes with sanitized fixtures.
- [ ] Compare parser assumptions with official schemas/exports and reference
  parsers; distinguish scan-result exports from human-readable report templates.
- [ ] Add missing variant, date, OS, tags and target-identity fixtures before
  claiming support for an entire scanner product/version.
- [ ] Validate domain-level versus host-level data, multi-target XCCDF and empty
  hosts. Confirm true streaming memory behavior on large synthetic reports.
- [ ] Document unsupported variants clearly. Do not infer that a vendor PDF, XML
  benchmark definition or dashboard screenshot is a parseable scan-result report.

Research performed for this plan (2026-09-30):

| Tool | Official/reference material | Evidence and next validation |
|---|---|---|
| Qualys VMDR | [Scan results and report templates](https://docs.qualys.com/en/vm/10.32.1.0/scans/win_scan_results.htm), [XML/DTD reference](https://cdn2.qualys.com/docs/version/10.21/qualys-api-vmpc-xml-dtd-reference.pdf) | Documentation distinguishes saved scan results and current host data and describes host OS. The XML reference is versioned and older; validate the actual chosen export/version against VCM fixtures. |
| Nessus | [Export formats with XML examples](https://developer.tenable.com/docs/export-file-formats), [Nessus scan report formats](https://docs.tenable.com/nessus/10_5/Content/ScanReportFormats.htm) | Use native `.nessus` XML and host-property samples as compatibility inputs; documentation versions must be recorded. Validate actual Nessus scan dates and OS fields; PDF is a presentation export. |
| PingCastle | [Report documentation/examples](https://www.pingcastle.com/documentation/), [HealthcheckData source](https://github.com/netwrix/pingcastle/blob/a14f2de5fa77f0d83d08009f8732a1130c03a1ca/PingCastleCommon/Data/HealthcheckData.cs) | Official documentation offers report examples; inspected source includes GenerationDate and domain report naming. The local excerpt is not proof of compatibility with every current release. Test domain identity and authentic XML structure. |
| Purple Knight | [Semperis report example and HTML/PDF description](https://www.semperis.com/blog/purple-knight-azure-security-indicators/) | This is an older report illustration, not a current machine-readable export schema. The dedicated documentation site was inaccessible during research. The local CSV fixture matches VCM assumptions but its official export provenance remains unverified; obtain/version a sanitized real export before broad compatibility claims. |
| DISA SCC / XCCDF | [DISA tools](https://www.cyber.mil/stigs/srg-stig-tools), [DISA download library](https://www.cyber.mil/stigs/downloads), [NIST XCCDF schemas/examples](https://csrc.nist.gov/Projects/security-content-automation-protocol/Specifications/xccdf) | NIST provides schemas and benchmark examples; benchmarks are not result reports. Obtain sanitized SCC-generated TestResult/ARF examples, including target identities, result timestamps and multiple targets. |

No customer reports or copied vendor bundles were added to this repository.
Research sources are references, not a claim that every template was downloaded
or imported successfully.

## Reference implementation inspection

Faraday's documented vulnerability view uses left-menu navigation, asset-related
findings and tag/search filters. These are useful workflow references, not a
requirement to reproduce its workspace model or every commercial feature.
[Faraday vulnerability management](https://docs.faradaysec.com/Vulns/)

Specific code inspected:

- Faraday revision `2ccc12a2b6309c87bf5f83f5b11c64ec1b8c1c06`:
  [host filters](https://github.com/infobyte/faraday/blob/2ccc12a2b6309c87bf5f83f5b11c64ec1b8c1c06/faraday/server/api/modules/hosts_base.py),
  [workspace host endpoints](https://github.com/infobyte/faraday/blob/2ccc12a2b6309c87bf5f83f5b11c64ec1b8c1c06/faraday/server/api/modules/hosts_workspaced.py),
  [saved search filters](https://github.com/infobyte/faraday/blob/2ccc12a2b6309c87bf5f83f5b11c64ec1b8c1c06/faraday/server/api/modules/search_filter.py).
- DefectDojo revision `8b12d80ae30904fed44f5a84ff71f28da14bebaf`:
  [sidebar/application template](https://github.com/DefectDojo/django-DefectDojo/blob/8b12d80ae30904fed44f5a84ff71f28da14bebaf/dojo/templates/base.html),
  [Qualys parser](https://github.com/DefectDojo/django-DefectDojo/blob/8b12d80ae30904fed44f5a84ff71f28da14bebaf/dojo/tools/qualys/parser.py),
  [PingCastle parser](https://github.com/DefectDojo/django-DefectDojo/blob/8b12d80ae30904fed44f5a84ff71f28da14bebaf/dojo/tools/pingcastle/parser.py).

Reuse the useful interaction and parsing ideas with recorded provenance. Keep
VCM parsers stdlib-only, pure and streaming; an upstream parser's dependencies
or full-tree loading are not automatically suitable for this project.

## Execution order and session handoff

1. Sidebar/design increment (#0019), while independently closing prerequisite
   scope/validation issues before exposing new mutations.
2. Scoped asset inventory and individual finding workflow (#0013/#0014),
   including current-OS filtering (#0021 first increment).
3. Import metadata/observation contract (#0020) and verified scanner compatibility
   (#0023); upload workflow (#0012), with optional date and tags.
4. Complete tag/date filters and filtered exports (#0021).
5. VA campaigns (#0022), then remediation campaigns (#0015), each with schema,
   API and GUI verified in small complete increments.

At the end of each completed feature/session: update checkboxes and issues,
run the required checks, commit and push the active branch, and verify the
remote branch hash. Record any failed push explicitly. Do not force-push or
replace remote history to resolve divergence. Merge through the repository's
PR/review workflow; keep main green.
