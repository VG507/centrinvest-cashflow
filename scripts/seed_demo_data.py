#!/usr/bin/env python3
"""
scripts/seed_second_demo_user.py

Creates a second demo user with two distinct commercial companies,
populates each with statement transactions from mentor datasets (C002 and C003),
detects recurring patterns, and computes initial forecasts.
Supports seeding both local and remote VPS PostgreSQL databases.
"""

import sys
import os
import asyncio
from datetime import date
from pathlib import Path

# Add backend directory to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import select, text

from src.models.entities import (
    User, Company, CompanyMembership, TransactionRecord, DailyActualRecord, ForecastSnapshotRecord
)
from src.services.auth_service import hash_password
from src.services.statement_service import StatementService
from src.services.forecaster_service import ForecasterService
from src.schemas.contracts import ColumnMapping, CreateForecastRequest

SECOND_USER_EMAIL = "client@centrinvest.ru"
SECOND_USER_PASSWORD = "password123"
SECOND_USER_NAME = "Анна Смирнова (Финансовый директор)"

COMPANIES_SPEC = [
    {
        "name": "ООО «Донские Продукты»",
        "business_type": "Продуктовый ритейл",
        "statement_file": PROJECT_ROOT / "data/statements/C002.csv",
        "as_of_date": "2026-09-29",
        "model": "weekday_mean"
    },
    {
        "name": "ИП «Южный Ремонт»",
        "business_type": "Строительство и ремонт",
        "statement_file": PROJECT_ROOT / "data/statements/C003.csv",
        "as_of_date": "2026-09-29",
        "model": "ridge_calendar"
    }
]


async def seed_database(db_url: str):
    print(f"\n[SEED] Connecting to database: {db_url}")
    engine = create_async_engine(db_url, echo=False)

    async with AsyncSession(engine, expire_on_commit=False) as db:
        # 1. Get or create second user
        q_user = await db.execute(select(User).where(User.email == SECOND_USER_EMAIL))
        user = q_user.scalar_one_or_none()
        if not user:
            user = User(
                email=SECOND_USER_EMAIL,
                password_hash=hash_password(SECOND_USER_PASSWORD),
                display_name=SECOND_USER_NAME
            )
            db.add(user)
            await db.flush()
            print(f"[OK] Created second user: {user.email} (id={user.id})")
        else:
            print(f"[EXISTS] User already exists: {user.email} (id={user.id})")

        # 2. Iterate companies
        for spec in COMPANIES_SPEC:
            comp_name = spec["name"]
            stmt_file = spec["statement_file"]

            q_comp = await db.execute(select(Company).where(Company.name == comp_name))
            company = q_comp.scalar_one_or_none()

            if not company:
                company = Company(
                    name=comp_name,
                    business_type=spec["business_type"],
                    currency="RUB",
                    timezone="Europe/Moscow",
                    data_revision=0
                )
                db.add(company)
                await db.flush()
                print(f"\n[OK] Created company: {company.name} (id={company.id})")
            else:
                print(f"\n[EXISTS] Company exists: {company.name} (id={company.id})")

            # Ensure membership
            q_mem = await db.execute(
                select(CompanyMembership).where(
                    CompanyMembership.user_id == user.id,
                    CompanyMembership.company_id == company.id
                )
            )
            if not q_mem.scalar_one_or_none():
                db.add(CompanyMembership(user_id=user.id, company_id=company.id))
                await db.flush()
                print(f"[OK] Bound user {user.email} to {company.name}")

            # Check if statement already loaded
            q_tx_count = await db.execute(
                select(text("count(*)")).select_from(TransactionRecord).where(
                    TransactionRecord.company_id == company.id
                )
            )
            tx_count = q_tx_count.scalar() or 0

            if tx_count == 0 and stmt_file.exists():
                print(f"[IMPORT] Ingesting statement from {stmt_file.name}...")
                with open(stmt_file, "rb") as f:
                    file_bytes = f.read()

                col_map = ColumnMapping(
                    date="operation_date",
                    amount="amount",
                    direction="direction",
                    counterparty_name="counterparty_name",
                    counterparty_inn="counterparty_inn",
                    purpose="payment_purpose",
                    closing_balance="balance_eod",
                    external_id="operation_id"
                )

                import_res = await StatementService.import_file(
                    db=db,
                    company_id=company.id,
                    file_bytes=file_bytes,
                    format_type="csv",
                    mapping=col_map,
                    balance_policy="reject_conflicts"
                )
                await db.refresh(company)
                print(f"[OK] Imported {import_res.accepted_rows} transactions. Closing balance: {company.closing_balance:,.2f} RUB")
            else:
                print(f"[EXISTS] Company has {tx_count} transactions.")

            # Check if forecast snapshot exists
            q_snap = await db.execute(
                select(ForecastSnapshotRecord)
                .where(ForecastSnapshotRecord.company_id == company.id)
                .order_by(ForecastSnapshotRecord.created_at.desc())
            )
            latest_snap = q_snap.scalars().first()
            if latest_snap:
                print(f"[EXISTS] Latest forecast: ID={latest_snap.id}, horizon={latest_snap.horizon_days}d")
            else:
                print(f"[FORECAST] Generating initial 30-day forecast for {company.name}...")
                await db.refresh(company)
                req = CreateForecastRequest(
                    as_of_date=spec["as_of_date"],
                    horizon_days=30,
                    initial_balance=company.closing_balance,
                    include_planned_events=True,
                    model=spec["model"],
                    expected_data_revision=company.data_revision
                )
                snap = await ForecasterService.create_forecast(db, company.id, req)
                await db.commit()
                print(f"[OK] Generated forecast: ID={snap.id}, end_balance={snap.summary.end_balance:,.2f} RUB")

        await db.commit()
    await engine.dispose()
    print(f"\n[DONE] Seeding finished successfully for: {db_url}")


async def main():
    local_db = "postgresql+asyncpg://postgres:postgrespassword@localhost:5432/hackrnd_db"
    remote_db = "postgresql+asyncpg://postgres:postgrespassword@194.113.106.233:5432/hackrnd_db"

    # Seed remote VPS database
    try:
        await seed_database(remote_db)
    except Exception as e:
        print(f"[WARN] Remote seeding failed: {e}")

    # Seed local database
    try:
        await seed_database(local_db)
    except Exception as e:
        print(f"[WARN] Local seeding failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
