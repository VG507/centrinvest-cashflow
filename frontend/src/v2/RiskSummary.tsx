import { CalendarDays, ChartNoAxesCombined, ShieldCheck, TriangleAlert, Wallet } from 'lucide-react';
import type { ForecastSnapshot } from '../../../blackboard/contracts/types';
import { fullDate, rub } from '../lib/cashflow';
import { Percent } from './shared';

export function RiskSummary({ forecast, canProbability }: { forecast: ForecastSnapshot; canProbability: boolean }) {
  const { summary } = forecast;
  const probability = canProbability ? summary.any_gap_probability : null;
  return <section className="risk-summary-grid risk-overview" aria-label="Ключевые показатели прогноза">
    <article className={`risk-summary risk-stat ${summary.minimum_balance < 0 ? 'is-negative' : 'is-positive'}`}>
      <div className="risk-stat-heading"><span className="risk-stat-icon"><Wallet size={18} aria-hidden="true" /></span><h3>Минимальный остаток</h3></div>
      <strong className="risk-stat-value">{rub(summary.minimum_balance)}</strong>
      <div className="risk-stat-detail"><CalendarDays size={14} aria-hidden="true" /><div><span>Дата минимума</span><time dateTime={summary.minimum_balance_date}>{fullDate(summary.minimum_balance_date)}</time></div></div>
    </article>
    <article className={`risk-summary risk-stat ${summary.maximum_shortage > 0 ? 'is-negative' : 'is-positive'}`}>
      <div className="risk-stat-heading"><span className="risk-stat-icon">{summary.maximum_shortage > 0 ? <TriangleAlert size={18} aria-hidden="true" /> : <ShieldCheck size={18} aria-hidden="true" />}</span><h3>Максимальная нехватка</h3></div>
      <strong className="risk-stat-value">{rub(summary.maximum_shortage)}</strong>
      <div className="risk-stat-detail"><div>{summary.first_gap_date ? <><span>Первый кассовый разрыв</span><time dateTime={summary.first_gap_date}>{fullDate(summary.first_gap_date)}</time></> : <><span>В базовом прогнозе</span><b>Нехватки денег нет</b></>}</div></div>
    </article>
    <article className={`risk-summary risk-stat risk-stat-probability ${probability === null ? 'unavailable' : summary.risk_level}`}>
      <div className="risk-stat-heading"><span className="risk-stat-icon"><ChartNoAxesCombined size={18} aria-hidden="true" /></span><h3>Вероятность кассового разрыва</h3></div>
      <strong className={`risk-stat-value ${probability === null ? 'risk-stat-unavailable' : ''}`}><Percent value={probability} /></strong>
      <div className="risk-stat-detail"><div>{probability === null ? <span>Недостаточно данных для оценки</span> : <><span>Хотя бы один разрыв</span><b>За {forecast.horizon_days} дней прогноза</b></>}</div></div>
    </article>
  </section>;
}
