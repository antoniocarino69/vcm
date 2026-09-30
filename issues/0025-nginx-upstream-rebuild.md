# 0025 — Nginx retains an API address after container recreation

## Context
During #0019 verification, rebuilding/recreating API and worker left the running
nginx container forwarding requests to the previous API IP address. Static pages
loaded, but API requests returned 502 with connection refused.

## Reproduction
Run the documented compose build/up command while nginx remains running and the
API container receives a new address. Request `/api/health` through port 8080.

## Expected behavior
The documented rebuild workflow restores working API proxying even when Docker
changes the upstream container address. Add a regression before changing deployment.

## Status
- Open. Operational recovery verified with `docker compose restart frontend`.
- Deployment configuration was not changed in the sidebar increment.
