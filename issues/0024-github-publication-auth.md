# 0024 — Publish completed branches after configuring GitHub authentication

## Context
The user authorized publishing to `https://github.com/antoniocarino69/vcm.git`.
Origin is configured and public fetch works. The original remote main commit
contains only LICENSE and has been merged into the local working branch.

## Reproduction
`git push -u origin docs/0018-operational-portal-checklist ...` fails with:
`fatal: could not read Username for 'https://github.com': No such device or address`.
The GitHub connector can read repository metadata but its Git tree creation
request fails with `403 Resource not accessible by integration`.

## Expected behavior
Configure an authorized HTTPS credential helper or SSH access on this machine.
Push completed branches, verify remote commit hashes and upstream tracking,
and update the publication checklist. Preserve remote main and existing history.
Do not store or log tokens/keys or ask for them in chat.

## Branches to publish
- docs/0018-operational-portal-checklist (contains the complete working tree/history)
- fix/0002-preserva-triage-import
- fix/0003-scope-dashboard
- feature/0011-client-environment-portal
- chore/0017-english-interface
- fix/0008-dashboard-rendering-context

## Status
- Closed
- Resolution: the existing SSH key was already authorized for antoniocarino69.
  Switched origin to SSH and successfully pushed all six listed branches,
  preserving original commit hashes and enabling upstream tracking.
- Closed by `docs(repo): record successful SSH publication`
