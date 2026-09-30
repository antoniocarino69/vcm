"""ORM <-> database catalog parity (AGENTS: models.py must stay 1:1 with schema.sql).

Opt-in PostgreSQL suite. The SQLAlchemy metadata is created in a throwaway
schema inside one rolled-back transaction and its table/constraint catalog is
compared with the database catalog, which db/schema.sql (or its migrations)
must keep identical.
"""
from __future__ import annotations

import os
from typing import Iterator

import pytest

pytest.importorskip("sqlalchemy")
from sqlalchemy import create_engine, text

from app.models import Base

TMP_SCHEMA = "vcm_orm_parity_tmp"

CATALOG_QUERY = """
SELECT c.relname || ':' || con.conname || ':' || con.contype::text
FROM pg_constraint con
JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = :ns AND c.relname = ANY(:tables)
"""


@pytest.fixture
def parity_connection() -> Iterator:
    url = os.environ.get("VCM_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set VCM_TEST_DATABASE_URL for ORM parity tests")
    engine = create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()
    engine.dispose()


def _catalog(connection, namespace: str) -> set[str]:
    tables = sorted(Base.metadata.tables)
    return set(connection.execute(text(CATALOG_QUERY),
                                 {"ns": namespace, "tables": tables}).scalars().all())


def test_orm_matches_database_catalog(parity_connection) -> None:
    connection = parity_connection
    connection.execute(text(f"CREATE SCHEMA {TMP_SCHEMA}"))
    # DDL without schema lands in the first search_path entry.
    connection.execute(text(f"SET LOCAL search_path TO {TMP_SCHEMA}, public"))
    # checkfirst=False: public tables with the same names must not shadow the DDL.
    Base.metadata.create_all(connection, checkfirst=False)
    orm_catalog = _catalog(connection, TMP_SCHEMA)
    reference = _catalog(connection, "public")
    assert orm_catalog, "create_all produced no constraints"
    assert orm_catalog == reference, (
        f"ORM-only: {sorted(orm_catalog - reference)}; "
        f"schema-only: {sorted(reference - orm_catalog)}"
    )
