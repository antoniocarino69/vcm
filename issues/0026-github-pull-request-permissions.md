# 0026 — GitHub integration cannot create a pull request

## Context
The #0013 inventory branch was pushed successfully using the authorized SSH
connection. Creating a draft PR through the GitHub connector returned HTTP 403:
`Resource not accessible by integration` from the create-pull-request API.

## Reproduction
Use the GitHub connector's create_pull_request for `antoniocarino69/vcm` with
head `feature/0013-scoped-asset-inventory` and base `feature/0019-shared-portal-shell`.

## Expected behavior
The GitHub connection can open reviewable PRs, or a repository maintainer opens
the PR through the web UI. Publication of the branch is already complete.

## Status
- Open. No PR was created and no merge was performed.
- [Review the isolated increment](https://github.com/antoniocarino69/vcm/compare/feature%2F0019-shared-portal-shell...feature%2F0013-scoped-asset-inventory)
- The branch remains based on the published shell increment pending prior reviews.
