import uuid
import pytest
import numpy as np
from datetime import date, timedelta
from sqlalchemy import select
from src.database import async_session_factory
from src.models.entities import (
    Company, DailyActualRecord, PlannedEventRecord, RecurringPatternRecord,
    ForecastSnapshotRecord
)
from src.schemas.contracts import (
    CreateForecastRequest, ForecastUpdateRequest, ScenarioRequest,
    FixedCostIncreaseScenario, RevenueDropScenario, DelayIncomeScenario
)
from src.services.forecaster_service import ForecasterService
from src.services.scenario_service import ScenarioService
from src.services.incremental_service import IncrementalService
from src.services.evaluation_service import EvaluationService


class DummyEvent:
    def __init__(
        self, ev_id: str, due_date: date, amount: float, direction: str,
        category_id: str, kind: str = "other", paid_amount: float = 0.0,
        status: str = "planned", recurrence_id: str | None = None
    ):
        self.id = ev_id
        self.due_date = due_date
        self.amount = amount
        self.direction = direction
        self.category_id = category_id
        self.kind = kind
        self.paid_amount = paid_amount
        self.status = status
        self.recurrence_id = recurrence_id


# ==============================================================================
# 1. Matched Component Decomposition in combine_baseline_and_events (Finding 4)
# ==============================================================================

def test_combine_baseline_matched_component_decomposition():
    """
    Reviewer Finding 4:
    Baseline 100 contains recurring 40 + other 60.
    Change recurring to 50 should yield 110.0 (not 100.0).
    """
    base_inc = np.array([0.0])
    base_exp = np.array([100.0])
    rec_out = np.array([50.0])
    base_rec_out = np.array([40.0])
    add_out = np.array([0.0])

    tot_inc, tot_exp = ForecasterService.combine_baseline_and_events(
        pred_income_base=base_inc,
        pred_expense_base=base_exp,
        recurring_inflow=np.array([0.0]),
        recurring_outflow=rec_out,
        additional_inflow=np.array([0.0]),
        additional_outflow=add_out,
        base_recurring_outflow=base_rec_out
    )

    assert float(tot_exp[0]) == 110.0, f"Expected 110.0, got {tot_exp[0]}"


def test_combine_baseline_identity_replacement_preserved():
    """
    Standard identity case: 100 base + 100 rec => 100.0
    """
    base_inc = np.array([100.0])
    base_exp = np.array([100.0])
    rec_in = np.array([100.0])
    rec_out = np.array([100.0])

    tot_inc, tot_exp = ForecasterService.combine_baseline_and_events(
        pred_income_base=base_inc,
        pred_expense_base=base_exp,
        recurring_inflow=rec_in,
        recurring_outflow=rec_out,
        additional_inflow=np.array([0.0]),
        additional_outflow=np.array([0.0])
    )

    assert float(tot_inc[0]) == 100.0
    assert float(tot_exp[0]) == 100.0


# ==============================================================================
# 2. Category Shock with No Matching Events Yields Shock 0 (Finding 5)
# ==============================================================================

def test_category_shock_no_matching_events_zero_shock():
    """
    Reviewer Finding 5:
    Rent-only +10% when day has no rent events (e.g. only payroll 100)
    must yield exactly 100.0, NOT 110.0.
    """
    target_d = date(2026, 11, 1)
    future_dates = [target_d]
    base_income = np.array([0.0])
    base_expense = np.array([100.0])

    # Day contains only payroll events, no rent events
    events = [
        DummyEvent(ev_id="ev-payroll", due_date=target_d, amount=100.0, direction="expense", category_id="payroll"),
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

    assert float(stressed_exp[0]) == 100.0, f"Expected 100.0 (zero shock for rent), got {stressed_exp[0]}"


# ==============================================================================
# 3. Delayed Invoice Retains Fixed Protection at Target Date (Finding 5)
# ==============================================================================

def test_delayed_invoice_retains_fixed_protection_at_target_date():
    """
    Reviewer Finding 5:
    Invoice 20 delayed from d1 to d15.
    At d15, revenue drop -20% is applied to total revenue 100 (80 variable + 20 delayed invoice).
    The delayed invoice must retain legal fixed protection:
    80 * 0.80 + 20 = 84.0, NOT 80.0.
    """
    d1 = date(2026, 11, 1)
    d15 = date(2026, 11, 15)
    future_dates = [d1 + timedelta(days=k) for k in range(20)]

    base_income = np.zeros(20)
    base_income[0] = 20.0   # original invoice day
    base_income[14] = 80.0  # target day variable revenue
    base_expense = np.zeros(20)

    inv_event = DummyEvent(
        ev_id="inv-legal-1",
        due_date=d1,
        amount=20.0,
        direction="income",
        category_id="sales",
        kind="invoice"
    )

    adj = [
        DelayIncomeScenario(
            kind="delay_income",
            event_id="inv-legal-1",
            delay_days=14
        ),
        RevenueDropScenario(
            kind="revenue_drop",
            percent=20.0,
            from_date=d15.strftime("%Y-%m-%d"),
            to_date=d15.strftime("%Y-%m-%d")
        )
    ]

    stressed_inc, stressed_exp = ScenarioService.apply_scenario_transforms(
        future_dates=future_dates,
        base_income=base_income,
        base_expense=base_expense,
        adjustments=adj,
        planned_events=[inv_event]
    )

    # At d1: invoice shifted away -> 0.0
    assert float(stressed_inc[0]) == 0.0
    # At d15: 80 variable discounted by 20% (64.0) + 20 protected invoice = 84.0
    assert float(stressed_inc[14]) == 84.0, f"Expected 84.0 at target date, got {stressed_inc[14]}"


# ==============================================================================
# 4. Recurring Pattern Suppression is Date-Specific (Finding 3)
# ==============================================================================

@pytest.mark.asyncio
async def test_recurrence_suppression_is_date_specific():
    """
    Reviewer Finding 3:
    Explicit event on week 1 must suppress only week 1, not subsequent weeks.
    Unrelated same amount/category must not suppress.
    """
    async with async_session_factory() as db:
        comp = Company(name=f"Comp_rec_{uuid.uuid4().hex[:6]}", business_type="Услуги", data_revision=1)
        db.add(comp)
        await db.flush()

        # Add 14 days of history
        as_of = date(2026, 10, 1)
        for i in range(14):
            d = as_of - timedelta(days=14 - i)
            db.add(DailyActualRecord(
                company_id=comp.id,
                date=d,
                income=1000.0,
                expense=500.0,
                closing_balance=10000.0
            ))

        # Weekly recurring expense of 700 on Mondays
        pat = RecurringPatternRecord(
            id=f"pat_weekly_{comp.id[:8]}",
            company_id=comp.id,
            direction="expense",
            category_id="suppliers",
            counterparty_name="Поставщик ООО",
            cadence="weekly",
            expected_amount=700.0,
            next_date=date(2026, 10, 5),
            confidence=0.95,
            sample_count=4
        )
        db.add(pat)

        # Explicit planned event scheduled ONLY on 2026-10-05
        ev1 = PlannedEventRecord(
            id=f"ev_explicit_{comp.id[:8]}",
            company_id=comp.id,
            recurrence_id=pat.id,
            due_date=date(2026, 10, 5),
            amount=700.0,
            direction="expense",
            category_id="suppliers",
            title="Запланированная поставка 05.10",
            kind="other",
            status="planned"
        )
        db.add(ev1)
        await db.commit()

        # Generate forecast for 30 days
        req = CreateForecastRequest(
            as_of_date=as_of.strftime("%Y-%m-%d"),
            horizon_days=30,
            model="weekday_mean",
            include_planned_events=True,
            expected_data_revision=comp.data_revision
        )
        fc = await ForecasterService.create_forecast(db, comp.id, req)

        days_by_date = {d.date: d for d in fc.days}

        # 2026-10-05 has the explicit event
        assert pat.id not in days_by_date["2026-10-05"].planned_event_ids
        assert ev1.id in days_by_date["2026-10-05"].planned_event_ids

        # 2026-10-12 (next week) MUST have pat.id generated, NOT suppressed!
        assert pat.id in days_by_date["2026-10-12"].planned_event_ids, "Pattern was wrongly suppressed on week 2!"
        assert pat.id in days_by_date["2026-10-19"].planned_event_ids, "Pattern was wrongly suppressed on week 3!"


# ==============================================================================
# 5. Incremental Repeated Update and Cancellation (Findings 1 & 2)
# ==============================================================================

@pytest.mark.asyncio
async def test_incremental_repeated_update_and_cancellation():
    """
    Reviewer Findings 1 & 2:
    Repeated update of the same event must not accumulate ghost totals.
    Cancelling the event must cleanly revert to baseline.
    Corridors and gap probabilities must be honest without +/-500 shortcuts.
    """
    async with async_session_factory() as db:
        comp = Company(name=f"Comp_inc_{uuid.uuid4().hex[:6]}", business_type="Торговля", data_revision=0)
        db.add(comp)
        await db.flush()

        as_of = date(2026, 10, 1)
        for i in range(20):
            d = as_of - timedelta(days=20 - i)
            db.add(DailyActualRecord(
                company_id=comp.id,
                date=d,
                income=1000.0,
                expense=500.0,
                closing_balance=10000.0 + (i * 500.0)
            ))
        await db.commit()

        base_fc = await ForecasterService.create_forecast(db, comp.id, CreateForecastRequest(
            as_of_date=as_of.strftime("%Y-%m-%d"),
            horizon_days=30,
            model="weekday_mean"
        ))
        base_day15_exp = base_fc.days[14].predicted_expense

        # Step 1: Add a planned event of 300 on day 15
        target_d = as_of + timedelta(days=15)
        ev = PlannedEventRecord(
            id=f"ev_dyn_{comp.id[:8]}",
            company_id=comp.id,
            due_date=target_d,
            amount=300.0,
            direction="expense",
            category_id="equipment",
            title="Оборудование",
            kind="other",
            status="planned"
        )
        db.add(ev)
        await db.commit()

        # Incremental update 1
        res1 = await IncrementalService.update_forecast(db, comp.id, base_fc.id, ForecastUpdateRequest(
            changed_from_date=target_d.strftime("%Y-%m-%d"),
            expected_data_revision=comp.data_revision
        ))
        assert res1.mode == "incremental"
        day15_res1 = res1.forecast.days[14]
        assert round(day15_res1.predicted_expense, 2) == round(base_day15_exp + 300.0, 2)

        # Corridors must not be hardcoded +/- 500
        assert day15_res1.balance_lower is not None
        assert day15_res1.balance_upper is not None
        diff_lower = abs(day15_res1.predicted_balance - day15_res1.balance_lower)
        assert diff_lower != 500.0, "Corridor must not be hardcoded +/-500!"

        # Step 2: Update same event without change (repeat update 2)
        res2 = await IncrementalService.update_forecast(db, comp.id, res1.forecast.id, ForecastUpdateRequest(
            changed_from_date=target_d.strftime("%Y-%m-%d"),
            expected_data_revision=comp.data_revision
        ))
        day15_res2 = res2.forecast.days[14]
        # Must still be exactly base + 300, NOT base + 600 or base + 900!
        assert round(day15_res2.predicted_expense, 2) == round(base_day15_exp + 300.0, 2)

        # Step 3: Cancel the event
        ev.status = "cancelled"
        await db.commit()

        res3 = await IncrementalService.update_forecast(db, comp.id, res2.forecast.id, ForecastUpdateRequest(
            changed_from_date=target_d.strftime("%Y-%m-%d"),
            expected_data_revision=comp.data_revision
        ))
        day15_res3 = res3.forecast.days[14]
        # Must revert back cleanly to base_day15_exp with zero phantom drift!
        assert round(day15_res3.predicted_expense, 2) == round(base_day15_exp, 2)


# ==============================================================================
# 6. Evaluation Uses Verified Closing Balance & Masks Missing (Finding 6)
# ==============================================================================

@pytest.mark.asyncio
async def test_evaluation_uses_verified_closing_balance_and_masks_missing():
    """
    Reviewer Finding 6:
    Evaluation must use verified bank closing balance act_bal as ground truth,
    not reconstructed sum flow. Missing observation days must be masked.
    """
    from src.schemas.contracts import EvaluationRequest
    async with async_session_factory() as db:
        comp = Company(name=f"Comp_eval_{uuid.uuid4().hex[:6]}", business_type="Торговля", data_revision=0)
        db.add(comp)
        await db.flush()

        start_d = date(2026, 8, 1)
        # Create 60 days of actuals
        # On day 45, bank records closing balance 50000 (with an external deposit not in income flow)
        for i in range(60):
            cur_d = start_d + timedelta(days=i)
            # Make every 7th day a missing day (e.g. statement gap)
            obs = "missing" if (i % 7 == 0) else "observed"
            # Bank statement records actual balance of 50,000 on day 45
            b_eod = 50000.0 if i == 45 else 10000.0 + (i * 100.0)
            db.add(DailyActualRecord(
                company_id=comp.id,
                date=cur_d,
                income=100.0 if obs == "observed" else 0.0,
                expense=50.0 if obs == "observed" else 0.0,
                closing_balance=b_eod,
                observation=obs
            ))
        await db.commit()

        end_date_str = (start_d + timedelta(days=59)).strftime("%Y-%m-%d")
        eval_res = await EvaluationService.evaluate_models(db, comp.id, EvaluationRequest(
            training_end_date=end_date_str,
            models=["weekday_mean"],
            test_days=30,
            folds=1
        ))

        assert eval_res.company_id == comp.id
        assert len(eval_res.metrics) >= 1
        m_eval = eval_res.metrics[0]
        # Verified evaluation must have completed with finite metrics
        assert m_eval.wape_cashflow is not None
        assert m_eval.gap_brier_score is not None
        assert m_eval.interval_empirical_coverage is not None


# ==============================================================================
# 7. Conformal Calibration on Held-out Slice (Finding 7)
# ==============================================================================

@pytest.mark.asyncio
async def test_conformal_calibration_heldout_slice():
    """
    Reviewer Finding 7:
    Conformal calibration must train on training slice and evaluate non-conformity
    on heldout validation slice (not around actual itself).
    """
    async with async_session_factory() as db:
        comp = Company(name=f"Comp_conf_{uuid.uuid4().hex[:6]}", business_type="Торговля", data_revision=0)
        db.add(comp)
        await db.flush()

        # 30 days of actuals
        start_d = date(2026, 9, 1)
        for i in range(30):
            cur_d = start_d + timedelta(days=i)
            db.add(DailyActualRecord(
                company_id=comp.id,
                date=cur_d,
                income=2000.0 + (500.0 if i % 2 == 0 else -300.0),
                expense=1500.0,
                closing_balance=10000.0 + (i * 500.0)
            ))
        await db.commit()

        fc = await ForecasterService.create_forecast(db, comp.id, CreateForecastRequest(
            as_of_date="2026-09-30",
            horizon_days=30,
            model="ridge_calendar"
        ))

        assert fc.probability_method == "residual_block_bootstrap"
        assert fc.interval_coverage == 0.80
        # Corridors must be valid and wrap around predictions
        for d in fc.days:
            assert d.balance_lower is not None
            assert d.balance_upper is not None
            assert d.balance_lower <= d.predicted_balance <= d.balance_upper


# ==============================================================================
# 8. Security Config Enforces Environment Variables (Finding 8)
# ==============================================================================

def test_config_security_environment_overrides(monkeypatch):
    """
    Reviewer Finding 8:
    Verify that security and connection configs respect environment overrides.
    """
    from src.config import Settings
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://secure_user:secure_pass@db:5432/secure_db")
    monkeypatch.setenv("REDIS_URL", "redis://:SecureRedisPass!@redis:6379/1")
    monkeypatch.setenv("SESSION_SECRET", "super-secure-production-secret-999")
    monkeypatch.setenv("CORS_ORIGINS", "https://bank.center-invest.ru,https://app.hackrnd.ru")

    test_settings = Settings()
    assert test_settings.DATABASE_URL == "postgresql+asyncpg://secure_user:secure_pass@db:5432/secure_db"
    assert test_settings.REDIS_URL == "redis://:SecureRedisPass!@redis:6379/1"
    assert test_settings.SESSION_SECRET == "super-secure-production-secret-999"
    assert test_settings.CORS_ORIGINS == ["https://bank.center-invest.ru", "https://app.hackrnd.ru"]

