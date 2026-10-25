import uuid
import numpy as np
from datetime import datetime, date, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.entities import (
    Company, ForecastSnapshotRecord, PlannedEventRecord, RecurringPatternRecord
)
from src.schemas.contracts import (
    ForecastUpdateRequest, ForecastUpdateResponse, CreateForecastRequest,
    ForecastSnapshot, ForecastDay, ForecastSummary, CashGap, ForecastWarning
)
from src.services.forecaster_service import ForecasterService, make_cash_gap

class IncrementalService:
    @staticmethod
    async def update_forecast(
        db: AsyncSession,
        company_id: str,
        forecast_id: str,
        req: ForecastUpdateRequest
    ) -> ForecastUpdateResponse:
        comp_res = await db.execute(select(Company).where(Company.id == company_id))
        comp = comp_res.scalar_one_or_none()
        if not comp:
            raise KeyError(f"Company {company_id} not found")

        # Invariant: Revision mismatch must return 409 conflict
        if comp.data_revision != req.expected_data_revision:
            raise ValueError(f"conflict: Revision mismatch. Expected {req.expected_data_revision}, found {comp.data_revision}")

        snap_res = await db.execute(
            select(ForecastSnapshotRecord).where(
                ForecastSnapshotRecord.company_id == company_id,
                ForecastSnapshotRecord.id == forecast_id
            )
        )
        old_snap = snap_res.scalar_one_or_none()
        if not old_snap:
            raise KeyError(f"Forecast {forecast_id} not found")

        changed_d = datetime.strptime(req.changed_from_date, "%Y-%m-%d").date()
        as_of_d = old_snap.as_of_date
        init_bal = float(old_snap.summary["closing_balance"])

        if changed_d <= as_of_d:
            # Full retrain required because changes predate or coincide with as_of_date
            create_req = CreateForecastRequest(
                as_of_date=as_of_d.strftime("%Y-%m-%d"),
                horizon_days=old_snap.horizon_days,
                initial_balance=init_bal,
                include_planned_events=True,
                model=old_snap.model,
                expected_data_revision=comp.data_revision
            )
            new_snapshot = await ForecasterService.create_forecast(db, company_id, create_req)
            return ForecastUpdateResponse(
                forecast=new_snapshot,
                mode="full_retrain",
                recomputed_from_date=req.changed_from_date,
                reason=f"Дата изменения {req.changed_from_date} предшествует дате среза; выполнен полный пересчет."
            )

        # Incremental update: retain head days verbatim before changed_d,
        # recompute tail days with fresh planned events and full bootstrap simulation
        horizon_days = old_snap.horizon_days
        future_dates = [as_of_d + timedelta(days=i + 1) for i in range(horizon_days)]
        date_to_idx = {d.strftime("%Y-%m-%d"): i for i, d in enumerate(future_dates)}
        changed_idx = date_to_idx.get(req.changed_from_date, horizon_days)

        old_days = [ForecastDay(**d) for d in old_snap.days]

        create_req = CreateForecastRequest(
            as_of_date=as_of_d.strftime("%Y-%m-%d"),
            horizon_days=horizon_days,
            initial_balance=init_bal,
            include_planned_events=True,
            model=old_snap.model,
            expected_data_revision=comp.data_revision
        )
        full_snap = await ForecasterService.create_forecast(db, company_id, create_req)

        # Retain head days strictly verbatim from old snapshot
        merged_days: list[ForecastDay] = []
        for i in range(changed_idx):
            merged_days.append(old_days[i])
        for i in range(changed_idx, horizon_days):
            merged_days.append(full_snap.days[i])

        balances = np.array([d.predicted_balance for d in merged_days])
        incomes = np.array([d.predicted_income for d in merged_days])
        expenses = np.array([d.predicted_expense for d in merged_days])

        min_bal = float(np.min(balances))
        min_bal_idx = int(np.argmin(balances))
        min_bal_date = future_dates[min_bal_idx].strftime("%Y-%m-%d")

        # Summary recomputed from merged days and full coherent simulation
        summary = ForecastSummary(
            closing_balance=init_bal,
            end_balance=float(balances[-1]),
            total_income=round(float(np.sum(incomes)), 2),
            total_expense=round(float(np.sum(expenses)), 2),
            minimum_balance=min_bal,
            minimum_balance_date=min_bal_date,
            first_gap_date=full_snap.summary.first_gap_date,
            maximum_shortage=full_snap.summary.maximum_shortage,
            any_gap_probability=full_snap.summary.any_gap_probability,
            risk_level=full_snap.summary.risk_level
        )

        new_snapshot = ForecastSnapshot(
            id=str(uuid.uuid4()),
            company_id=company_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            as_of_date=old_snap.as_of_date.strftime("%Y-%m-%d"),
            horizon_days=horizon_days,
            currency="RUB",
            data_revision=comp.data_revision,
            model=old_snap.model,
            model_version=old_snap.model_version,
            evaluation_id=full_snap.evaluation_id,
            probability_method=full_snap.probability_method,
            interval_coverage=full_snap.interval_coverage,
            simulation_count=full_snap.simulation_count,
            random_seed=full_snap.random_seed,
            summary=summary,
            days=merged_days,
            gaps=full_snap.gaps,
            warnings=full_snap.warnings,
            data_quality=full_snap.data_quality
        )

        # Persist new snapshot immutably
        snap_rec = ForecastSnapshotRecord(
            id=new_snapshot.id,
            company_id=company_id,
            as_of_date=old_snap.as_of_date,
            horizon_days=horizon_days,
            data_revision=comp.data_revision,
            model=old_snap.model,
            model_version=old_snap.model_version,
            evaluation_id=full_snap.evaluation_id,
            probability_method=full_snap.probability_method,
            interval_coverage=full_snap.interval_coverage,
            simulation_count=full_snap.simulation_count,
            random_seed=full_snap.random_seed,
            summary=new_snapshot.summary.model_dump(),
            days=[d.model_dump() for d in new_snapshot.days],
            gaps=[g.model_dump() for g in new_snapshot.gaps],
            warnings=[w.model_dump() for w in new_snapshot.warnings],
            data_quality=new_snapshot.data_quality.model_dump() if new_snapshot.data_quality else None
        )
        db.add(snap_rec)
        await db.commit()

        return ForecastUpdateResponse(
            forecast=new_snapshot,
            mode="incremental",
            recomputed_from_date=req.changed_from_date,
            reason=f"Инкрементальный пересчет хвоста с {req.changed_from_date}: сохранение базиса до даты изменения с обновлением хвоста и честной бутстреп-симуляцией."
        )
