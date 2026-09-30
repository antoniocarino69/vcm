# 0019 — Shared sidebar and operational interface redesign

## Context
Replace the separate page layouts with a shared sidebar and stable client/environment context. Inspect Faraday/DefectDojo code and screenshots and establish VCM-specific table, filter and detail patterns.

## Expected behavior
Deliver and review a desktop/mobile design, then implement the shared shell for functional routes. Preserve scope and filters, keyboard navigation and English text; avoid generic repeated KPI/card layouts.

## Acceptance checklist
See the corresponding section in `docs/portal-next-steps.md`.
Update each completed increment with its commit/PR, real verification and push.

## Status
- Open

## First increment — 2026-09-30

- Shared sidebar/top bar for Overview and Clients & environments, validated
  client/environment URL navigation, environment-aware dashboard/import/report
  links, compact summary and local Chart.js runtime with MIT license.
- Design/source provenance and synthetic desktop/mobile previews:
  `docs/portal-shell-design.md`.
- Verification: backend 24 passed / 5 optional DB cases skipped; all three browser
  scripts passed; live two-client Nessus/Qualys ingest and scoped report/browser
  checks passed. Fixture data removed. Nginx recovery recorded separately (#0025).
- Branch: `feature/0019-shared-portal-shell`. Published implementation: `c4346e0`; remote branch hash verified.
- In progress: broader list/detail layouts and return state remain open.
