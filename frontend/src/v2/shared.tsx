import { useEffect, useRef, useState } from 'react';
import type { DependencyList, ReactNode } from 'react';
import { LoaderCircle, TriangleAlert } from 'lucide-react';
import type { Category, CategoryId, ForecastSnapshot } from '../../../contracts/types';
import { addDays, validDate } from '../lib/cashflow';
import { messageOf } from './client';

export function useResource<T>(load: (signal: AbortSignal) => Promise<T>, deps: DependencyList) {
  const loader = useRef(load); loader.current = load;
  const [data, setData] = useState<T | null>(null), [error, setError] = useState(''), [loading, setLoading] = useState(true), [revision, setRevision] = useState(0), [isStale, setIsStale] = useState(false);
  useEffect(() => {
    const abort = new AbortController(); setLoading(true); setError(''); setIsStale(true);
    loader.current(abort.signal).then(value => { if (!abort.signal.aborted) { setData(value); setIsStale(false); } }).catch(e => { if (!abort.signal.aborted) { setError(messageOf(e)); setData(null); setIsStale(false); } }).finally(() => { if (!abort.signal.aborted) setLoading(false); });
    return () => abort.abort();
  }, [...deps, revision]);
  return { data, error, loading, isStale, reload: () => setRevision(r => r + 1), setData };
}
export function ErrorBox({ message, retry }: { message: string; retry?: () => void }) {
  return message ? <div className="error-message" role="alert"><TriangleAlert size={18} /><div>{message}{retry && <button className="text-button" onClick={retry}>Повторить</button>}</div></div> : null;
}
export function Loading({ text = 'Загружаем данные…' }: { text?: string }) { return <p className="v2-loading" role="status"><LoaderCircle size={19} className="spin" />{text}</p>; }
export function Empty({ children }: { children: ReactNode }) { return <div className="v2-empty">{children}</div>; }
export function Percent({ value }: { value: number | null }) { return <>{value === null ? 'Нет оценки' : new Intl.NumberFormat('ru-RU', { style: 'percent', maximumFractionDigits: 1 }).format(value)}</>; }
export const modelNames = { seasonal_naive: 'Сезонный наивный', weekday_mean: 'Среднее по дням недели', ridge_calendar: 'Ridge с календарем', auto: 'Автоматический выбор' };
export function categoryName(categories: Category[], id: CategoryId) { return categories.find(c => c.id === id)?.name ?? id; }
export function validateSnapshot(snapshot: ForecastSnapshot): ForecastSnapshot {
  if (!snapshot || !snapshot.summary || typeof snapshot.summary.closing_balance !== 'number' || !Number.isFinite(snapshot.summary.closing_balance) || typeof snapshot.summary.end_balance !== 'number' || !Number.isFinite(snapshot.summary.end_balance) || typeof snapshot.summary.total_income !== 'number' || !Number.isFinite(snapshot.summary.total_income) || typeof snapshot.summary.total_expense !== 'number' || !Number.isFinite(snapshot.summary.total_expense)) {
    throw new Error('Сервер вернул некорректную сводку остатков или оборотов.');
  }
  if (!Array.isArray(snapshot.days) || snapshot.days.length !== snapshot.horizon_days || ![30,60,90].includes(snapshot.horizon_days) || !validDate(snapshot.as_of_date)) {
    throw new Error('Сервер вернул некорректную длину или дату прогноза.');
  }
  let previous = snapshot.summary.closing_balance;
  let totalIncome = 0;
  let totalExpense = 0;

  snapshot.days.forEach((day, i) => {
    const probabilities = [day.gap_probability, snapshot.summary.any_gap_probability];
    if ((day.balance_lower === null) !== (day.balance_upper === null)) {
      throw new Error('Доверительный интервал должен содержать обе границы или отсутствовать полностью.');
    }
    if (day.date !== addDays(snapshot.as_of_date, i+1) || ![day.predicted_income,day.predicted_expense,day.predicted_balance].every(Number.isFinite) || day.predicted_income < 0 || day.predicted_expense < 0 || Math.abs(previous + day.predicted_income - day.predicted_expense - day.predicted_balance) > .05 || probabilities.some(p => p !== null && (!Number.isFinite(p) || p < 0 || p > 1)) || [day.balance_lower,day.balance_upper].some(v=>v!==null&&!Number.isFinite(v)) || (day.balance_lower !== null && day.balance_upper !== null && day.balance_lower > day.balance_upper)) {
      throw new Error('Даты, суммы или вероятности ответа не согласованы.');
    }
    totalIncome += day.predicted_income;
    totalExpense += day.predicted_expense;
    previous = day.predicted_balance;
  });

  const lastBalance = snapshot.days.at(-1)?.predicted_balance;
  if (Math.abs(totalIncome - snapshot.summary.total_income) > 0.5 || Math.abs(totalExpense - snapshot.summary.total_expense) > 0.5 || (lastBalance !== undefined && Math.abs(lastBalance - snapshot.summary.end_balance) > 0.5)) {
    throw new Error('Сводные обороты или конечный остаток противоречат дневным рядам.');
  }
  return snapshot;
}
export interface SnapshotRef { id: string; as_of_date: string; horizon_days: number; created_at: string }
export function readSnapshots(companyId: string): SnapshotRef[] {
  try { const rows: unknown = JSON.parse(sessionStorage.getItem(`snapshots:${companyId}`) ?? '[]'); return Array.isArray(rows) ? rows.filter((r): r is SnapshotRef => !!r && typeof r.id === 'string' && typeof r.as_of_date === 'string' && typeof r.created_at === 'string' && typeof r.horizon_days === 'number') : []; } catch { return []; }
}
export function rememberSnapshot(companyId: string, snapshot: ForecastSnapshot) {
  const rows = [{ id: snapshot.id, as_of_date: snapshot.as_of_date, horizon_days: snapshot.horizon_days, created_at: snapshot.created_at }, ...readSnapshots(companyId).filter(r => r.id !== snapshot.id)].slice(0, 30);
  try { sessionStorage.setItem(`snapshots:${companyId}`, JSON.stringify(rows)); } catch { /* Storage may be disabled; the current result remains usable. */ }
  return rows;
}
