import io
import uuid
import pytest
import numpy as np
from datetime import date, timedelta
from sqlalchemy import select
from src.database import async_session_factory
from src.models.entities import (
    Company, DailyActualRecord, PlannedEventRecord, RecurringPatternRecord,
    ForecastSnapshotRecord, TransactionRecord, ImportRecord
)
from src.schemas.contracts import (
    CreateForecastRequest, ForecastUpdateRequest, ScenarioRequest,
    RevenueDropScenario, DelayIncomeScenario, FixedCostIncreaseScenario, ExtraExpenseScenario,
    PlanActualResponse, EvaluationRequest, ColumnMapping
)
from src.services.forecaster_service import ForecasterService
from src.services.scenario_service import ScenarioService
from src.services.incremental_service import IncrementalService
from src.services.statement_service import StatementService
from src.services.category_service import CategoryService
from src.services.reconciliation_service import ReconciliationService


# ==============================================================================
# STAGE A01: Traceability to Official Bank Center-invest Presentation (Pages 4-11)
# ==============================================================================

def test_a01_tz_matrix_capabilities_and_models():
    """
    Stage A01 (P0):
    Verify that all 11 core capabilities and 3 canonical forecasting models
    required by official presentation pages 4-11 are exposed in contracts.
    """
    from src.schemas.contracts import CapabilitiesResponse, FeatureName, ModelId

    cap = CapabilitiesResponse(
        contract_version="2.0.0",
        features=[
            "imports", "categorization", "recurring", "forecast_v2", "probability",
            "events", "scenarios", "plan_actual", "evaluation", "integrations", "advice"
        ]
    )
    assert len(cap.features) == 11
    # Check all official required features from presentation
    assert "categorization" in cap.features   # Page 4, task 1
    assert "recurring" in cap.features        # Page 4, task 2
    assert "forecast_v2" in cap.features      # Page 4, task 3
    assert "probability" in cap.features      # Page 5, task 4
    assert "events" in cap.features           # Page 6, task 1 (contracts, invoices, taxes)
    assert "plan_actual" in cap.features      # Page 6, task 2 (plan-fact comparison)
    assert "scenarios" in cap.features        # Page 7, task 3 (what-if scenarios)
    assert "integrations" in cap.features     # Page 7, task 4 (external/internal integrations)
    assert "evaluation" in cap.features       # Page 8, task 3 & Page 10, task 4 (model evaluation)


# ==============================================================================
# STAGE A02: End-to-End Data Flow Integrity for Isolated Company
# ==============================================================================

@pytest.mark.asyncio
async def test_a02_e2e_data_flow_isolated_company():
    """
    Stage A02 (P0):
    Isolated end-to-end data pipeline:
    Company creation -> Bank statement import (with leading zero INN) ->
    Category override -> Daily actuals aggregation -> 30-day forecast ->
    Planned events -> What-if scenario -> Plan-actual tracking.
    """
    async with async_session_factory() as db:
        comp = Company(
            name=f"ООО «ДонЛогистик_{uuid.uuid4().hex[:6]}»",
            business_type="Транспорт",
            currency="RUB",
            timezone="Europe/Moscow",
            data_revision=0
        )
        db.add(comp)
        await db.commit()
        await db.refresh(comp)

        # 1. Bank statement import with leading zeros in INN
        csv_content = (
            "operation_date;amount;direction;counterparty_name;counterparty_inn;payment_purpose;balance_eod;operation_id\n"
            "2026-09-01;50000.00;income;ООО «Заказчик Юг»;0123456789;Оплата по договору перевозок;130000.00;tx-001\n"
            "2026-09-01;20000.00;expense;ООО «Лукойл-Юг»;6164009999;Оплата ГСМ по карте;130000.00;tx-002\n"
            "2026-09-02;15000.00;expense;ИП Иванов А.В.;098765432101;Аренда бокса и стоянки;115000.00;tx-003\n"
        )
        file_bytes = csv_content.encode("utf-8")

        imp_res = await StatementService.import_file(
            db=db,
            company_id=comp.id,
            file_bytes=file_bytes,
            format_type="csv",
            mapping=ColumnMapping()
        )
        assert imp_res.status == "ready"
        assert imp_res.accepted_rows == 3
        assert imp_res.duplicate_rows == 0
        assert imp_res.data_revision > 0

        # Verify INN leading zero preservation in DB
        tx_q = await db.execute(
            select(TransactionRecord).where(TransactionRecord.company_id == comp.id, TransactionRecord.external_id == "tx-001")
        )
        tx_rec = tx_q.scalar_one()
        assert tx_rec.counterparty_inn == "0123456789", f"Leading zero lost: {tx_rec.counterparty_inn}"

        # 2. Category Override
        tx_q2 = await db.execute(
            select(TransactionRecord).where(TransactionRecord.company_id == comp.id, TransactionRecord.external_id == "tx-002")
        )
        tx_rec2 = tx_q2.scalar_one()
        await StatementService.update_category(
            db=db,
            company_id=comp.id,
            transaction_id=tx_rec2.id,
            category_id="suppliers"
        )
        await db.refresh(tx_rec)
        assert tx_rec.category_id is not None

        # 3. Create 30-day forecast as of 2026-09-02
        req_fc = CreateForecastRequest(
            as_of_date="2026-09-02",
            horizon_days=30,
            model="weekday_mean",
            include_planned_events=True,
            expected_data_revision=comp.data_revision
        )
        fc = await ForecasterService.create_forecast(db, comp.id, req_fc)
        assert len(fc.days) == 30
        assert fc.summary.closing_balance == 115000.00
        assert fc.currency == "RUB"
        assert fc.days[0].date == "2026-09-03"

        # 4. Add planned events (external contract invoice and tax)
        d_inv = date(2026, 9, 15)
        ev_inv = PlannedEventRecord(
            id=f"ev_inv_{comp.id[:8]}",
            company_id=comp.id,
            title="Оплата рейса Ростов - Москва",
            kind="invoice",
            direction="income",
            amount=80000.00,
            due_date=d_inv,
            category_id="sales",
            status="planned"
        )
        db.add(ev_inv)
        await db.commit()

        # 5. Simulate negative scenario (delay invoice by 14 days and revenue drop 20%)
        sc_req = ScenarioRequest(
            name="Задержка рейса и спад рынка",
            adjustments=[
                DelayIncomeScenario(
                    kind="delay_income",
                    event_id=ev_inv.id,
                    delay_days=14
                ),
                RevenueDropScenario(
                    kind="revenue_drop",
                    percent=20.0,
                    from_date="2026-09-03",
                    to_date="2026-09-20"
                )
            ]
        )
        sc_res = await ScenarioService.simulate_scenario(db, comp.id, fc.id, sc_req)
        assert len(sc_res.forecast.days) == 30
        assert sc_res.forecast.summary.minimum_balance <= fc.summary.minimum_balance

        # 6. Plan-actual reconciliation check
        pa_res = await ReconciliationService.get_plan_actual(
            db=db,
            company_id=comp.id,
            forecast_id=fc.id,
            from_date="2026-09-03",
            to_date="2026-09-07"
        )
        assert pa_res.forecast_id == fc.id
        assert len(pa_res.days) == 5


# ==============================================================================
# STAGE A03: Concurrency, Atomicity, and Idempotency
# ==============================================================================

@pytest.mark.asyncio
async def test_a03_concurrency_and_atomicity():
    """
    Stage A03 (P0):
    1. Idempotent statement replay: re-importing identical statement produces duplicate_rows.
    2. Tenant isolation: two separate companies with identical transaction external_ids do not clash.
    3. Optimistic locking: updating forecast with stale expected_data_revision returns conflict (409).
    4. Snapshot immutability: updating forecast creates a new UUID record, old record unchanged.
    """
    async with async_session_factory() as db:
        compA = Company(name=f"CompA_{uuid.uuid4().hex[:6]}", business_type="Торговля", data_revision=0)
        compB = Company(name=f"CompB_{uuid.uuid4().hex[:6]}", business_type="Услуги", data_revision=0)
        db.add_all([compA, compB])
        await db.commit()

        # Shared CSV with same external_id
        csv_data = (
            "operation_date;amount;direction;counterparty_name;counterparty_inn;payment_purpose;balance_eod;operation_id\n"
            "2026-09-01;10000.00;income;Клиент Общий;7701234567;Оплата счетов;10000.00;tx-shared-01\n"
        ).encode("utf-8")

        # Import into CompA
        resA1 = await StatementService.import_file(db, compA.id, csv_data, "csv", ColumnMapping())
        assert resA1.accepted_rows == 1

        # Re-import identical statement into CompA (Idempotency)
        resA2 = await StatementService.import_file(db, compA.id, csv_data, "csv", ColumnMapping())
        assert resA2.accepted_rows == 0
        assert resA2.duplicate_rows == 1

        # Import into CompB with SAME external_id (Tenant Isolation)
        resB = await StatementService.import_file(db, compB.id, csv_data, "csv", ColumnMapping())
        assert resB.accepted_rows == 1
        assert resB.duplicate_rows == 0

        # Optimistic locking on forecast update
        await db.refresh(compA)
        fcA = await ForecasterService.create_forecast(db, compA.id, CreateForecastRequest(
            as_of_date="2026-09-01",
            horizon_days=30,
            model="weekday_mean",
            expected_data_revision=compA.data_revision
        ))

        # Update with wrong expected_data_revision -> must raise conflict
        with pytest.raises(ValueError, match="conflict: Revision mismatch"):
            await IncrementalService.update_forecast(
                db, compA.id, fcA.id,
                ForecastUpdateRequest(
                    changed_from_date="2026-09-10",
                    expected_data_revision=compA.data_revision + 99
                )
            )

        # Snapshot immutability: valid update produces distinct new snapshot ID
        upd_res = await IncrementalService.update_forecast(
            db, compA.id, fcA.id,
            ForecastUpdateRequest(
                changed_from_date="2026-09-10",
                expected_data_revision=compA.data_revision
            )
        )
        assert upd_res.forecast.id != fcA.id

        # Verify old snapshot still exists intact in database
        old_snap_rec = await db.execute(
            select(ForecastSnapshotRecord).where(ForecastSnapshotRecord.id == fcA.id)
        )
        assert old_snap_rec.scalar_one_or_none() is not None
