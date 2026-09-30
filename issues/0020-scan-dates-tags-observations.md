# 0020 — Optional scan dates, tags and observation provenance

## Context
scan_imports currently has no dedicated assessment date or tag fields. Findings retain only last_import_id; this cannot support filtering by earlier tagged imports.

## Expected behavior
Define schema/API/migrations for optional operator date/tags, scanner timestamp/source/precision and observation links. Historical uploads cannot regress current lifecycle. Preserve manual tags and dedup identity; test retries and metadata gaps.

## Acceptance checklist
See the corresponding section in `docs/portal-next-steps.md`.
Update each completed increment with its commit/PR, real verification and push.

## Status
- Open
