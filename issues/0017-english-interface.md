# 0017 — Use English throughout the portal and generated reports

## Context
The user requested English project/product text on 2026-09-30. Conversation
with the operator remains Italian. Existing dashboard and report labels are Italian.

## Expected behavior
Dashboard, client/environment portal and generated reports use English.
Existing finding status values and database contracts remain unchanged.
New documentation and comments use English; historical Italian documentation
is retained until a dedicated documentation translation increment.

## Verification
Load dashboard and HTML reports against the running stack and check visible labels.
Run the existing backend suite and browser checks.

## Status
- Closed
- Branch: chore/0017-english-interface
- Verification: backend suite passed; rebuilt stack; English dashboard and
  Executive/Technical HTML output checked against the running API.
- Closed by `chore(portal): use English dashboard and report labels`
