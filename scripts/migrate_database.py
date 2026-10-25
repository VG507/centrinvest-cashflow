#!/usr/bin/env python3
"""Manual database migration and schema verification script for Hack RND 2026.

Ensures PostgreSQL tables and initial demo entities are created cleanly
on target database host.
"""

import argparse
import asyncio
import os
import sys
from typing import List

# Self-bootstrap using backend virtualenv if running under system python without deps
try:
    import asyncpg
    import sqlalchemy
except ImportError:
    repo_venv_python = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "backend", ".venv", "bin", "python3")
    )
    if os.path.exists(repo_venv_python) and sys.executable != repo_venv_python:
        os.execv(repo_venv_python, [repo_venv_python] + sys.argv)
    else:
        print("Error: Missing required database dependencies (sqlalchemy, asyncpg).", file=sys.stderr)
        print("Please run inside backend virtual environment or via: uv run python scripts/migrate_database.py", file=sys.stderr)
        sys.exit(1)

from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base

# Add backend directory to sys.path to load models
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from src.database import Base
from src.models.entities import (
    CategoryOverride,
    Company,
    CompanyMembership,
    DailyActualRecord,
    EvaluationRecord,
    ForecastSnapshotRecord,
    ImportRecord,
    IntegrationRecord,
    PlannedEventRecord,
    RecurringPatternRecord,
    ScenarioRecord,
    Session,
    TransactionRecord,
    User,
)
from src.services.auth_service import AuthService

DEFAULT_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgrespassword@localhost:5432/hackrnd_db"
)

DEFAULT_REDIS_URL = os.environ.get(
    "REDIS_URL",
    "redis://:HackRndRedis2026!@194.113.106.233:6379/0"
)

EXPECTED_TABLES = [
    "category_overrides",
    "companies",
    "company_memberships",
    "daily_actuals",
    "evaluations",
    "forecast_snapshots",
    "imports",
    "integrations",
    "planned_events",
    "recurring_patterns",
    "scenarios",
    "sessions",
    "transactions",
    "users"
]


async def run_migration(db_url: str) -> bool:
    """Execute migration and verification against target PostgreSQL database."""
    print(f"Connecting to database at {db_url}...")
    engine = create_async_engine(db_url, echo=False)

    try:
        async with engine.begin() as conn:
            # Enable extensions if available
            try:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                print("pgvector extension check passed.")
            except Exception as e:
                print(f"Notice: pgvector extension skipped or not present: {e}")

            # Create all tables registered in Base metadata
            print("Creating database schema and tables...")
            await conn.run_sync(Base.metadata.create_all)

        # Verify tables synchronously on the connection
        def get_existing_tables(sync_conn) -> List[str]:
            inspector = inspect(sync_conn)
            return inspector.get_table_names()

        async with engine.connect() as conn:
            existing = await conn.run_sync(get_existing_tables)
            print(f"Discovered tables in database ({len(existing)}): {', '.join(sorted(existing))}")
            missing = [tbl for tbl in EXPECTED_TABLES if tbl not in existing]
            if missing:
                print(f"Error: Missing expected tables: {missing}", file=sys.stderr)
                return False

        # Seed initial demo entities
        async with AsyncSession(engine, expire_on_commit=False) as session:
            print("Seeding demo user and default company...")
            user = await AuthService.get_or_create_demo_user(session)
            print(f"Demo user verified: id={user.id}, email={user.email}")

            comp_res = await session.execute(select(Company))
            existing_comp = comp_res.scalars().first()
            if not existing_comp:
                company = Company(
                    name="ООО «Грузоперевозки-063»",
                    business_type="Грузоперевозки",
                    currency="RUB",
                    timezone="Europe/Moscow",
                    data_revision=0
                )
                session.add(company)
                await session.flush()
                session.add(CompanyMembership(user_id=user.id, company_id=company.id))
                await session.commit()
                print(f"Created default company: id={company.id}, name={company.name}")
            else:
                print(f"Default company already exists: id={existing_comp.id}, name={existing_comp.name}")

        print("Migration and schema initialization completed successfully.")
        return True

    except Exception as err:
        print(f"Migration failed with error: {err}", file=sys.stderr)
        return False
    finally:
        await engine.dispose()


def notify_bridge(redis_url: str, db_url: str, details: str = "Database schema synchronized"):
    """Optionally broadcast migration event over Redis bridge."""
    try:
        import redis
        client = redis.Redis.from_url(redis_url, decode_responses=True)
        # Import bridge publisher if available
        bridge_script = os.path.join(os.path.dirname(__file__), "agent_redis_bridge.py")
        if os.path.exists(bridge_script):
            import agent_redis_bridge
            agent_redis_bridge.publish_event(
                client=client,
                channel="agent:events",
                event_type="migration_completed",
                data={
                    "target": "vps",
                    "revision": "v2.0.0",
                    "details": details,
                    "db_target": db_url.split("@")[-1] if "@" in db_url else db_url
                },
                sender="backend"
            )
            print("Successfully published migration notification to Redis bridge.")
    except Exception as err:
        print(f"Notice: Redis notification skipped: {err}")


def main():
    parser = argparse.ArgumentParser(description="Hack RND 2026 Manual DB Migration")
    parser.add_argument("--db-url", default=DEFAULT_DB_URL, help="Asyncpg database URL")
    parser.add_argument("--notify-redis", action="store_true", help="Broadcast migration event to Redis bridge")
    parser.add_argument("--redis-url", default=DEFAULT_REDIS_URL, help="Redis bridge URL")
    args = parser.parse_args()

    success = asyncio.run(run_migration(args.db_url))
    if not success:
        sys.exit(1)

    if args.notify_redis:
        notify_bridge(args.redis_url, args.db_url)


if __name__ == "__main__":
    main()

