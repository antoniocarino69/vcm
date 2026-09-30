-- 0002: explicit tenant consistency for child tables (issue #0004).
--
-- Fresh installs already get these constraints from db/schema.sql (baseline
-- 0001). This migration upgrades populated volumes created before them:
-- * child history tables (asset_moves, finding_status_history, finding_comments)
--   gain an explicit tenant_id, backfilled from their owning parent row;
-- * single-column foreign keys are replaced by composite (id, tenant_id) keys,
--   so no statement can mix two clients even with valid parent rows.
--
-- Idempotent: safe to re-run. Apply atomically, e.g.:
--   docker compose exec -T postgres psql -U vcm -d vcm -1 -f - \
--     < db/migrations/0002_tenant_consistency.sql
-- Requires PostgreSQL 15+ (ON DELETE SET NULL with a column list).

CREATE TABLE IF NOT EXISTS schema_migrations (
    version    integer PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

-- Unique helpers required as composite foreign key targets.
CREATE UNIQUE INDEX IF NOT EXISTS environments_id_tenant_uidx ON environments (id, tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS assets_id_tenant_uidx ON assets (id, tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS scan_imports_id_tenant_uidx ON scan_imports (id, tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS findings_id_tenant_uidx ON findings (id, tenant_id);

-- Child history tables carry their own tenant_id, backfilled from the parent.
ALTER TABLE asset_moves ADD COLUMN IF NOT EXISTS tenant_id uuid;
ALTER TABLE finding_status_history ADD COLUMN IF NOT EXISTS tenant_id uuid;
ALTER TABLE finding_comments ADD COLUMN IF NOT EXISTS tenant_id uuid;

UPDATE asset_moves am SET tenant_id = a.tenant_id FROM assets a
 WHERE am.asset_id = a.id AND am.tenant_id IS NULL;
UPDATE finding_status_history h SET tenant_id = f.tenant_id FROM findings f
 WHERE h.finding_id = f.id AND h.tenant_id IS NULL;
UPDATE finding_comments c SET tenant_id = f.tenant_id FROM findings f
 WHERE c.finding_id = f.id AND c.tenant_id IS NULL;

ALTER TABLE asset_moves ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE finding_status_history ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE finding_comments ALTER COLUMN tenant_id SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'asset_moves_tenant_fkey') THEN
        ALTER TABLE asset_moves ADD CONSTRAINT asset_moves_tenant_fkey
            FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'asset_moves_asset_tenant_fkey') THEN
        ALTER TABLE asset_moves DROP CONSTRAINT IF EXISTS asset_moves_asset_id_fkey;
        ALTER TABLE asset_moves ADD CONSTRAINT asset_moves_asset_tenant_fkey
            FOREIGN KEY (asset_id, tenant_id) REFERENCES assets (id, tenant_id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'asset_moves_from_environment_tenant_fkey') THEN
        ALTER TABLE asset_moves DROP CONSTRAINT IF EXISTS asset_moves_from_environment_id_fkey;
        ALTER TABLE asset_moves ADD CONSTRAINT asset_moves_from_environment_tenant_fkey
            FOREIGN KEY (from_environment_id, tenant_id) REFERENCES environments (id, tenant_id)
            ON DELETE SET NULL (from_environment_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'asset_moves_to_environment_tenant_fkey') THEN
        ALTER TABLE asset_moves DROP CONSTRAINT IF EXISTS asset_moves_to_environment_id_fkey;
        ALTER TABLE asset_moves ADD CONSTRAINT asset_moves_to_environment_tenant_fkey
            FOREIGN KEY (to_environment_id, tenant_id) REFERENCES environments (id, tenant_id)
            ON DELETE RESTRICT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'finding_status_history_tenant_fkey') THEN
        ALTER TABLE finding_status_history ADD CONSTRAINT finding_status_history_tenant_fkey
            FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'finding_status_history_finding_tenant_fkey') THEN
        ALTER TABLE finding_status_history DROP CONSTRAINT IF EXISTS finding_status_history_finding_id_fkey;
        ALTER TABLE finding_status_history ADD CONSTRAINT finding_status_history_finding_tenant_fkey
            FOREIGN KEY (finding_id, tenant_id) REFERENCES findings (id, tenant_id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'finding_status_history_import_tenant_fkey') THEN
        ALTER TABLE finding_status_history DROP CONSTRAINT IF EXISTS finding_status_history_import_id_fkey;
        ALTER TABLE finding_status_history ADD CONSTRAINT finding_status_history_import_tenant_fkey
            FOREIGN KEY (import_id, tenant_id) REFERENCES scan_imports (id, tenant_id)
            ON DELETE SET NULL (import_id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'finding_comments_tenant_fkey') THEN
        ALTER TABLE finding_comments ADD CONSTRAINT finding_comments_tenant_fkey
            FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'finding_comments_finding_tenant_fkey') THEN
        ALTER TABLE finding_comments DROP CONSTRAINT IF EXISTS finding_comments_finding_id_fkey;
        ALTER TABLE finding_comments ADD CONSTRAINT finding_comments_finding_tenant_fkey
            FOREIGN KEY (finding_id, tenant_id) REFERENCES findings (id, tenant_id) ON DELETE CASCADE;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'findings_asset_tenant_fkey') THEN
        ALTER TABLE findings DROP CONSTRAINT IF EXISTS findings_asset_id_fkey;
        ALTER TABLE findings ADD CONSTRAINT findings_asset_tenant_fkey
            FOREIGN KEY (asset_id, tenant_id) REFERENCES assets (id, tenant_id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'findings_environment_tenant_fkey') THEN
        ALTER TABLE findings DROP CONSTRAINT IF EXISTS findings_environment_id_fkey;
        ALTER TABLE findings ADD CONSTRAINT findings_environment_tenant_fkey
            FOREIGN KEY (environment_id, tenant_id) REFERENCES environments (id, tenant_id)
            ON DELETE RESTRICT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'findings_last_import_tenant_fkey') THEN
        ALTER TABLE findings DROP CONSTRAINT IF EXISTS findings_last_import_id_fkey;
        ALTER TABLE findings ADD CONSTRAINT findings_last_import_tenant_fkey
            FOREIGN KEY (last_import_id, tenant_id) REFERENCES scan_imports (id, tenant_id)
            ON DELETE SET NULL (last_import_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'findings_closed_by_import_tenant_fkey') THEN
        ALTER TABLE findings DROP CONSTRAINT IF EXISTS findings_closed_by_import_id_fkey;
        ALTER TABLE findings ADD CONSTRAINT findings_closed_by_import_tenant_fkey
            FOREIGN KEY (closed_by_import_id, tenant_id) REFERENCES scan_imports (id, tenant_id)
            ON DELETE SET NULL (closed_by_import_id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'scan_imports_environment_tenant_fkey') THEN
        ALTER TABLE scan_imports DROP CONSTRAINT IF EXISTS scan_imports_environment_id_fkey;
        ALTER TABLE scan_imports ADD CONSTRAINT scan_imports_environment_tenant_fkey
            FOREIGN KEY (environment_id, tenant_id) REFERENCES environments (id, tenant_id)
            ON DELETE RESTRICT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ad_health_environment_tenant_fkey') THEN
        ALTER TABLE ad_health_snapshots DROP CONSTRAINT IF EXISTS ad_health_snapshots_environment_id_fkey;
        ALTER TABLE ad_health_snapshots ADD CONSTRAINT ad_health_environment_tenant_fkey
            FOREIGN KEY (environment_id, tenant_id) REFERENCES environments (id, tenant_id)
            ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ad_health_asset_tenant_fkey') THEN
        ALTER TABLE ad_health_snapshots DROP CONSTRAINT IF EXISTS ad_health_snapshots_asset_id_fkey;
        ALTER TABLE ad_health_snapshots ADD CONSTRAINT ad_health_asset_tenant_fkey
            FOREIGN KEY (asset_id, tenant_id) REFERENCES assets (id, tenant_id)
            ON DELETE SET NULL (asset_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ad_health_import_tenant_fkey') THEN
        ALTER TABLE ad_health_snapshots DROP CONSTRAINT IF EXISTS ad_health_snapshots_import_id_fkey;
        ALTER TABLE ad_health_snapshots ADD CONSTRAINT ad_health_import_tenant_fkey
            FOREIGN KEY (import_id, tenant_id) REFERENCES scan_imports (id, tenant_id)
            ON DELETE SET NULL (import_id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'report_jobs_environment_tenant_fkey') THEN
        ALTER TABLE report_jobs DROP CONSTRAINT IF EXISTS report_jobs_environment_id_fkey;
        ALTER TABLE report_jobs ADD CONSTRAINT report_jobs_environment_tenant_fkey
            FOREIGN KEY (environment_id, tenant_id) REFERENCES environments (id, tenant_id)
            ON DELETE CASCADE;
    END IF;

    -- Align default baseline names with the explicit names used by schema.sql.
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'scan_imports_tenant_id_fkey') THEN
        ALTER TABLE scan_imports RENAME CONSTRAINT scan_imports_tenant_id_fkey TO scan_imports_tenant_fkey;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'findings_tenant_id_fkey') THEN
        ALTER TABLE findings RENAME CONSTRAINT findings_tenant_id_fkey TO findings_tenant_fkey;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ad_health_snapshots_tenant_id_fkey') THEN
        ALTER TABLE ad_health_snapshots RENAME CONSTRAINT ad_health_snapshots_tenant_id_fkey TO ad_health_snapshots_tenant_fkey;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'report_jobs_tenant_id_fkey') THEN
        ALTER TABLE report_jobs RENAME CONSTRAINT report_jobs_tenant_id_fkey TO report_jobs_tenant_fkey;
    END IF;
END $$;

INSERT INTO schema_migrations (version) VALUES (2)
ON CONFLICT (version) DO NOTHING;
