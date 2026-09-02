"""Verify the full Alembic migration chain on a disposable, empty database.

This used to reflect a live source database's already-existing legacy tables
into the test database before running Alembic, because no migration could
create them from nothing — the schema predated Alembic entirely. Now that
``20260101_baseline_legacy_schema`` creates the complete schema on its own,
that reflection step is gone: this script creates a genuinely empty database,
proving the full chain (baseline → CV tailoring → email/password auth) works
the way ``README.md`` claims it does, with no dependency on any pre-existing
database.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from app.core.config import get_settings

LEGACY_TABLES = {"applications", "listings", "profiles", "saved_opportunities", "users", "wallet", "entitlements", "feature_usage"}
CV_TAILORING_TABLES = {"cv_versions", "tailored_documents", "tailoring_request_reservations", "reward_events"}
AUTH_TABLES = {"user_auth_identities", "refresh_tokens"}
ALL_EXPECTED_TABLES = LEGACY_TABLES | CV_TAILORING_TABLES | AUTH_TABLES


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="phanda_migration_test")
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--replace-existing", action="store_true", help="Drop only the named disposable test database before testing")
    args = parser.parse_args()
    if not args.database.startswith("phanda_migration_test"):
        raise SystemExit("Refusing a non-test database name")

    source_engine = create_engine(get_settings().database_url)
    source_name = source_engine.url.database
    if args.database == source_name:
        raise SystemExit("Refusing to use the configured source database as a test target")
    admin_engine = create_engine(source_engine.url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    created = False
    try:
        with admin_engine.connect() as admin:
            exists = admin.execute(text("select 1 from pg_database where datname = :name"), {"name": args.database}).scalar()
            if exists and not args.replace_existing:
                raise RuntimeError(f"Test database already exists: {args.database}")
            if exists:
                admin.execute(text("select pg_terminate_backend(pid) from pg_stat_activity where datname = :name and pid <> pg_backend_pid()"), {"name": args.database})
                admin.execute(text(f'drop database "{args.database}"'))
            admin.execute(text(f'create database "{args.database}"'))
            created = True

        test_url = source_engine.url.set(database=args.database)
        command_env = os.environ | {"DATABASE_URL": test_url.render_as_string(hide_password=False)}
        root = Path(__file__).resolve().parents[1]
        _alembic(root, command_env, "upgrade", "head")
        _verify_full_schema(test_url)
        _alembic(root, command_env, "downgrade", "base")
        _verify_empty(test_url)
        _alembic(root, command_env, "upgrade", "head")
        _verify_full_schema(test_url)
        print(f"Migration chain verified from empty on {args.database}")
    finally:
        source_engine.dispose()
        if created and not args.keep:
            with admin_engine.connect() as admin:
                admin.execute(text("select pg_terminate_backend(pid) from pg_stat_activity where datname = :name and pid <> pg_backend_pid()"), {"name": args.database})
                still_exists = admin.execute(text("select 1 from pg_database where datname = :name"), {"name": args.database}).scalar()
                if still_exists:
                    admin.execute(text(f'drop database "{args.database}"'))
                    print(f"Removed disposable database {args.database}")
        admin_engine.dispose()


def _alembic(root: Path, env: dict[str, str], *args: str) -> None:
    subprocess.run([sys.executable, "-m", "alembic", *args], cwd=root, env=env, check=True)


def _verify_full_schema(url) -> None:
    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert ALL_EXPECTED_TABLES.issubset(tables), f"Missing tables: {ALL_EXPECTED_TABLES - tables}"
        assert "otp_challenges" not in tables, "otp_challenges should have been dropped by the auth migration"
        _columns(inspector, "users", {"email", "password_hash", "email_verified_at", "last_login_at"})
        assert "phone_number" not in {c["name"] for c in inspector.get_columns("users")}, "phone_number should have been dropped"
        _columns(inspector, "profiles", {"active_cv_version_id"})
        _columns(inspector, "applications", {"tailored_document_id", "submission_status", "idempotency_key", "email_provider_message_id", "email_attempt_count"})
        _columns(inspector, "listings", {"category", "last_seen_at"})
        _columns(inspector, "cv_versions", {"candidate_facts_json", "extracted_text_key", "sha256", "attempt_count", "processing_lease_expires_at"})
        _columns(inspector, "tailored_documents", {"listing_snapshot_json", "profile_snapshot_json", "idempotency_key", "correction_attempted"})
        _columns(inspector, "user_auth_identities", {"provider", "provider_subject"})
        _columns(inspector, "refresh_tokens", {"token_hash", "expires_at", "revoked_at", "rotated_from_id"})
        _unique(inspector, "users", {"email"})
        _unique(inspector, "cv_versions", {"user_id", "version_number"})
        _unique(inspector, "tailored_documents", {"user_id", "listing_id", "cv_version_id"})
        _unique(inspector, "tailoring_request_reservations", {"tailored_document_id"})
        _unique(inspector, "reward_events", {"provider", "external_event_id"})
        _unique(inspector, "applications", {"user_id", "idempotency_key"})
        _unique(inspector, "user_auth_identities", {"provider", "provider_subject"})
        _unique(inspector, "refresh_tokens", {"token_hash"})
        _foreign_key(inspector, "profiles", "active_cv_version_id", "cv_versions")
        _foreign_key(inspector, "applications", "tailored_document_id", "tailored_documents")
        _foreign_key(inspector, "user_auth_identities", "user_id", "users")
        _foreign_key(inspector, "refresh_tokens", "user_id", "users")
        with engine.connect() as connection:
            enum_values = connection.execute(text("select unnest(enum_range(null::applicationstatus))::text")).scalars().all()
            assert {"prepared", "external_started"}.issubset(enum_values), "Application status enum not extended"
    finally:
        engine.dispose()


def _verify_empty(url) -> None:
    engine = create_engine(url)
    try:
        tables = set(inspect(engine).get_table_names())
        assert not tables, f"downgrade base left tables behind: {tables}"
    finally:
        engine.dispose()


def _columns(inspector, table: str, expected: set[str]) -> None:
    actual = {column["name"] for column in inspector.get_columns(table)}
    assert expected.issubset(actual), f"{table} missing {expected - actual}"


def _unique(inspector, table: str, expected: set[str]) -> None:
    constraints = [set(item["column_names"] or []) for item in inspector.get_unique_constraints(table)]
    assert expected in constraints, f"{table} missing unique constraint {expected}"


def _foreign_key(inspector, table: str, column: str, target_table: str) -> None:
    for key in inspector.get_foreign_keys(table):
        if key["constrained_columns"] == [column] and key["referred_table"] == target_table:
            return
    raise AssertionError(f"{table}.{column} foreign key is missing")


if __name__ == "__main__":
    main()
