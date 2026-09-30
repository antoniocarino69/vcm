-- =============================================================================
-- VCM (Vulnerability & Compliance Management) - PostgreSQL schema
-- Multi-tenant, asset-centric, orientato a scanner di infrastruttura/AD/STIG.
-- Convenzioni: snake_case, timestamptz UTC, JSONB per payload grezzi scanner.
-- =============================================================================
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- -----------------------------------------------------------------------------
-- Enumerazioni condivise
-- -----------------------------------------------------------------------------
CREATE TYPE tenant_status       AS ENUM ('active', 'archived');
CREATE TYPE environment_kind    AS ENUM ('production', 'dmz', 'active_directory', 'staging', 'cloud', 'ot', 'other');
CREATE TYPE scanner_type        AS ENUM ('qualys_vmdr', 'tenable_nessus', 'scc_xccdf', 'pingcastle', 'purple_knight');
CREATE TYPE import_status       AS ENUM ('pending', 'parsing', 'completed', 'failed', 'cancelled');
CREATE TYPE finding_kind        AS ENUM ('vulnerability', 'compliance');
CREATE TYPE severity_level      AS ENUM ('critical', 'high', 'medium', 'low', 'info');
CREATE TYPE stig_category       AS ENUM ('CAT_I', 'CAT_II', 'CAT_III');
CREATE TYPE compliance_result   AS ENUM ('pass', 'fail', 'not_reviewed', 'not_applicable', 'error');
CREATE TYPE finding_status      AS ENUM ('active', 'mitigated', 'false_positive', 'risk_accepted');
CREATE TYPE asset_match_key     AS ENUM ('ip', 'fqdn', 'netbios');
CREATE TYPE membership_role     AS ENUM ('admin', 'analyst', 'viewer');
CREATE TYPE report_kind         AS ENUM ('executive', 'technical');
CREATE TYPE report_format       AS ENUM ('html', 'pdf', 'csv');
CREATE TYPE report_status       AS ENUM ('pending', 'rendering', 'ready', 'failed');

-- -----------------------------------------------------------------------------
-- 1. Multi-tenant: Clienti e Ambienti
-- -----------------------------------------------------------------------------
CREATE TABLE tenants (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug        text NOT NULL UNIQUE,
    name        text NOT NULL,
    description text,
    status      tenant_status NOT NULL DEFAULT 'active',
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE environments (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name        text NOT NULL,
    kind        environment_kind NOT NULL DEFAULT 'other',
    tags        jsonb NOT NULL DEFAULT '{}'::jsonb,   -- {"tier":"critical","location":"milano"}
    match_key   asset_match_key NOT NULL DEFAULT 'ip', -- chiave di riconciliazione asset
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, name)
);
CREATE INDEX environments_tags_idx ON environments USING gin (tags);

-- -----------------------------------------------------------------------------
-- 2. Asset & Host Management
-- -----------------------------------------------------------------------------
CREATE TABLE assets (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    environment_id uuid NOT NULL REFERENCES environments(id) ON DELETE RESTRICT,
    ip            inet,
    fqdn          text,
    hostname_netbios text,
    os            text,
    criticality   smallint NOT NULL DEFAULT 3 CHECK (criticality BETWEEN 1 AND 5),
    tags          jsonb NOT NULL DEFAULT '{}'::jsonb,
    first_seen    timestamptz NOT NULL DEFAULT now(),
    last_seen     timestamptz NOT NULL DEFAULT now(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT assets_has_identity CHECK (ip IS NOT NULL OR fqdn IS NOT NULL OR hostname_netbios IS NOT NULL)
);
-- Riconciliazione: gli indici unici parziali sono creati da app.services.assets
-- in base a environments.match_key; qui gli indici di lookup generici.
CREATE INDEX assets_tenant_env_idx  ON assets (tenant_id, environment_id);
CREATE INDEX assets_ip_idx          ON assets (tenant_id, ip);
CREATE INDEX assets_fqdn_idx        ON assets (tenant_id, lower(fqdn));
CREATE INDEX assets_netbios_idx     ON assets (tenant_id, lower(hostname_netbios));
CREATE INDEX assets_tags_idx        ON assets USING gin (tags);

-- Spostamenti asset tra ambienti: lo storico scansioni/commenti è preservato
-- perché findings/scan_imports conservano environment_id dello snapshot.
CREATE TABLE asset_moves (
    id                 bigserial PRIMARY KEY,
    asset_id           uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    from_environment_id uuid REFERENCES environments(id) ON DELETE SET NULL,
    to_environment_id   uuid NOT NULL REFERENCES environments(id) ON DELETE RESTRICT,
    moved_at           timestamptz NOT NULL DEFAULT now(),
    reason             text
);
CREATE INDEX asset_moves_asset_idx ON asset_moves (asset_id, moved_at DESC);

-- -----------------------------------------------------------------------------
-- 3. Importazioni (upload report scanner) + task asincroni di parsing
-- -----------------------------------------------------------------------------
CREATE TABLE scan_imports (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    environment_id uuid NOT NULL REFERENCES environments(id) ON DELETE RESTRICT,
    scanner        scanner_type NOT NULL,
    filename       text NOT NULL,
    content_sha256 char(64) NOT NULL,
    storage_path   text NOT NULL,
    status         import_status NOT NULL DEFAULT 'pending',
    -- Lifecycle: chiudi finding non più rilevati su questo asset/scanner
    auto_close     boolean NOT NULL DEFAULT false,
    stats          jsonb NOT NULL DEFAULT '{}'::jsonb,  -- {"hosts":120,"findings":3421,"new":..,"updated":..,"closed":..}
    error          text,
    started_at     timestamptz,
    finished_at    timestamptz,
    created_by     text,                                -- subject esterno (auth futuro)
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, content_sha256)
);
CREATE INDEX scan_imports_env_idx ON scan_imports (environment_id, created_at DESC);

-- -----------------------------------------------------------------------------
-- 4. Findings unificati: vulnerabilità (Qualys/Nessus) e compliance (SCC/STIG,
--    PingCastle, Purple Knight). I campi compliance sono NULL per kind='vuln'.
-- -----------------------------------------------------------------------------
CREATE TABLE findings (
    id             bigserial PRIMARY KEY,
    tenant_id      uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    asset_id       uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    environment_id uuid NOT NULL REFERENCES environments(id) ON DELETE RESTRICT, -- snapshot a frontiera import
    kind           finding_kind NOT NULL,

    scanner        scanner_type NOT NULL,
    rule_id        text NOT NULL,          -- QID / PluginID / Rule idref / RiskRule / Indicator
    rule_title     text NOT NULL,
    category       text,                   -- es. "Privileged Accounts", "Kerberos", plugin family
    severity       severity_level NOT NULL,
    severity_raw   text,                   -- "3", "Risk Factor: High", "CAT II", "Critical"
    stig_category  stig_category,          -- solo compliance STIG/SCC
    cvss_score     numeric(4,1),
    cvss_vector    text,
    cves           text[] NOT NULL DEFAULT '{}',
    port           integer CHECK (port BETWEEN 0 AND 65535),
    protocol       text,

    -- Compliance specific
    benchmark      text,                   -- es. "Microsoft Windows Server 2019 STIG"
    profile        text,                   -- es. "Level 2 - Domain Controller"
    result         compliance_result,      -- pass/fail/not_reviewed/...
    affected_objects jsonb NOT NULL DEFAULT '[]'::jsonb, -- Purple Knight / PingCastle

    description    text,                   -- Diagnosi / technical details
    solution       text,                   -- Remediation / recommendation
    scanner_output text,                   -- RESULTS / plugin output / finding details

    -- Lifecycle & deduplica
    dedup_hash     char(64) NOT NULL,      -- sha256(asset_id | rule_id | port)
    status         finding_status NOT NULL DEFAULT 'active',
    first_seen     timestamptz NOT NULL DEFAULT now(),
    last_seen      timestamptz NOT NULL DEFAULT now(),
    occurrence_count integer NOT NULL DEFAULT 1,
    last_import_id uuid REFERENCES scan_imports(id) ON DELETE SET NULL,
    closed_at      timestamptz,
    closed_by_import_id uuid REFERENCES scan_imports(id) ON DELETE SET NULL,
    status_reason  text,                   -- note su FP / risk accepted / mitigazione
    risk_accepted_until date,
    raw            jsonb NOT NULL DEFAULT '{}'::jsonb,  -- nodo XML/CSV originale

    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT findings_vuln_shape CHECK (
        (kind = 'vulnerability' AND result IS NULL)
        OR (kind = 'compliance'  AND result IS NOT NULL)
    ),
    CONSTRAINT findings_risk_acceptance CHECK (
        status <> 'risk_accepted' OR status_reason IS NOT NULL
    ),
    CONSTRAINT findings_open_iff_active CHECK (
        (status = 'active' AND closed_at IS NULL)
        OR (status <> 'active' AND closed_at IS NOT NULL)
    )
);

-- Deduplica: un finding identificativo per ambiente vive una sola volta.
CREATE UNIQUE INDEX findings_dedup_uidx   ON findings (environment_id, dedup_hash);
CREATE INDEX findings_asset_scanner_idx   ON findings (asset_id, scanner, status);
CREATE INDEX findings_severity_idx        ON findings (tenant_id, severity) WHERE status = 'active';
CREATE INDEX findings_cves_idx            ON findings USING gin (cves);
CREATE INDEX findings_last_seen_idx       ON findings (last_seen DESC);
CREATE INDEX findings_rule_idx            ON findings (scanner, rule_id);

-- Storico transizioni di stato (Active -> Mitigated / FP / Risk Accepted)
CREATE TABLE finding_status_history (
    id          bigserial PRIMARY KEY,
    finding_id  bigint NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    from_status finding_status,
    to_status   finding_status NOT NULL,
    reason      text,
    import_id   uuid REFERENCES scan_imports(id) ON DELETE SET NULL,
    changed_by  text,
    changed_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX finding_status_history_idx ON finding_status_history (finding_id, changed_at DESC);

CREATE TABLE finding_comments (
    id         bigserial PRIMARY KEY,
    finding_id bigint NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    author     text NOT NULL,
    body       text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- 5. AD Health Score (PingCastle global score / Purple Knight posture)
-- -----------------------------------------------------------------------------
CREATE TABLE ad_health_snapshots (
    id            bigserial PRIMARY KEY,
    tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    environment_id uuid NOT NULL REFERENCES environments(id) ON DELETE CASCADE,
    asset_id      uuid REFERENCES assets(id) ON DELETE SET NULL,  -- DC / dominio a cui si riferisce
    tool          scanner_type NOT NULL CHECK (tool IN ('pingcastle', 'purple_knight')),
    global_score  numeric(5,2),                 -- PingCastle: 0-100 (più alto = peggio)
    category_scores jsonb NOT NULL DEFAULT '{}'::jsonb, -- {"Privileged Accounts":45,"Trust":10,...}
    snapshot_at   timestamptz NOT NULL DEFAULT now(),
    import_id     uuid REFERENCES scan_imports(id) ON DELETE SET NULL,
    raw           jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX ad_health_idx ON ad_health_snapshots (environment_id, snapshot_at DESC);

-- -----------------------------------------------------------------------------
-- 6. Reporting
-- -----------------------------------------------------------------------------
CREATE TABLE report_jobs (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    environment_id uuid REFERENCES environments(id) ON DELETE CASCADE, -- NULL = tutti gli ambienti
    kind        report_kind NOT NULL,
    format      report_format NOT NULL DEFAULT 'html',
    status      report_status NOT NULL DEFAULT 'pending',
    options     jsonb NOT NULL DEFAULT '{}'::jsonb,  -- {"period_days":30,"include_closed":false}
    storage_path text,
    error       text,
    requested_by text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);

-- -----------------------------------------------------------------------------
-- 7. Viste analitiche per dashboard
-- -----------------------------------------------------------------------------
CREATE VIEW v_open_findings AS
SELECT f.*, a.ip, a.fqdn, a.hostname_netbios, e.name AS environment_name
FROM findings f
JOIN assets a ON a.id = f.asset_id
JOIN environments e ON e.id = f.environment_id
WHERE f.status = 'active';

CREATE VIEW v_severity_distribution AS
SELECT tenant_id, environment_id, kind, severity, count(*) AS total
FROM findings
WHERE status = 'active'
GROUP BY 1, 2, 3, 4;

CREATE VIEW v_top_vulnerable_hosts AS
SELECT tenant_id, asset_id, environment_id,
       count(*) AS open_findings,
       count(*) FILTER (WHERE severity IN ('critical','high')) AS open_critical_high,
       max(last_seen) AS last_seen
FROM findings
WHERE status = 'active'
GROUP BY 1, 2, 3
ORDER BY open_critical_high DESC, open_findings DESC;

CREATE VIEW v_top_widespread_rules AS
SELECT tenant_id, scanner, rule_id, rule_title, severity,
       count(DISTINCT asset_id) AS affected_assets,
       max(last_seen) AS last_seen
FROM findings
WHERE status = 'active'
GROUP BY 1, 2, 3, 4, 5
ORDER BY affected_assets DESC;

-- Trend giornaliero aperti/chiusi (alimentato dalle query API, materializzabile)
CREATE VIEW v_daily_lifecycle AS
SELECT tenant_id, environment_id,
       date_trunc('day', last_seen)::date  AS day,
       count(*) FILTER (WHERE status = 'active')   AS open_findings,
       count(*) FILTER (WHERE status = 'mitigated') AS mitigated_findings
FROM findings
GROUP BY 1, 2, 3;

-- -----------------------------------------------------------------------------
-- 8. RBAC minimale (le credenziali arriveranno in una fase successiva):
--    membership tenant-scoped con ruolo. Il subject esterno (SSO/IdP) verrà
--    mappato su memberships.external_subject.
-- -----------------------------------------------------------------------------
CREATE TABLE memberships (
    id               bigserial PRIMARY KEY,
    tenant_id        uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    external_subject text NOT NULL,        -- es. "okta:uid", "local:admin"
    display_name     text NOT NULL,
    role             membership_role NOT NULL DEFAULT 'viewer',
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, external_subject)
);
