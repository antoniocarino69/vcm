"""Modelli SQLAlchemy 1:1 con db/schema.sql (enum nativi PG, create_type=False)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (BigInteger, Boolean, Date, DateTime, Enum, ForeignKey,
                        Integer, Numeric, SmallInteger, Text, text)
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
    __tablename__ = "asset_moves"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(UUID, ForeignKey("assets.id", ondelete="CASCADE"))
    from_environment_id: Mapped[Optional[str]] = mapped_column(UUID, ForeignKey("environments.id", ondelete="SET NULL"))
    to_environment_id: Mapped[str] = mapped_column(UUID, ForeignKey("environments.id", ondelete="RESTRICT"))
    moved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    reason: Mapped[Optional[str]] = mapped_column(Text)


class ScanImport(Base):
    __tablename__ = "scan_imports"
    id: Mapped[str] = mapped_column(UUID, primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[str] = mapped_column(UUID, ForeignKey("tenants.id", ondelete="CASCADE"))
    environment_id: Mapped[str] = mapped_column(UUID, ForeignKey("environments.id", ondelete="RESTRICT"))
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
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(UUID, ForeignKey("tenants.id", ondelete="CASCADE"))
    asset_id: Mapped[str] = mapped_column(UUID, ForeignKey("assets.id", ondelete="CASCADE"))
    environment_id: Mapped[str] = mapped_column(UUID, ForeignKey("environments.id", ondelete="RESTRICT"))
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
    last_import_id: Mapped[Optional[str]] = mapped_column(UUID, ForeignKey("scan_imports.id", ondelete="SET NULL"))
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    closed_by_import_id: Mapped[Optional[str]] = mapped_column(UUID, ForeignKey("scan_imports.id", ondelete="SET NULL"))
    status_reason: Mapped[Optional[str]] = mapped_column(Text)
    risk_accepted_until: Mapped[Optional[date]] = mapped_column(Date)
    raw: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class FindingStatusHistory(Base):
    __tablename__ = "finding_status_history"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    finding_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("findings.id", ondelete="CASCADE"))
    from_status: Mapped[Optional[str]] = mapped_column(FINDING_STATUS)
    to_status: Mapped[str] = mapped_column(FINDING_STATUS)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    import_id: Mapped[Optional[str]] = mapped_column(UUID, ForeignKey("scan_imports.id", ondelete="SET NULL"))
    changed_by: Mapped[Optional[str]] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class FindingComment(Base):
    __tablename__ = "finding_comments"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    finding_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("findings.id", ondelete="CASCADE"))
    author: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class ADHealthSnapshot(Base):
    __tablename__ = "ad_health_snapshots"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(UUID, ForeignKey("tenants.id", ondelete="CASCADE"))
    environment_id: Mapped[str] = mapped_column(UUID, ForeignKey("environments.id", ondelete="CASCADE"))
    asset_id: Mapped[Optional[str]] = mapped_column(UUID, ForeignKey("assets.id", ondelete="SET NULL"))
    tool: Mapped[str] = mapped_column(SCANNER_TYPE)
    global_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    category_scores: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    import_id: Mapped[Optional[str]] = mapped_column(UUID, ForeignKey("scan_imports.id", ondelete="SET NULL"))
    raw: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


class ReportJob(Base):
    __tablename__ = "report_jobs"
    id: Mapped[str] = mapped_column(UUID, primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[str] = mapped_column(UUID, ForeignKey("tenants.id", ondelete="CASCADE"))
    environment_id: Mapped[Optional[str]] = mapped_column(UUID, ForeignKey("environments.id", ondelete="CASCADE"))
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
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(UUID, ForeignKey("tenants.id", ondelete="CASCADE"))
    external_subject: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(MEMBERSHIP_ROLE, server_default=text("'viewer'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
