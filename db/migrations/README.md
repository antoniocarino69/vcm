# Database migrations

`db/schema.sql` is the source of truth (baseline 0001): fresh PostgreSQL
volumes apply it automatically through `/docker-entrypoint-initdb.d`. It is
kept 1:1 with `backend/app/models.py`.

Already populated volumes cannot see schema.sql changes, so each schema change
after the baseline ships as a numbered, idempotent SQL migration here and is
applied explicitly:

```sh
docker compose exec -T postgres psql -U vcm -d vcm -1 -f - \
  < db/migrations/0002_tenant_consistency.sql
```

`-1` wraps the file in a single transaction (the files contain no transaction
control so they can also run inside test transactions). Applied versions are
recorded in `schema_migrations`; re-running a migration is safe by design.

Registrazione esiti: ogni migrazione va verificata sia su database già
popolato (backfill + catalogo) sia su un database nuovo da schema.sql
(`backend/tests/test_migrations_postgres.py` + verifica catalogo in fase di
rilascio). Richiede PostgreSQL 15+ quando usa `ON DELETE SET NULL (colonna)`.
