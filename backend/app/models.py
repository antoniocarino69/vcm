"""Modelli SQLAlchemy 1:1 con db/schema.sql (enum nativi PG, create_type=False)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (BigInteger, Boolean, CheckConstraint, Date, DateTime,
                        Enum, ForeignKey, ForeignKeyConstraint, Index, Integer,
                        Numeric, SmallInteger, Text, UniqueConstraint, text)
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _pg_enum(name: str, *values: str) -> Enum:
    """Enum nativo PostgreSQL già creato da schema.sql (niente CREATE TYPE)."""
    return Enum(*values, name=name, native_enum=True, create_type=False,
                validate_strings=True)


TENANT_STATUS = _pg_enum("tenant_status", "active", "archived")
ENVIRONMENT_KIND = _pg_enum("environment_kind", "production", "dmz",
                            "active_directory", "staging", "cloud", "ot", "other")
ASSET_MATCH_KEY = _pg_enum("asset_match_key", "ip", "fqdn", "netbios")
SCANNER_TYPE = _pg_enum("scanner_type", "qualys_vmdr", "tenable_nessus",
                        "scc_xccdf", "pingcastle", "purple_knight")
IMPORT_STATUS = _pg_enum("import_status", "pending", "parsing", "completed",
                         "failed", "cancelled")
FINDING_KIND = _pg_enum("finding_kind", "vulnerability", "compliance")
SEVERITY_LEVEL = _pg_enum("severity_level", "critical", "high", "medium", "low", "info")
STIG_CATEGORY = _pg_enum("stig_category", "CAT_I", "CAT_II", "CAT_III")
COMPLIANCE_RESULT = _pg_enum("compliance_result", "pass", "fail", "not_reviewed",
                             "not_applicable", "error")
FINDING_STATUS = _pg_enum("finding_status", "active", "mitigated",
                          "false_positive", "risk_accepted")
REPORT_KIND = _pg_enum("report_kind", "executive", "technical")
REPORT_FORMAT = _pg_enum("report_format", "html", "pdf", "csv")
REPORT_STATUS = _pg_enum("report_status", "pending", "rendering", "ready", "failed")
MEMBERSHIP_ROLE = _pg_enum("membership_role", "admin", "analyst", "viewer")


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(UUID, primary_key=True, server_default=text("gen_random_uuid()"))
    slug: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(TENANT_STATUS, server_default=text("'active'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class Environment(Base):
    __tablename__ = "environments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="environments_tenant_id_name_key"),
        Index("environments_id_tenant_uidx", "id", "tenant_id", unique=True),
    )
    id: Mapped[str] = mapped_column(UUID, primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[str] = mapped_column(UUID, ForeignKey("tenants.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(ENVIRONMENT_KIND, server_default=text("'other'"))
    tags: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    match_key: Mapped[str] = mapped_column(ASSET_MATCH_KEY, server_default=text("'ip'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class Asset(Base):
    __tablename__ = "assets"
    # CHECK constraints mirror db/schema.sql (same names as PostgreSQL defaults).
    __table_args__ = (
        CheckConstraint("criticality BETWEEN 1 AND 5", name="assets_criticality_check"),
        CheckConstraint("ip IS NOT NULL OR fqdn IS NOT NULL OR hostname_netbios IS NOT NULL",
                        name="assets_has_identity"),
        Index("assets_id_tenant_uidx", "id", "tenant_id", unique=True),
    )
    id: Mapped[str] = mapped_column(UUID, primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[str] = mapped_column(UUID, ForeignKey("tenants.id", ondelete="CASCADE"))
    environment_id: Mapped[str] = mapped_column(UUID, ForeignKey("environments.id", ondelete="RESTRICT"))
    ip: Mapped[Optional[str]] = mapped_column(INET)
    fqdn: Mapped[Optional[str]] = mapped_column(Text)
    hostname_netbios: Mapped[Optional[str]] = mapped_column(Text)
    os: Mapped[Optional[str]] = mapped_column(Text)
    criticality: Mapped[int] = mapped_column(SmallInteger, server_default=text("3"))
    tags: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class AssetMove(Base):
    """Composite keys keep move rows on one client (schema.sql is the source of
    truth; SQLAlchemy cannot express column-list SET NULL, see db/migrations/)."""
    __tablename__ = "asset_moves"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="asset_moves_tenant_fkey"),
        ForeignKeyConstraint(["asset_id", "tenant_id"], ["assets.id", "assets.tenant_id"],
                             ondelete="CASCADE", name="asset_moves_asset_tenant_fkey"),
        ForeignKeyConstraint(["from_environment_id", "tenant_id"],
                             ["environments.id", "environments.tenant_id"],
                             ondelete="SET NULL",
                             name="asset_moves_from_environment_tenant_fkey"),
        ForeignKeyConstraint(["to_environment_id", "tenant_id"],
                             ["environments.id", "environments.tenant_id"],
                             ondelete="RESTRICT",
                             name="asset_moves_to_environment_tenant_fkey"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(UUID)
    asset_id: Mapped[str] = mapped_column(UUID)
    from_environment_id: Mapped[Optional[str]] = mapped_column(UUID)
    to_environment_id: Mapped[str] = mapped_column(UUID)
    moved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    reason: Mapped[Optional[str]] = mapped_column(Text)


class ScanImport(Base):
    __tablename__ = "scan_imports"
    __table_args__ = (
        UniqueConstraint("tenant_id", "content_sha256",
                         name="scan_imports_tenant_id_content_sha256_key"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="scan_imports_tenant_fkey"),
        ForeignKeyConstraint(["environment_id", "tenant_id"],
                             ["environments.id", "environments.tenant_id"],
                             ondelete="RESTRICT",
                             name="scan_imports_environment_tenant_fkey"),
        Index("scan_imports_id_tenant_uidx", "id", "tenant_id", unique=True),
    )
    id: Mapped[str] = mapped_column(UUID, primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[str] = mapped_column(UUID)
    environment_id: Mapped[str] = mapped_column(UUID)
    scanner: Mapped[str] = mapped_column(SCANNER_TYPE)
    filename: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(Text)
    storage_path: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(IMPORT_STATUS, server_default=text("'pending'"))
    auto_close: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    stats: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    error: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (
        CheckConstraint("port BETWEEN 0 AND 65535", name="findings_port_check"),
        CheckConstraint("(kind = 'vulnerability' AND result IS NULL) "
                        "OR (kind = 'compliance' AND result IS NOT NULL)",
                        name="findings_vuln_shape"),
        CheckConstraint("status <> 'risk_accepted' OR status_reason IS NOT NULL",
                        name="findings_risk_acceptance"),
        CheckConstraint("(status = 'active' AND closed_at IS NULL) "
                        "OR (status <> 'active' AND closed_at IS NOT NULL)",
                        name="findings_open_iff_active"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="findings_tenant_fkey"),
        ForeignKeyConstraint(["asset_id", "tenant_id"], ["assets.id", "assets.tenant_id"],
                             ondelete="CASCADE", name="findings_asset_tenant_fkey"),
        ForeignKeyConstraint(["environment_id", "tenant_id"],
                             ["environments.id", "environments.tenant_id"],
                             ondelete="RESTRICT",
                             name="findings_environment_tenant_fkey"),
        ForeignKeyConstraint(["last_import_id", "tenant_id"],
                             ["scan_imports.id", "scan_imports.tenant_id"],
                             ondelete="SET NULL",
                             name="findings_last_import_tenant_fkey"),
        ForeignKeyConstraint(["closed_by_import_id", "tenant_id"],
                             ["scan_imports.id", "scan_imports.tenant_id"],
                             ondelete="SET NULL",
                             name="findings_closed_by_import_tenant_fkey"),
        Index("findings_id_tenant_uidx", "id", "tenant_id", unique=True),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(UUID)
    asset_id: Mapped[str] = mapped_column(UUID)
    environment_id: Mapped[str] = mapped_column(UUID)
    kind: Mapped[str] = mapped_column(FINDING_KIND)
    scanner: Mapped[str] = mapped_column(SCANNER_TYPE)
    rule_id: Mapped[str] = mapped_column(Text)
    rule_title: Mapped[str] = mapped_column(Text)
    category: Mapped[Optional[str]] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(SEVERITY_LEVEL)
    severity_raw: Mapped[Optional[str]] = mapped_column(Text)
    stig_category: Mapped[Optional[str]] = mapped_column(STIG_CATEGORY)
    cvss_score: Mapped[Optional[float]] = mapped_column(Numeric(4, 1))
    cvss_vector: Mapped[Optional[str]] = mapped_column(Text)
    cves: Mapped[list] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    port: Mapped[Optional[int]] = mapped_column(Integer)
    protocol: Mapped[Optional[str]] = mapped_column(Text)
    benchmark: Mapped[Optional[str]] = mapped_column(Text)
    profile: Mapped[Optional[str]] = mapped_column(Text)
    result: Mapped[Optional[str]] = mapped_column(COMPLIANCE_RESULT)
    affected_objects: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    description: Mapped[Optional[str]] = mapped_column(Text)
    solution: Mapped[Optional[str]] = mapped_column(Text)
    scanner_output: Mapped[Optional[str]] = mapped_column(Text)
    dedup_hash: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(FINDING_STATUS, server_default=text("'active'"))
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    occurrence_count: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    last_import_id: Mapped[Optional[str]] = mapped_column(UUID)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    closed_by_import_id: Mapped[Optional[str]] = mapped_column(UUID)
    status_reason: Mapped[Optional[str]] = mapped_column(Text)
    risk_accepted_until: Mapped[Optional[date]] = mapped_column(Date)
    raw: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class FindingStatusHistory(Base):
    __tablename__ = "finding_status_history"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="finding_status_history_tenant_fkey"),
        ForeignKeyConstraint(["finding_id", "tenant_id"],
                             ["findings.id", "findings.tenant_id"],
                             ondelete="CASCADE",
                             name="finding_status_history_finding_tenant_fkey"),
        ForeignKeyConstraint(["import_id", "tenant_id"],
                             ["scan_imports.id", "scan_imports.tenant_id"],
                             ondelete="SET NULL",
                             name="finding_status_history_import_tenant_fkey"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(UUID)
    finding_id: Mapped[int] = mapped_column(BigInteger)
    from_status: Mapped[Optional[str]] = mapped_column(FINDING_STATUS)
    to_status: Mapped[str] = mapped_column(FINDING_STATUS)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    import_id: Mapped[Optional[str]] = mapped_column(UUID)
    changed_by: Mapped[Optional[str]] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class FindingComment(Base):
    __tablename__ = "finding_comments"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="finding_comments_tenant_fkey"),
        ForeignKeyConstraint(["finding_id", "tenant_id"],
                             ["findings.id", "findings.tenant_id"],
                             ondelete="CASCADE",
                             name="finding_comments_finding_tenant_fkey"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(UUID)
    finding_id: Mapped[int] = mapped_column(BigInteger)
    author: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class ADHealthSnapshot(Base):
    __tablename__ = "ad_health_snapshots"
    __table_args__ = (
        CheckConstraint("tool IN ('pingcastle', 'purple_knight')",
                        name="ad_health_snapshots_tool_check"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="ad_health_snapshots_tenant_fkey"),
        ForeignKeyConstraint(["environment_id", "tenant_id"],
                             ["environments.id", "environments.tenant_id"],
                             ondelete="CASCADE",
                             name="ad_health_environment_tenant_fkey"),
        ForeignKeyConstraint(["asset_id", "tenant_id"], ["assets.id", "assets.tenant_id"],
                             ondelete="SET NULL", name="ad_health_asset_tenant_fkey"),
        ForeignKeyConstraint(["import_id", "tenant_id"],
                             ["scan_imports.id", "scan_imports.tenant_id"],
                             ondelete="SET NULL", name="ad_health_import_tenant_fkey"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(UUID)
    environment_id: Mapped[str] = mapped_column(UUID)
    asset_id: Mapped[Optional[str]] = mapped_column(UUID)
    tool: Mapped[str] = mapped_column(SCANNER_TYPE)
    global_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    category_scores: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    import_id: Mapped[Optional[str]] = mapped_column(UUID)
    raw: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


class ReportJob(Base):
    __tablename__ = "report_jobs"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="report_jobs_tenant_fkey"),
        ForeignKeyConstraint(["environment_id", "tenant_id"],
                             ["environments.id", "environments.tenant_id"],
                             ondelete="CASCADE",
                             name="report_jobs_environment_tenant_fkey"),
    )
    id: Mapped[str] = mapped_column(UUID, primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[str] = mapped_column(UUID)
    environment_id: Mapped[Optional[str]] = mapped_column(UUID)
    kind: Mapped[str] = mapped_column(REPORT_KIND)
    format: Mapped[str] = mapped_column(REPORT_FORMAT, server_default=text("'html'"))
    status: Mapped[str] = mapped_column(REPORT_STATUS, server_default=text("'pending'"))
    options: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    storage_path: Mapped[Optional[str]] = mapped_column(Text)
    error: Mapped[Optional[str]] = mapped_column(Text)
    requested_by: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_subject",
                         name="memberships_tenant_id_external_subject_key"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(UUID, ForeignKey("tenants.id", ondelete="CASCADE"))
    external_subject: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(MEMBERSHIP_ROLE, server_default=text("'viewer'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
