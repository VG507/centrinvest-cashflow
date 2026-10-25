import uuid
import pytest
import numpy as np
from datetime import date, timedelta
from sqlalchemy import select
from src.database import async_session_factory
from src.models.entities import (
    Company, DailyActualRecord, PlannedEventRecord, RecurringPatternRecord,
    ForecastSnapshotRecord, IntegrationRecord, TransactionRecord
)
from src.schemas.contracts import (
    CreateForecastRequest, ForecastUpdateRequest, ScenarioRequest,
    DelayIncomeScenario, RevenueDropScenario, FixedCostIncreaseScenario, ExtraExpenseScenario
)
from src.services.forecaster_service import ForecasterService
from src.services.scenario_service import ScenarioService
from src.services.incremental_service import IncrementalService
from src.services.integration_service import IntegrationService
from src.services.statement_service import StatementService


class DummyEvent:
    def __init__(self, ev_id: str, due_date: date, amount: float, direction: str, category_id: str, kind: str = "other", paid_amount: float = 0.0):
        self.id = ev_id
        self.due_date = due_date
        self.amount = amount
        self.direction = direction
        self.category_id = category_id
        self.kind = kind
        self.paid_amount = paid_amount


# ==============================================================================
# CASE 3: Selected Category Shock & Revenue Drop Component Protection
# ==============================================================================

def test_selected_category_shock_rent40_payroll60_rent10():
    """
    Reviewer Acceptance Case 3:
    Projected expenses 100 containing rent 40 / payroll 60;
    rent +10% must yield exactly 104.0, not 110.0.
    """
    target_d = date(2026, 11, 1)
    future_dates = [target_d]
    base_income = np.array([0.0])
    base_expense = np.array([100.0])

    events = [
        DummyEvent(ev_id="ev-rent", due_date=target_d, amount=40.0, direction="expense", category_id="rent"),
        DummyEvent(ev_id="ev-payroll", due_date=target_d, amount=60.0, direction="expense", category_id="payroll"),
    ]

    adj = [
        FixedCostIncreaseScenario(
            kind="fixed_cost_increase",
            percent=10.0,
            category_ids=["rent"],
            from_date=target_d.strftime("%Y-%m-%d"),
            to_date=target_d.strftime("%Y-%m-%d")
        )
    ]

    stressed_inc, stressed_exp = ScenarioService.apply_scenario_transforms(
        future_dates=future_dates,
        base_income=base_income,
        base_expense=base_expense,
        adjustments=adj,
        planned_events=events
    )

    assert float(stressed_exp[0]) == 104.0, f"Expected 104.0, got {stressed_exp[0]}"


def test_revenue_drop_protects_confirmed_invoice():
    """
    Reviewer Acceptance Case 3:
    Revenue 80 plus fixed confirmed invoice 20;
    revenue -20% must yield exactly 84.0, not 80.0.
    """
    target_d = date(2026, 11, 1)
    future_dates = [target_d]
    base_income = np.array([100.0])
    base_expense = np.array([0.0])

    events = [
        DummyEvent(ev_id="ev-inv", due_date=target_d, amount=20.0, direction="income", category_id="sales", kind="invoice"),
    ]

    adj = [
        RevenueDropScenario(
            kind="revenue_drop",
            percent=20.0,
            from_date=target_d.strftime("%Y-%m-%d"),
            to_date=target_d.strftime("%Y-%m-%d")
        )
    ]

    stressed_inc, stressed_exp = ScenarioService.apply_scenario_transforms(
        future_dates=future_dates,
        base_income=base_income,
        base_expense=base_expense,
        adjustments=adj,
        planned_events=events
    )

    assert float(stressed_inc[0]) == 84.0, f"Expected 84.0, got {stressed_inc[0]}"


# ==============================================================================
# CASE 2: Count-Once Identity Replacement
# ==============================================================================

def test_count_once_pure_combination():
    """
    Reviewer Acceptance Case 2:
    Same recurring component already in baseline then inserted as event:
    Must produce expected_income 100.0 and expected_expense 100.0,
    NOT 200.0 / 150.0.
    """
    pred_inc_base = np.array([100.0])
    pred_exp_base = np.array([100.0])
    rec_inflow = np.array([100.0])
    rec_outflow = np.array([100.0])
    add_inflow = np.array([0.0])
    add_outflow = np.array([0.0])

    tot_inc, tot_exp = ForecasterService.combine_baseline_and_events(
        pred_income_base=pred_inc_base,
        pred_expense_base=pred_exp_base,
        recurring_inflow=rec_inflow,
        recurring_outflow=rec_outflow,
        additional_inflow=add_inflow,
        additional_outflow=add_outflow
    )

    assert float(tot_inc[0]) == 100.0, f"Expected income 100.0, got {tot_inc[0]}"
    assert float(tot_exp[0]) == 100.0, f"Expected expense 100.0, got {tot_exp[0]}"


def test_count_once_additional_event_adds_correctly():
    """
    A separate genuinely additional 100 expense must still add 100.
    """
    pred_inc_base = np.array([100.0])
    pred_exp_base = np.array([100.0])
    rec_inflow = np.array([100.0])
    rec_outflow = np.array([100.0])
    add_inflow = np.array([0.0])
    add_outflow = np.array([100.0])  # genuine additional expense

    tot_inc, tot_exp = ForecasterService.combine_baseline_and_events(
        pred_income_base=pred_inc_base,
        pred_expense_base=pred_exp_base,
        recurring_inflow=rec_inflow,
        recurring_outflow=rec_outflow,
        additional_inflow=add_inflow,
        additional_outflow=add_outflow
    )

    assert float(tot_inc[0]) == 100.0
    assert float(tot_exp[0]) == 200.0, f"Expected expense 200.0, got {tot_exp[0]}"


# ==============================================================================
# CASE 1: Connector Isolation & Unconfigured Rejection
# ==============================================================================

@pytest.mark.asyncio
async def test_unconfigured_connector_cannot_become_connected():
    """
    Reviewer Acceptance Case 1:
    Unconfigured source cannot become connected or claim provider sync.
    Demo sync retains truthful status as not_configured.
    """
    async with async_session_factory() as db:
        comp = Company(name=f"Comp_{uuid.uuid4().hex[:6]}", business_type="Торговля", data_revision=0)
        db.add(comp)
        await db.flush()

        int_rec = IntegrationRecord(
            id=f"int_test_unconf_{comp.id[:8]}",
            company_id=comp.id,
            kind="bank",
            name="DirectBank Test",
            status="not_configured",
            supported_entities=["transactions"]
        )
        db.add(int_rec)
        await db.commit()

        res = await IntegrationService.sync_integration(db, comp.id, int_rec.id)

        # Status must remain not_configured
        await db.refresh(int_rec)
        assert int_rec.status == "not_configured"
        assert res.data_revision == 0


@pytest.mark.asyncio
async def test_configured_sandbox_sync_does_not_bump_data_revision():
    """
    Reviewer Acceptance Case 1:
    Sandbox demo sync cannot alter confirmed daily actuals or data_revision.
    Replay must be idempotent.
    """
    async with async_session_factory() as db:
        comp = Company(name=f"Comp_{uuid.uuid4().hex[:6]}", business_type="Торговля", data_revision=5)
        db.add(comp)
        await db.flush()
        orig_revision = comp.data_revision

        int_rec = IntegrationRecord(
            id=f"int_test_conf_{comp.id[:8]}",
            company_id=comp.id,
            kind="accounting",
            name="1C Test Connected",
            status="connected",
            supported_entities=["transactions"]
        )
        db.add(int_rec)
        await db.commit()

        # First sync
        res1 = await IntegrationService.sync_integration(db, comp.id, int_rec.id)
        assert res1.imported_count == 3
        assert res1.data_revision == orig_revision

        await db.refresh(comp)
        assert comp.data_revision == orig_revision

        # Second sync (idempotent replay)
        res2 = await IntegrationService.sync_integration(db, comp.id, int_rec.id)
        assert res2.imported_count == 0
        assert res2.data_revision == orig_revision


# ==============================================================================
# CASE 5: Historical Opening Balance Cutoff
# ==============================================================================

@pytest.mark.asyncio
async def test_cutoff_day1_does_not_use_day3_balance():
    """
    Reviewer Acceptance Case 5:
    With verified balance 100 at day 1 and 200 at later day 3,
    cutoff day 1 must not use 200.
    """
    async with async_session_factory() as db:
        comp = Company(name=f"Comp_{uuid.uuid4().hex[:6]}", business_type="Торговля", data_revision=0)
        db.add(comp)
        await db.flush()

        d1 = date(2026, 10, 1)
        d2 = date(2026, 10, 2)
        d3 = date(2026, 10, 3)

        db.add_all([
            DailyActualRecord(company_id=comp.id, date=d1, income=50.0, expense=0.0, closing_balance=100.0),
            DailyActualRecord(company_id=comp.id, date=d2, income=50.0, expense=0.0, closing_balance=150.0),
            DailyActualRecord(company_id=comp.id, date=d3, income=50.0, expense=0.0, closing_balance=200.0),
        ])
        comp.closing_balance = 200.0
        comp.balance_date = d3
        await db.commit()

        # Forecast as of day 1
        req = CreateForecastRequest(
            as_of_date=d1.strftime("%Y-%m-%d"),
            horizon_days=30,
            model="seasonal_naive"
        )

        forecast = await ForecasterService.create_forecast(db, comp.id, req)
        assert forecast.summary.closing_balance == 100.0, f"Expected cutoff opening balance 100.0, got {forecast.summary.closing_balance}"


# ==============================================================================
# CASE 8: Incremental vs Full Retrain Mode
# ==============================================================================

@pytest.mark.asyncio
async def test_incremental_mode_separation():
    """
    Reviewer Acceptance Case 8:
    changed_from_date > as_of_date => incremental
    changed_from_date <= as_of_date => full_retrain
    Revision mismatch => 409 conflict
    """
    async with async_session_factory() as db:
        comp = Company(name=f"Comp_{uuid.uuid4().hex[:6]}", business_type="Торговля", data_revision=2)
        db.add(comp)
        await db.flush()

        as_of = date(2026, 10, 1)
        db.add(DailyActualRecord(
            company_id=comp.id,
            date=as_of,
            income=1000.0,
            expense=500.0,
            closing_balance=10000.0
        ))
        await db.commit()

        base_f = await ForecasterService.create_forecast(db, comp.id, CreateForecastRequest(
            as_of_date=as_of.strftime("%Y-%m-%d"),
            horizon_days=30,
            model="seasonal_naive",
            expected_data_revision=comp.data_revision
        ))

        # 1. Incremental tail update
        inc_req = ForecastUpdateRequest(
            changed_from_date="2026-10-15",
            expected_data_revision=comp.data_revision
        )
        inc_res = await IncrementalService.update_forecast(db, comp.id, base_f.id, inc_req)
        assert inc_res.mode == "incremental"

        # 2. Full retrain update (date <= as_of_date)
        retrain_req = ForecastUpdateRequest(
            changed_from_date="2026-10-01",
            expected_data_revision=comp.data_revision
        )
        retrain_res = await IncrementalService.update_forecast(db, comp.id, base_f.id, retrain_req)
        assert retrain_res.mode == "full_retrain"

        # 3. Revision mismatch
        conflict_req = ForecastUpdateRequest(
            changed_from_date="2026-10-15",
            expected_data_revision=999
        )
        with pytest.raises(ValueError, match="conflict: Revision mismatch"):
            await IncrementalService.update_forecast(db, comp.id, base_f.id, conflict_req)
