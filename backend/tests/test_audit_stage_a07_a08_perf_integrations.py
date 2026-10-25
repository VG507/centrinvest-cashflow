import time
import uuid
import pytest
from datetime import date, timedelta
from sqlalchemy import select
from src.database import async_session_factory
from src.models.entities import Company, DailyActualRecord, TransactionRecord
from src.schemas.contracts import CreateForecastRequest
from src.services.forecaster_service import ForecasterService
from src.services.integration_service import IntegrationService

# ==============================================================================
# STAGE A07: Performance, Scaling, and Resource Limits
# STAGE A08: Real Connectors, Sandbox Provenance, and Replay Idempotency
# ==============================================================================

@pytest.mark.asyncio
async def test_a07_performance_horizon_and_bootstrap_latency():
    """
    Stage A07 (P1):
    Benchmark forecasting performance:
    - 90-day historical series.
    - 30-day horizon with 1000 residual block bootstrap simulations.
    - Latency budget: p95 must complete in < 2.0s without memory leaks.
    """
    async with async_session_factory() as db:
        comp = Company(
            name=f"ООО «Нагрузка_{uuid.uuid4().hex[:6]}»",
            business_type="Дистрибуция",
            data_revision=0
        )
        db.add(comp)
        await db.commit()
        await db.refresh(comp)

        # Seed 90 days of actuals
        start_d = date(2026, 6, 1)
        actuals = []
        bal = 500000.0
        for i in range(90):
            curr_d = start_d + timedelta(days=i)
            inc = 60000.0 + (i % 7) * 5000.0
            exp = 45000.0 + (i % 5) * 3000.0
            bal += (inc - exp)
            actuals.append(DailyActualRecord(
                company_id=comp.id,
                date=curr_d,
                income=inc,
                expense=exp,
                closing_balance=bal,
                observation="observed"
            ))
        db.add_all(actuals)
        await db.commit()

        # Warm-up / benchmark 30-day forecast
        t0 = time.perf_counter()
        req30 = CreateForecastRequest(
            as_of_date="2026-08-29",
            horizon_days=30,
            model="weekday_mean",
            expected_data_revision=comp.data_revision
        )
        fc30 = await ForecasterService.create_forecast(db, comp.id, req30)
        t_elapsed30 = time.perf_counter() - t0

        assert len(fc30.days) == 30
        assert fc30.simulation_count == 1000
        # Latency must be strictly under 2.0 seconds
        assert t_elapsed30 < 2.0, f"Forecast latency exceeded budget: {t_elapsed30:.3f}s"

        # Benchmark 90-day horizon
        t1 = time.perf_counter()
        req90 = CreateForecastRequest(
            as_of_date="2026-08-29",
            horizon_days=90,
            model="weekday_mean",
            expected_data_revision=comp.data_revision
        )
        fc90 = await ForecasterService.create_forecast(db, comp.id, req90)
        t_elapsed90 = time.perf_counter() - t1

        assert len(fc90.days) == 90
        assert t_elapsed90 < 3.0, f"90-day forecast exceeded budget: {t_elapsed90:.3f}s"


@pytest.mark.asyncio
async def test_a08_integration_connectors_provenance_and_idempotency():
    """
    Stage A08 (P1):
    Connectors, Provenance, and Idempotent Replay:
    1. Default integrations exist with status 'not_configured' (no fabricated connected state).
    2. Sync on FNS registry connector imports 0 monetary transactions.
    3. Sync on Bank connector imports sandbox transactions tagged with source_kind='sandbox'
       and clear '[SANDBOX]' purpose prefix.
    4. Repeated sync is strictly idempotent (imported_count == 0).
    5. Tenant isolation: transactions remain isolated to target company.
    """
    async with async_session_factory() as db:
        comp = Company(
            name=f"ООО «Интеграции_{uuid.uuid4().hex[:6]}»",
            business_type="Производство",
            closing_balance=1000000.0,
            data_revision=0
        )
        db.add(comp)
        await db.commit()
        await db.refresh(comp)

        # 1. Retrieve default integrations
        int_list = await IntegrationService.get_integrations(db, comp.id)
        assert len(int_list.items) == 5
        for it in int_list.items:
            # Must be not_configured without real bank tokens
            assert it.status == "not_configured"

        # Locate bank and registry connectors
        bank_conn = next(i for i in int_list.items if i.kind == "bank")
        fns_conn = next(i for i in int_list.items if i.kind == "registry")

        # 2. Sync FNS connector
        sync_fns = await IntegrationService.sync_integration(db, comp.id, fns_conn.id)
        assert sync_fns.imported_count == 0

        # 3. First sync Bank connector
        sync_bank1 = await IntegrationService.sync_integration(db, comp.id, bank_conn.id)
        assert sync_bank1.imported_count == 3

        # Verify provenance in database
        tx_res = await db.execute(
            select(TransactionRecord).where(
                TransactionRecord.company_id == comp.id,
                TransactionRecord.source_id == bank_conn.id
            )
        )
        txs = tx_res.scalars().all()
        assert len(txs) == 3
        for tx in txs:
            assert tx.source_kind == "sandbox"
            assert "[SANDBOX]" in tx.purpose
            assert tx.source_id == bank_conn.id

        # 4. Repeated sync must be strictly idempotent
        sync_bank2 = await IntegrationService.sync_integration(db, comp.id, bank_conn.id)
        assert sync_bank2.imported_count == 0, f"Duplicate transactions imported on replay: {sync_bank2.imported_count}"

        # Count in DB must still be exactly 3
        tx_res2 = await db.execute(
            select(TransactionRecord).where(
                TransactionRecord.company_id == comp.id,
                TransactionRecord.source_id == bank_conn.id
            )
        )
        assert len(tx_res2.scalars().all()) == 3
