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
