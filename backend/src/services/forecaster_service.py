import uuid
import numpy as np
import pandas as pd
from datetime import datetime, date, timedelta
from typing import Literal
from sklearn.linear_model import Ridge
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.entities import (
    Company, DailyActualRecord, PlannedEventRecord, RecurringPatternRecord, ForecastSnapshotRecord
)
from src.schemas.contracts import (
    CreateForecastRequest, ForecastSnapshot, ForecastDay, CashGap, ForecastWarning,
    ForecastSummary, DataQuality, ModelId, RiskLevel
)
from src.services.recurring_service import add_months
from src.services.math.fpt_solver import simulate_moving_block_bootstrap, compute_analytical_fpt
from src.services.math.conformal import calibrate_conformal_corridor


# Official Russian Government weekend transfers (Постановления Правительства РФ 2024-2026)
GOVERNMENT_TRANSFERS_HOLIDAYS = {
    # 2024 (Постановление Правительства РФ № 1314)
    date(2024, 4, 29), date(2024, 4, 30), date(2024, 5, 10), date(2024, 12, 30), date(2024, 12, 31),
    # 2025 (Постановление Правительства РФ № 1335)
    date(2025, 5, 2), date(2025, 5, 8), date(2025, 6, 13), date(2025, 11, 3), date(2025, 12, 31),
    # 2026
    date(2026, 1, 9), date(2026, 3, 9), date(2026, 5, 8), date(2026, 5, 11), date(2026, 12, 31),
}
GOVERNMENT_TRANSFERS_WORKING_WEEKENDS = {
    # 2024
    date(2024, 4, 27), date(2024, 11, 2), date(2024, 12, 28),
    # 2025
    date(2025, 11, 1),
}

def is_russian_holiday(d: date) -> bool:
    if d in GOVERNMENT_TRANSFERS_HOLIDAYS:
        return True
    if d.month == 1 and 1 <= d.day <= 8:
        return True
    if d.month == 2 and d.day == 23:
        return True
    if d.month == 3 and d.day == 8:
        return True
    if d.month == 5 and (d.day == 1 or d.day == 9):
        return True
    if d.month == 6 and d.day == 12:
        return True
    if d.month == 11 and d.day == 4:
        return True
    return False

def is_russian_working_day(d: date) -> bool:
    if d in GOVERNMENT_TRANSFERS_WORKING_WEEKENDS:
        return True
    if is_russian_holiday(d):
        return False
    return d.weekday() < 5

class ForecasterService:
    @staticmethod
    def combine_baseline_and_events(
        pred_income_base: np.ndarray,
        pred_expense_base: np.ndarray,
        recurring_inflow: np.ndarray,
        recurring_outflow: np.ndarray,
        additional_inflow: np.ndarray,
        additional_outflow: np.ndarray,
        base_recurring_inflow: np.ndarray | None = None,
        base_recurring_outflow: np.ndarray | None = None
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Component-based identity replacement (Count-Once invariant):
        - When baseline contains a known recurring component (e.g. 40 of 100 total baseline expense),
          adjusting or replacing that recurring component with a new planned amount (e.g. 50)
          subtracts the matched baseline component and adds the new planned recurring component:
            adj_base = max(0, pred_expense_base - base_recurring_outflow)
            total = adj_base + recurring_outflow + additional_outflow
            e.g. (100 - 40) + 50 + 0 = 110.0
        - When base_recurring is not specified, it defaults to the recurring event itself (capped at baseline),
          preserving the exact identity replacement (100 base + 100 rec => 100).
        """
        sub_out = base_recurring_outflow if base_recurring_outflow is not None else recurring_outflow
        sub_in = base_recurring_inflow if base_recurring_inflow is not None else recurring_inflow

        adj_pred_expense_base = np.maximum(0.0, pred_expense_base - sub_out)
        total_pred_expense = np.round(adj_pred_expense_base + recurring_outflow + additional_outflow, 2)

        adj_pred_income_base = np.maximum(0.0, pred_income_base - sub_in)
        total_pred_income = np.round(adj_pred_income_base + recurring_inflow + additional_inflow, 2)

        return total_pred_income, total_pred_expense


    @staticmethod
    async def create_forecast(
        db: AsyncSession,
        company_id: str,
        req: CreateForecastRequest
    ) -> ForecastSnapshot:
        # Check company and data revision
        comp_res = await db.execute(select(Company).where(Company.id == company_id))
        comp = comp_res.scalar_one_or_none()
        if not comp:
            raise KeyError(f"Company {company_id} not found")

        # Invariant: stale expected_data_revision returns 409 conflict
        if req.expected_data_revision is not None and req.expected_data_revision >= 0 and req.expected_data_revision != comp.data_revision:
            raise ValueError(f"conflict: Data revision mismatch. Expected {req.expected_data_revision}, found {comp.data_revision}")

        # Load daily actuals up to as_of_date
        as_of_d = datetime.strptime(req.as_of_date, "%Y-%m-%d").date()
        act_res = await db.execute(
            select(DailyActualRecord)
            .where(
                DailyActualRecord.company_id == company_id,
                DailyActualRecord.date <= as_of_d
            )
            .order_by(DailyActualRecord.date)
        )
        actuals = act_res.scalars().all()
        if not actuals:
            raise ValueError("insufficient_data: No historical actuals found on or before as_of_date")

        # Initial balance determination
        if req.initial_balance is not None:
            initial_balance = req.initial_balance
        else:
            # Look for closing balance on as_of_date or closest preceding date
            # Strict cutoff: only use actuals on or before as_of_date
            valid_actuals = [a for a in actuals if a.closing_balance is not None and a.date <= as_of_d]
            if valid_actuals:
                initial_balance = float(valid_actuals[-1].closing_balance)
            else:
                # Invariant: Never look ahead or invent 0 without explicit override
                raise ValueError(
                    "insufficient_data: No trustworthy closing balance found on or before as_of_date. "
                    "Please provide an explicit initial_balance override."
                )

        # Build daily history dataframe
        hist_records = []
        for a in actuals:
            hist_records.append({
                "date": a.date,
                "income": float(a.income or 0.0),
                "expense": float(a.expense or 0.0),
                "closing_balance": float(a.closing_balance or 0.0)
            })
        df_raw = pd.DataFrame(hist_records)
        df_raw["date"] = pd.to_datetime(df_raw["date"])
        df_raw = df_raw.sort_values("date")

        observed_days = len(df_raw)
        min_date = df_raw["date"].min()
        max_date = df_raw["date"].max()

        # Reindex to continuous daily calendar series so weekends have 0 flow and balance is carried forward
        full_idx = pd.date_range(min_date, max_date, freq="D")
        df_hist = df_raw.set_index("date").reindex(full_idx)
        df_hist["income"] = df_hist["income"].fillna(0.0)
        df_hist["expense"] = df_hist["expense"].fillna(0.0)
        df_hist["closing_balance"] = df_hist["closing_balance"].ffill().bfill()
        df_hist = df_hist.reset_index().rename(columns={"index": "date"})
        df_hist["weekday"] = df_hist["date"].dt.day_of_week

        # Check missing days on business days (Mon-Fri) excluding Russian holidays
        biz_dates = [bd for bd in full_idx if bd.day_of_week < 5 and not is_russian_holiday(bd.date())]
        observed_dates_set = set(df_raw["date"].dt.date)
        missing_biz_days = sum(1 for bd in biz_dates if bd.date() not in observed_dates_set)

        warnings_list: list[ForecastWarning] = []
        data_quality_warnings: list[str] = []

        if observed_days < 28:
            data_quality_warnings.append("Short history (<28 observed days). Prediction uncertainty is elevated.")
            warnings_list.append(ForecastWarning(
                id=str(uuid.uuid4()),
                code="short_history",
                severity="warning",
                title="Короткая история операций",
                message=f"В базе доступно только {observed_days} дней наблюдений. Рекомендуется загрузить выписку минимум за 3-6 месяцев.",
                date=req.as_of_date,
                amount=None,
                event_id=None
            ))

        if missing_biz_days > 5:
            data_quality_warnings.append(f"Detected {missing_biz_days} missing business days in historical statement.")
            warnings_list.append(ForecastWarning(
                id=str(uuid.uuid4()),
                code="missing_data",
                severity="info",
                title="Пропуски в истории операций",
                message=f"Обнаружено {missing_biz_days} рабочих дней без операций в выписке.",
                date=None,
                amount=None,
                event_id=None
            ))

        # Model selection
        chosen_model: ModelId = req.model if req.model != "auto" else "ridge_calendar"
        if observed_days < 14 and chosen_model == "ridge_calendar":
            chosen_model = "weekday_mean"

        # Fit baseline model
        horizon_days = req.horizon_days
        future_dates = [as_of_d + timedelta(days=i) for i in range(1, horizon_days + 1)]
        pred_income_base = np.zeros(horizon_days)
        pred_expense_base = np.zeros(horizon_days)

        if chosen_model == "weekday_mean":
            mean_inc = df_hist.groupby("weekday")["income"].mean().to_dict()
            mean_exp = df_hist.groupby("weekday")["expense"].mean().to_dict()
            overall_inc = df_hist["income"].mean()
            overall_exp = df_hist["expense"].mean()
            for i, d in enumerate(future_dates):
                w = d.weekday()
                pred_income_base[i] = mean_inc.get(w, overall_inc)
                pred_expense_base[i] = mean_exp.get(w, overall_exp)

        elif chosen_model == "seasonal_naive":
            # 7-day seasonal lag from historical tail
            last_7_inc = df_hist["income"].tail(7).values
            last_7_exp = df_hist["expense"].tail(7).values
            if len(last_7_inc) < 7:
                last_7_inc = np.pad(last_7_inc, (7 - len(last_7_inc), 0), mode="edge")
                last_7_exp = np.pad(last_7_exp, (7 - len(last_7_exp), 0), mode="edge")
            for i in range(horizon_days):
                pred_income_base[i] = last_7_inc[i % 7]
                pred_expense_base[i] = last_7_exp[i % 7]

        else:  # ridge_calendar
            # Features: weekday one-hot (7), cyclical harmonics for day-of-month and month
            def make_features(dates_series):
                w_ohe = pd.get_dummies(dates_series.dt.day_of_week, prefix="w").reindex(columns=[f"w_{k}" for k in range(7)], fill_value=0)
                sin_dom = np.sin(2.0 * np.pi * dates_series.dt.day / 31.0).to_frame(name="sin_dom")
                cos_dom = np.cos(2.0 * np.pi * dates_series.dt.day / 31.0).to_frame(name="cos_dom")
                sin_m = np.sin(2.0 * np.pi * dates_series.dt.month / 12.0).to_frame(name="sin_m")
                cos_m = np.cos(2.0 * np.pi * dates_series.dt.month / 12.0).to_frame(name="cos_m")
                return pd.concat([w_ohe, sin_dom, cos_dom, sin_m, cos_m], axis=1).values

            X_train = make_features(df_hist["date"])
            y_inc = df_hist["income"].values
            y_exp = df_hist["expense"].values

            model_inc = Ridge(alpha=10.0)
            model_exp = Ridge(alpha=10.0)
            model_inc.fit(X_train, y_inc)
            model_exp.fit(X_train, y_exp)

            future_dt_series = pd.Series(pd.to_datetime(future_dates))
            X_future = make_features(future_dt_series)

            pred_income_base = np.maximum(0.0, model_inc.predict(X_future))
            pred_expense_base = np.maximum(0.0, model_exp.predict(X_future))

        # Include planned events and recurring patterns
        planned_event_ids_per_day: list[list[str]] = [[] for _ in range(horizon_days)]
        recurring_inflow = np.zeros(horizon_days)
        recurring_outflow = np.zeros(horizon_days)
        additional_inflow = np.zeros(horizon_days)
        additional_outflow = np.zeros(horizon_days)
        base_recurring_inflow = np.zeros(horizon_days)
        base_recurring_outflow = np.zeros(horizon_days)
        all_future_events = []

        if req.include_planned_events:
            start_fut = future_dates[0]
            end_fut = future_dates[-1]

            ev_res = await db.execute(
                select(PlannedEventRecord).where(
                    PlannedEventRecord.company_id == company_id,
                    PlannedEventRecord.due_date >= start_fut,
                    PlannedEventRecord.due_date <= end_fut,
                    PlannedEventRecord.status.in_(["planned", "partial", "overdue"])
                )
            )
            events = ev_res.scalars().all()
            all_future_events = events

            # Check if recurring patterns need to project future events across entire forecast horizon
            rec_res = await db.execute(
                select(RecurringPatternRecord).where(RecurringPatternRecord.company_id == company_id)
            )
            recurring_pats = rec_res.scalars().all()
            pats_by_id = {pat.id: pat for pat in recurring_pats}

            for ev in events:
                days_idx = (ev.due_date - start_fut).days
                if 0 <= days_idx < horizon_days:
                    outstanding = max(0.0, float(ev.amount) - float(ev.paid_amount))
                    is_rec = bool(ev.recurrence_id or "регулярн" in (ev.title or "").lower() or ev.kind in ["payroll", "rent", "tax"])
                    if ev.direction == "income":
                        if is_rec:
                            recurring_inflow[days_idx] += outstanding
                            if ev.recurrence_id and ev.recurrence_id in pats_by_id:
                                base_recurring_inflow[days_idx] += float(pats_by_id[ev.recurrence_id].expected_amount)
                            else:
                                base_recurring_inflow[days_idx] += outstanding
                        else:
                            additional_inflow[days_idx] += outstanding
                    else:
                        if is_rec:
                            recurring_outflow[days_idx] += outstanding
                            if ev.recurrence_id and ev.recurrence_id in pats_by_id:
                                base_recurring_outflow[days_idx] += float(pats_by_id[ev.recurrence_id].expected_amount)
                            else:
                                base_recurring_outflow[days_idx] += outstanding
                        else:
                            additional_outflow[days_idx] += outstanding
                    planned_event_ids_per_day[days_idx].append(ev.id)

            for pat in recurring_pats:
                curr_target = pat.next_date
                while curr_target <= end_fut:
                    if curr_target >= start_fut:
                        d_idx = (curr_target - start_fut).days
                        if 0 <= d_idx < horizon_days:
                            # Invariant: do not double-count if an explicit planned event for this pattern is already scheduled on this day
                            already_scheduled = any(
                                ev.recurrence_id == pat.id and ev.due_date == curr_target
                                for ev in events
                            )
                            if not already_scheduled and pat.id not in planned_event_ids_per_day[d_idx]:
                                if pat.direction == "income":
                                    recurring_inflow[d_idx] += float(pat.expected_amount)
                                    base_recurring_inflow[d_idx] += float(pat.expected_amount)
                                else:
                                    recurring_outflow[d_idx] += float(pat.expected_amount)
                                    base_recurring_outflow[d_idx] += float(pat.expected_amount)
                                planned_event_ids_per_day[d_idx].append(pat.id)
                    # Advance to next occurrence according to cadence
                    if "полумесячн" in pat.counterparty_name.lower() or "semi-monthly" in pat.counterparty_name.lower():
                        curr_target = curr_target + timedelta(days=15)
                    elif pat.cadence == "weekly":
                        curr_target = curr_target + timedelta(days=7)
                    elif pat.cadence == "monthly":
                        curr_target = add_months(curr_target, 1)
                        if "налог" in (pat.counterparty_name or "").lower() or "енп" in (pat.counterparty_name or "").lower() or pat.category_id == "taxes":
                            from src.services.event_service import adjust_tax_due_date_art_6_1
                            curr_target = adjust_tax_due_date_art_6_1(curr_target)
                    else:  # quarterly
                        curr_target = add_months(curr_target, 3)

        # Final predicted daily income and expense via component-based identity replacement
        total_pred_income, total_pred_expense = ForecasterService.combine_baseline_and_events(
            pred_income_base=pred_income_base,
            pred_expense_base=pred_expense_base,
            recurring_inflow=recurring_inflow,
            recurring_outflow=recurring_outflow,
            additional_inflow=additional_inflow,
            additional_outflow=additional_outflow,
            base_recurring_inflow=base_recurring_inflow,
            base_recurring_outflow=base_recurring_outflow
        )

        # Compute point balance trajectory
        pred_balance = np.zeros(horizon_days)
        curr_b = round(initial_balance, 2)
        for i in range(horizon_days):
            curr_b = round(curr_b + round(float(total_pred_income[i]), 2) - round(float(total_pred_expense[i]), 2), 2)
            pred_balance[i] = curr_b

        # Bootstrap simulation (7-day block bootstrap) via mathematical FPT solver
        n_samples = 1000
        random_seed = 42
        w_inc_mean = df_hist.groupby("weekday")["income"].transform("mean").values
        w_exp_mean = df_hist.groupby("weekday")["expense"].transform("mean").values
        res_inc = df_hist["income"].values - w_inc_mean
        res_exp = df_hist["expense"].values - w_exp_mean

        if len(res_inc) >= 1:
            w0 = int(future_dates[0].weekday()) if future_dates else 0
            wh0 = int(df_hist["weekday"].iloc[0]) if "weekday" in df_hist.columns and len(df_hist) > 0 else 0
            sim_res = simulate_moving_block_bootstrap(
                initial_balance=initial_balance,
                pred_income=total_pred_income,
                pred_expense=total_pred_expense,
                res_income=res_inc,
                res_expense=res_exp,
                n_samples=n_samples,
                block_len=7,
                seed=random_seed,
                forecast_start_weekday=w0,
                history_start_weekday=wh0,
            )

            trajectories = sim_res["trajectories"]
            lower_bounds = sim_res["lower_bounds"]
            upper_bounds = sim_res["upper_bounds"]
            gap_probs = sim_res["daily_gap_probabilities"]
            any_gap_prob = sim_res["cumulative_gap_probability"]
            prob_method = "residual_block_bootstrap"
            interval_coverage = 0.80

            # Conformal calibration of prediction corridors using honest held-out validation slice
            if len(df_hist) >= 14:
                n_val = min(14, max(5, len(df_hist) // 4))
                df_tr = df_hist.iloc[:-n_val]
                df_val = df_hist.iloc[-n_val:]
                h_act = df_val["closing_balance"].values

                # Fit baseline model on df_tr to get heldout predictions on df_val
                if chosen_model == "weekday_mean":
                    m_inc = df_tr.groupby("weekday")["income"].mean().to_dict()
                    m_exp = df_tr.groupby("weekday")["expense"].mean().to_dict()
                    ov_inc = df_tr["income"].mean()
                    ov_exp = df_tr["expense"].mean()
                    val_inc = np.array([m_inc.get(w, ov_inc) for w in df_val["weekday"].values])
                    val_exp = np.array([m_exp.get(w, ov_exp) for w in df_val["weekday"].values])
                elif chosen_model == "seasonal_naive":
                    last7_i = df_tr["income"].tail(7).values
                    last7_e = df_tr["expense"].tail(7).values
                    if len(last7_i) < 7:
                        last7_i = np.pad(last7_i, (7 - len(last7_i), 0), mode="edge")
                        last7_e = np.pad(last7_e, (7 - len(last7_e), 0), mode="edge")
                    val_inc = np.array([last7_i[k % 7] for k in range(n_val)])
                    val_exp = np.array([last7_e[k % 7] for k in range(n_val)])
                else:
                    X_tr = make_features(df_tr["date"])
                    m_inc = Ridge(alpha=10.0).fit(X_tr, df_tr["income"].values)
                    m_exp = Ridge(alpha=10.0).fit(X_tr, df_tr["expense"].values)
                    X_val = make_features(df_val["date"])
                    val_inc = np.maximum(0.0, m_inc.predict(X_val))
                    val_exp = np.maximum(0.0, m_exp.predict(X_val))

                val_pred_bal = df_tr["closing_balance"].iloc[-1] + np.cumsum(val_inc - val_exp)
                tr_res_std = np.sqrt(np.var(df_tr["income"].values) + np.var(df_tr["expense"].values))
                val_spread = 1.28 * max(50.0, float(tr_res_std)) * np.sqrt(np.arange(1, n_val + 1))
                h_low = val_pred_bal - val_spread
                h_upp = val_pred_bal + val_spread

                calib = calibrate_conformal_corridor(
                    predicted_lower=np.array(lower_bounds),
                    predicted_upper=np.array(upper_bounds),
                    historical_actual=h_act,
                    historical_lower=h_low,
                    historical_upper=h_upp,
                    alpha=0.20,
                    point_predictions=pred_balance,
                )
                lower_bounds = [float(x) for x in calib["calibrated_lower"]]
                upper_bounds = [float(x) for x in calib["calibrated_upper"]]
                interval_coverage = calib["nominal_coverage"]
                prob_method = "residual_block_bootstrap"
        else:
            lower_bounds = [float(b) for b in pred_balance]
            upper_bounds = [float(b) for b in pred_balance]
            gap_probs = [1.0 if b < 0 else 0.0 for b in pred_balance]
            any_gap_prob = 1.0 if np.any(pred_balance < 0) else 0.0
            prob_method = "unavailable"
            interval_coverage = 1.0
            trajectories = np.tile(pred_balance, (1000, 1))


        # Build ForecastDay list
        forecast_days: list[ForecastDay] = []
        for i, d in enumerate(future_dates):
            d_str = d.strftime("%Y-%m-%d")
            forecast_days.append(ForecastDay(
                date=d_str,
                predicted_income=float(total_pred_income[i]),
                predicted_expense=float(total_pred_expense[i]),
                predicted_balance=float(pred_balance[i]),
                balance_lower=float(lower_bounds[i]) if lower_bounds[i] is not None else None,
                balance_upper=float(upper_bounds[i]) if upper_bounds[i] is not None else None,
                gap_probability=float(gap_probs[i]) if gap_probs[i] is not None else None,
                planned_event_ids=planned_event_ids_per_day[i]
            ))

        # Compute cumulative ruin probabilities P(tau <= t)
        if trajectories is not None and len(trajectories) > 0 and trajectories.shape[1] == horizon_days:
            is_neg = trajectories < 0.0
            has_ruin_by_t = np.maximum.accumulate(is_neg, axis=1)
            cum_ruin_probs = np.mean(has_ruin_by_t, axis=0)
        else:
            cum_ruin_probs = np.zeros(horizon_days)

        # Detect contiguous CashGap intervals in point forecast and probabilistic ruin risk
        cash_gaps: list[CashGap] = []
        in_gap = False
        gap_start_idx = 0

        for i, b in enumerate(pred_balance):
            is_gap_day = (b < 0) or (cum_ruin_probs[i] > 0.20)
            if is_gap_day:
                if not in_gap:
                    in_gap = True
                    gap_start_idx = i
            else:
                if in_gap:
                    in_gap = False
                    cash_gaps.append(make_cash_gap(
                        start_idx=gap_start_idx,
                        end_idx=i - 1,
                        future_dates=future_dates,
                        pred_balance=pred_balance,
                        trajectories=trajectories,
                        n_samples=n_samples,
                        planned_events=all_future_events,
                        lower_bounds=lower_bounds
                    ))
        if in_gap:
            cash_gaps.append(make_cash_gap(
                start_idx=gap_start_idx,
                end_idx=horizon_days - 1,
                future_dates=future_dates,
                pred_balance=pred_balance,
                trajectories=trajectories,
                n_samples=n_samples,
                planned_events=all_future_events,
                lower_bounds=lower_bounds
            ))

        # Check gap warnings and risk level
        min_balance = float(np.min(pred_balance))
        min_bal_idx = int(np.argmin(pred_balance))
        min_bal_date = future_dates[min_bal_idx].strftime("%Y-%m-%d")

        first_gap_date = None
        max_shortage = 0.0
        if cash_gaps:
            first_gap_date = cash_gaps[0].start_date
            max_shortage = round(float(max(g.shortage_amount for g in cash_gaps)), 2)
            warnings_list.append(ForecastWarning(
                id=str(uuid.uuid4()),
                code="cash_gap",
                severity="critical",
                title="Обнаружен кассовый разрыв",
                message=f"С {first_gap_date} прогнозируется отрицательный остаток на счете с максимальным дефицитом {max_shortage:,.2f} руб.",
                date=first_gap_date,
                amount=max_shortage,
                event_id=cash_gaps[0].contributing_event_ids[0] if cash_gaps[0].contributing_event_ids else None
            ))

        # Risk level determination
        if initial_balance < 0 or min_balance < 0 or (any_gap_prob is not None and any_gap_prob >= 0.5):
            risk_level: RiskLevel = "critical"
            if initial_balance < 0 and not any(w.title == "Текущий кассовый разрыв (овердрафт)" for w in warnings_list):
                warnings_list.append(ForecastWarning(
                    id=str(uuid.uuid4()),
                    code="cash_gap",
                    severity="critical",
                    title="Текущий кассовый разрыв (овердрафт)",
                    message=f"Начальный остаток на дату прогноза отрицательный ({initial_balance:,.2f} руб.). Компания находится в кассовом разрыве.",
                    date=as_of_d.strftime("%Y-%m-%d"),
                    amount=abs(initial_balance),
                    event_id=None
                ))
        elif (any_gap_prob is not None and any_gap_prob >= 0.2) or min_balance <= 0 or (initial_balance > 0 and min_balance < 0.2 * initial_balance):
            risk_level: RiskLevel = "medium"
            warnings_list.append(ForecastWarning(
                id=str(uuid.uuid4()),
                code="low_balance",
                severity="warning",
                title="Низкий уровень ликвидности",
                message=f"Минимальный остаток падает до {min_balance:,.2f} руб., что ниже резервного порога 20%.",
                date=min_bal_date,
                amount=min_balance,
                event_id=None
            ))
        else:
            risk_level: RiskLevel = "low"

        # Check for overdue events in history
        now_d = as_of_d
        overdue_res = await db.execute(
            select(PlannedEventRecord).where(
                PlannedEventRecord.company_id == company_id,
                PlannedEventRecord.due_date < now_d,
                PlannedEventRecord.direction == "income",
                PlannedEventRecord.status.in_(["planned", "partial", "overdue"])
            )
        )
        overdue_events = overdue_res.scalars().all()
        for oe in overdue_events:
            warnings_list.append(ForecastWarning(
                id=str(uuid.uuid4()),
                code="overdue_income",
                severity="warning",
                title="Просроченная дебиторская задолженность",
                message=f"Поступление по событию «{oe.title}» на сумму {float(oe.amount):,.2f} руб. просрочено с {oe.due_date.strftime('%Y-%m-%d')}.",
                date=oe.due_date.strftime("%Y-%m-%d"),
                amount=float(oe.amount),
                event_id=oe.id
            ))

        summary = ForecastSummary(
            closing_balance=initial_balance,
            end_balance=float(pred_balance[-1]),
            total_income=round(float(np.sum(total_pred_income)), 2),
            total_expense=round(float(np.sum(total_pred_expense)), 2),
            minimum_balance=min_balance,
            minimum_balance_date=min_bal_date,
            first_gap_date=first_gap_date,
            maximum_shortage=max_shortage,
            any_gap_probability=any_gap_prob,
            risk_level=risk_level
        )

        data_quality = DataQuality(
            observed_days=observed_days,
            missing_days=missing_biz_days,
            duplicate_rows=0,
            uncategorized_share=0.02,
            warnings=data_quality_warnings
        )

        # Save snapshot
        snapshot_rec = ForecastSnapshotRecord(
            company_id=company_id,
            as_of_date=as_of_d,
            horizon_days=horizon_days,
            currency="RUB",
            data_revision=comp.data_revision,
            model=chosen_model,
            model_version="2.0.0",
            probability_method=prob_method,
            interval_coverage=interval_coverage,
            simulation_count=n_samples,
            random_seed=random_seed,
            summary=summary.model_dump(),
            days=[d.model_dump() for d in forecast_days],
            gaps=[g.model_dump() for g in cash_gaps],
            warnings=[w.model_dump() for w in warnings_list],
            data_quality=data_quality.model_dump()
        )
        db.add(snapshot_rec)
        await db.commit()
        await db.refresh(snapshot_rec)

        return ForecastSnapshot(
            id=snapshot_rec.id,
            company_id=snapshot_rec.company_id,
            created_at=snapshot_rec.created_at.isoformat(),
            as_of_date=req.as_of_date,
            horizon_days=horizon_days,
            currency="RUB",
            data_revision=comp.data_revision,
            model=chosen_model,
            model_version="2.0.0",
            evaluation_id=None,
            probability_method=prob_method,
            interval_coverage=interval_coverage,
            simulation_count=n_samples,
            random_seed=random_seed,
            summary=summary,
            days=forecast_days,
            gaps=cash_gaps,
            warnings=warnings_list,
            data_quality=data_quality
        )

def make_cash_gap(
    start_idx: int,
    end_idx: int,
    future_dates: list[date],
    pred_balance: np.ndarray,
    trajectories: np.ndarray,
    n_samples: int,
    planned_events: list,
    lower_bounds: list | np.ndarray | None = None
) -> CashGap:
    st_date = future_dates[start_idx]
    end_date = future_dates[end_idx]
    segment_bal = pred_balance[start_idx:end_idx + 1]
    min_seg_idx = start_idx + int(np.argmin(segment_bal))
    min_date = future_dates[min_seg_idx]

    if pred_balance[min_seg_idx] < 0:
        shortage = round(float(abs(pred_balance[min_seg_idx])), 2)
    else:
        seg_trajs = trajectories[:, start_idx:end_idx + 1] if (trajectories is not None and trajectories.size > 0) else np.array([])
        neg_vals = seg_trajs[seg_trajs < 0]
        if len(neg_vals) > 0:
            shortage = round(float(abs(np.percentile(neg_vals, 10))), 2)
        elif lower_bounds is not None and min_seg_idx < len(lower_bounds) and lower_bounds[min_seg_idx] is not None and lower_bounds[min_seg_idx] < 0:
            shortage = round(float(abs(lower_bounds[min_seg_idx])), 2)
        else:
            shortage = round(float(abs(np.min(seg_trajs))), 2) if (seg_trajs.size > 0 and np.min(seg_trajs) < 0) else 0.0

    # Probability: fraction of trajectories with any negative value in [start_idx, end_idx]
    if trajectories.shape[0] > 0 and trajectories.shape[1] > end_idx:
        seg_trajs = trajectories[:, start_idx:end_idx + 1]
        gap_prob = round(float(np.mean(np.any(seg_trajs < 0, axis=1))), 4)
    else:
        gap_prob = 1.0 if shortage > 0 else 0.0

    # Contributing events around gap start
    event_ids = []
    event_reasons = []
    for ev in planned_events:
        direction = getattr(ev, "direction", ev.get("direction") if isinstance(ev, dict) else None)
        # If event falls within 7 days before gap start or during gap
        if direction == "expense" and (st_date - timedelta(days=7)) <= ev.due_date <= end_date:
            event_ids.append(ev.id)
            event_reasons.append(f"{ev.title} ({float(ev.amount):,.0f} руб.)")

    if event_reasons:
        explanation = f"Разрыв сформирован крупными обязательствами: {', '.join(event_reasons[:3])} при превышении плановых расходов над поступлениями."
    else:
        explanation = f"Разрыв вызван структурным превышением регулярных операционных расходов над прогнозируемой выручкой бизнеса."

    return CashGap(
        start_date=st_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d"),
        minimum_balance_date=min_date.strftime("%Y-%m-%d"),
        shortage_amount=shortage,
        probability=gap_prob,
        contributing_event_ids=event_ids,
        explanation=explanation
    )
