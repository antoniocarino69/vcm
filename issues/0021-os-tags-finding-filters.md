# 0021 — OS and tag filters for assets and individual findings

## Context
The user needs per-client/environment vulnerability management with operating-system and arbitrary-tag filters inspired by Faraday. Current finding endpoint lacks OS/tag filters.

## Expected behavior
Implement server-side filtering before pagination, Unknown OS, explicit tag provenance/combination, usual severity/status/scanner/CVE/rule/port/date filters, active chips and consistent exports. Test cross-tenant isolation and repeated tagged imports without duplicate rows.

## Acceptance checklist
See the corresponding section in `docs/portal-next-steps.md`.
Update each completed increment with its commit/PR, real verification and push.

## Status
- Open

## First asset-filter increment — 2026-09-30

- Current asset OS substring, explicit Windows/Linux marker families, Unknown,
  identity search and AND-combined asset key/key:value tags implemented before
  pagination. Filters/chips/sort/page persist in inventory/detail/back URLs.
- PostgreSQL tests cover differing/missing OS, literal wildcards, overlapping
  client tags, moved assets and filtering before pages. Live Nessus Ubuntu and
  Windows records verified. See `docs/asset-inventory.md`.
- Implementation published as `790c70b` on `feature/0013-scoped-asset-inventory`; remote branch hash verified.
- Finding OS/tag filters, other tag sources, observations/date/campaign filtering
  and matching exports remain open; the complete issue is not delivered.
