import io
import uuid
import pytest
import numpy as np
from datetime import date, timedelta
from sqlalchemy import select
from src.database import async_session_factory
from src.models.entities import Company, DailyActualRecord
from src.schemas.contracts import (
    CreateForecastRequest, EvaluationRequest, ColumnMapping
)
from src.services.forecaster_service import ForecasterService
from src.services.evaluation_service import EvaluationService
from src.services.statement_service import StatementService
from src.services.math.metrics import compute_wape, compute_brier_score
from src.services.math.fpt_solver import wald_gap_probability

# ==============================================================================
# STAGE A05: Model Veracity, Temporal Folds, and Edge Cases
# ==============================================================================

@pytest.mark.asyncio
async def test_a05_negative_initial_balance_immediate_cash_gap():
    """
    Stage A05:
    Edge Case: Company with negative starting balance (overdrawn).
    The mathematical FPT solver and simulation must immediately flag gap_probability = 1.0
    and risk_level = 'critical' on day 1.
    """
    async with async_session_factory() as db:
        comp = Company(
            name=f"ООО «Овердрафт_{uuid.uuid4().hex[:6]}»",
            business_type="Производство",
            data_revision=0
        )
        db.add(comp)
        await db.commit()
        await db.refresh(comp)

        # Populate 60 days of history with negative closing balance
        start_d = date(2026, 7, 1)
        actuals = []
        for i in range(60):
            curr_d = start_d + timedelta(days=i)
            actuals.append(DailyActualRecord(
                company_id=comp.id,
                date=curr_d,
                income=10000.0,
                expense=15000.0,
                closing_balance=-50000.0 - (i * 100.0),
                observation="observed"
            ))
        db.add_all(actuals)
        await db.commit()

        # Generate 30-day forecast
        req = CreateForecastRequest(
            as_of_date="2026-08-29",
            horizon_days=30,
            model="weekday_mean",
            expected_data_revision=comp.data_revision
        )
        fc = await ForecasterService.create_forecast(db, comp.id, req)

        # Verification: Day 1 already in cash gap
        assert fc.summary.risk_level == "critical"
        assert fc.summary.maximum_shortage > 0.0
        assert fc.summary.first_gap_date == fc.days[0].date
        assert fc.days[0].gap_probability == 1.0
        assert len(fc.gaps) > 0
        assert fc.gaps[0].start_date == fc.days[0].date


@pytest.mark.asyncio
async def test_a05_rolling_origin_leakage_free_evaluation():
    """
    Stage A05:
    Leakage-free temporal validation:
    Verify that EvaluationService strictly enforces temporal order:
    For every fold, max(train_date) < min(test_date).
    Future data points must never leak into training set.
    """
    async with async_session_factory() as db:
        comp = Company(
            name=f"ООО «Метрики_{uuid.uuid4().hex[:6]}»",
            business_type="Ритейл",
            data_revision=0
        )
        db.add(comp)
        await db.commit()

        # Seed 90 consecutive days of realistic business actuals
        start_d = date(2026, 6, 1)
        actuals = []
        bal = 200000.0
        for i in range(90):
            curr_d = start_d + timedelta(days=i)
            weekday = curr_d.weekday()
            # Weekday pattern: higher sales Wed-Fri, low Sun
            inc = 40000.0 if weekday in [2, 3, 4] else (15000.0 if weekday == 6 else 25000.0)
            exp = 20000.0 if weekday < 5 else 5000.0
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

        # Run 3-fold rolling origin evaluation with 14-day test horizon
        eval_req = EvaluationRequest(
            training_end_date="2026-08-29",
            test_days=30,
            folds=2,
            models=["seasonal_naive", "weekday_mean", "ridge_calendar"]
        )
        res = await EvaluationService.evaluate_models(db, comp.id, eval_req)

        assert len(res.folds) > 0
        for fold in res.folds:
            # Strict temporal invariant: train_end < test_start <= test_end
            assert fold.train_end < fold.test_start
            assert fold.test_start <= fold.test_end

        # Metrics verification
        assert len(res.metrics) == 3
        for m in res.metrics:
            assert m.wape_cashflow is not None
            assert 0.0 <= m.wape_cashflow <= 1.0, f"WAPE out of bounds: {m.wape_cashflow}"
            assert m.mae_balance >= 0.0
            assert m.gap_brier_score is not None
            assert 0.0 <= m.gap_brier_score <= 1.0


@pytest.mark.asyncio
async def test_a05_sparse_history_and_missing_observations_masking():
    """
    Stage A05:
    Missing observations in bank statements:
    When calendar days have observation='missing' (e.g. gaps between statement imports),
    the evaluation engine must properly mask them out without distorting WAPE/MAE.
    """
    async with async_session_factory() as db:
        comp = Company(
            name=f"ООО «Пропуски_{uuid.uuid4().hex[:6]}»",
            business_type="ИТ-услуги",
            data_revision=0
        )
        db.add(comp)
        await db.commit()

        # 60 days history where every weekend is marked 'missing'
        start_d = date(2026, 7, 1)
        actuals = []
        bal = 300000.0
        for i in range(60):
            curr_d = start_d + timedelta(days=i)
            is_weekend = curr_d.weekday() >= 5
            obs = "missing" if is_weekend else "observed"
            inc = 0.0 if is_weekend else 30000.0
            exp = 0.0 if is_weekend else 18000.0
            if obs == "observed":
                bal += (inc - exp)
            actuals.append(DailyActualRecord(
                company_id=comp.id,
                date=curr_d,
                income=inc if obs == "observed" else 0.0,
                expense=exp if obs == "observed" else 0.0,
                closing_balance=bal,
                observation=obs
            ))
        db.add_all(actuals)
        await db.commit()

        eval_req = EvaluationRequest(
            training_end_date="2026-08-29",
            test_days=30,
            folds=1,
            models=["weekday_mean"]
        )
        res = await EvaluationService.evaluate_models(db, comp.id, eval_req)
        assert len(res.metrics) == 1
        m = res.metrics[0]
        # WAPE must be finite and realistic, unaffected by artificial zero fills
        assert m.wape_cashflow is not None
        assert 0.0 <= m.wape_cashflow < 1.0
