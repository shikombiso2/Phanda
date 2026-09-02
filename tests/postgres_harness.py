"""Opt-in, disposable PostgreSQL harness for integration tests.

Creates an empty, uniquely named database and runs ``alembic upgrade head``
against it — nothing else. Before the Alembic baseline revision existed,
this had to reflect a live source database's tables into the test database
first, because no migration could create them from nothing. Now that
``20260101_baseline_legacy_schema`` creates the full schema on its own, that
reflection step would actively break things (Alembic's own ``create_table``
calls would collide with tables already reflected in), so it is gone.
"""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy import create_engine, text

from app.core.config import get_settings


class PostgresHarness:
    def __init__(self) -> None:
        self.source_engine = create_engine(get_settings().database_url)
        self.name = f"phanda_integration_test_{uuid.uuid4().hex[:12]}"
        self.test_url = self.source_engine.url.set(database=self.name)
        self.admin_engine = create_engine(self.source_engine.url.set(database="postgres"), isolation_level="AUTOCOMMIT")

    def create(self) -> None:
        with self.admin_engine.connect() as connection:
            connection.execute(text(f'create database "{self.name}"'))
        env = os.environ | {"DATABASE_URL": self.test_url.render_as_string(hide_password=False)}
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=Path(__file__).resolve().parents[1], env=env, check=True)

    def drop(self) -> None:
        with self.admin_engine.connect() as connection:
            connection.execute(text("select pg_terminate_backend(pid) from pg_stat_activity where datname = :name and pid != pg_backend_pid()"), {"name": self.name})
            connection.execute(text(f'drop database if exists "{self.name}"'))
        self.source_engine.dispose()
        self.admin_engine.dispose()
