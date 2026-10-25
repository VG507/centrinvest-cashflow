import { DatePicker } from './DatePicker';
import { TableViewport } from './TableViewport';
import { Select } from './Select';
import { useState } from 'react';
import { ArrowRight, ChartNoAxesCombined, CheckCheck, CalendarClock } from 'lucide-react';
import type { SnapshotRef } from './shared';
import { Empty, ErrorBox, Loading, useResource } from './shared';
import { api } from './client';
import { dateLabel, fullDate, rub } from '../lib/cashflow';
import { PlanChart } from './ForecastChart';
import { groupPlanWeeks } from './plan';

export default function PlanActual({companyId,snapshots,latestId,revision,openEvent,openOverview}:{companyId:string;snapshots:SnapshotRef[];latestId:string;revision:number;openEvent:(id:string)=>void;openOverview:()=>void}) {
  const [selected,setSelected]=useState(latestId||snapshots[0]?.id||''), [inputId,setInputId]=useState(''), [week,setWeek]=useState(false), [metric,setMetric]=useState<'balance'|'income'|'expense'>('balance'), [from,setFrom]=useState(''), [to,setTo]=useState('');
  const invalid=!!from&&!!to&&from>to;
  const result=useResource(async signal=>selected&&!invalid?api('planActual',{params:{company_id:companyId},data:{forecast_id:selected,from_date:from||undefined,to_date:to||undefined,granularity:'day'},signal}):null,[companyId,selected,from,to,revision]);
  const data=!result.isStale&&!invalid&&result.data?.forecast_id===selected?result.data:null;
  const days=week?groupPlanWeeks(data?.days??[]):data?.days??[];
  const last=days.filter(d=>d[`actual_${metric}`]!==null).at(-1);
  const planned=last?.[`planned_${metric}`], actual=last?.[`actual_${metric}`];
  const delta=planned!==undefined&&actual!==undefined&&actual!==null?actual-planned:null;
  const tone=(value:number)=>Math.abs(value)<.01?'':(metric==='expense'?value>0:value<0)?'negative':'positive';
  const signed=(value:number)=>`${value>0?'+':''}${rub(value)}`;
  const labels={balance:'Остаток',income:'Поступления',expense:'Расходы'};
  return <div className="screen-stack plan-redesign"><section className="panel screen-panel">
    <div className="section-title"><div><h2>Насколько факт отличается от плана?</h2><p>Сравните прогноз с фактическими операциями.</p></div></div>
    {(selected||snapshots.length>0)&&<div className="plan-filters"><label>Сохранённый план<Select value={selected} onChange={e=>setSelected(e.target.value)}><option value="">Выберите прогноз</option>{snapshots.map(s=><option key={s.id} value={s.id}>Прогноз от {fullDate(s.as_of_date)} · {s.horizon_days} дней</option>)}{selected&&!snapshots.some(s=>s.id===selected)&&<option value={selected}>План {selected.slice(0,8)}</option>}</Select></label><label>С даты<DatePicker value={from} onChange={setFrom}/></label><label>По дату<DatePicker min={from||undefined} value={to} onChange={setTo}/></label></div>}
    <details className="snapshot-id"><summary>Открыть план по ID</summary><form className="action-row" onSubmit={e=>{e.preventDefault();setSelected(inputId.trim());}}><label>ID сохранённого плана<input value={inputId} onChange={e=>setInputId(e.target.value)} required/></label><button className="button button-secondary">Открыть</button></form><p className="field-hint">Укажите ID прогноза, ранее сохранённого на сервере.</p></details>
    <ErrorBox message={invalid?'Начало периода должно быть не позже его окончания.':result.error} retry={invalid?undefined:result.reload}/>
    {!selected&&<div className="plan-start"><ChartNoAxesCombined size={32}/><h3>{snapshots.length?'Выберите сохранённый прогноз':'Сначала нужен прогноз'}</h3><p>{snapshots.length?'Выберите план выше, чтобы сравнить его с фактическими операциями.':'Постройте прогноз в обзоре. Затем здесь можно будет сравнить его с фактическими операциями.'}</p><button className="button button-primary" onClick={openOverview}>Перейти в обзор <ArrowRight size={16}/></button></div>}
    {selected&&!invalid&&result.loading&&<Loading text="Получаем план и фактические операции…"/>}
    {data&&<><div className="plan-controls"><div className="plan-segments" role="group" aria-label="Показатель">{(['balance','income','expense'] as const).map(value=><button key={value} aria-pressed={metric===value} onClick={()=>setMetric(value)}>{labels[value]}</button>)}</div><div className="plan-segments plan-granularity" role="group" aria-label="Группировка"><button aria-pressed={!week} onClick={()=>setWeek(false)}>По дням</button><button aria-pressed={week} onClick={()=>setWeek(true)}>По неделям</button></div></div>
    {last?<div className="plan-comparison"><div className="plan-comparison-heading"><h3>{labels[metric]}: план и факт</h3><span>{week?'За выбранные дни недели с':'На'} {fullDate(last.date)}</span></div><div className="plan-numbers"><div><span>По плану</span><strong>{rub(planned!)}</strong></div><div><span>По факту</span><strong>{rub(actual!)}</strong></div><div><span>Разница с планом</span><strong className={tone(delta!)}>{signed(delta!)}</strong></div></div></div>:<Empty>В выбранном периоде ещё нет фактических данных для сравнения.</Empty>}
    {days.length>0&&<><div className="chart-legend plan-legend"><span><i className="plan-line"/>План</span><span><i className="fact-line"/>Факт</span><small>Пропуски означают отсутствие данных</small></div><PlanChart days={days} metric={metric} period={{from:data.days[0].date,to:data.days.at(-1)!.date}}/>
    <TableViewport visibleRows={5} label="План и факт: пять строк, остальные при прокрутке"><table className="plan-table"><caption><span className="plan-table-caption"><span><strong>{labels[metric]}: сравнение плана и факта</strong><small>{fullDate(data.days[0].date)} — {fullDate(data.days.at(-1)!.date)}</small></span><span className="plan-table-period">{week?'По неделям':'По дням'}<b>{days.length} {week?'нед.':'дн.'}</b></span></span></caption><thead><tr><th>{week?'Неделя с':'Дата'}</th><th>План</th><th>Факт</th><th>Разница</th></tr></thead><tbody>{days.map(d=>{const p=d[`planned_${metric}`],a=d[`actual_${metric}`],diff=a===null?null:a-p;return <tr key={d.date}><th scope="row" title={fullDate(d.date)}>{dateLabel(d.date)}</th><td>{rub(p)}</td><td>{a===null?<span className="plan-unavailable">Нет данных</span>:rub(a)}</td><td className={diff===null?'':tone(diff)}>{diff===null?<span className="plan-unavailable">Нет оценки</span>:signed(diff)}</td></tr>;})}</tbody></table></TableViewport></>}
    {!days.length&&<Empty>В выбранном диапазоне нет дней сохранённого плана.</Empty>}
    <details className="plan-provenance"><summary>О данных сравнения</summary><p>План: {data.forecast_id}. Версия фактических данных: {data.data_revision}.</p>{data.updated_forecast_id&&<p>После обновления данных создан новый прогноз: {data.updated_forecast_id}. Первоначальный план сохранён.</p>}</details>
    </>}
  </section>{selected&&<section className="panel screen-panel plan-overdue"><div className="section-title"><div><h2>Просроченные платежи</h2><p>По данным выбранного плана</p></div><CalendarClock size={22}/></div>{data?(data.overdue_events.length?<div className="plan-event-list">{data.overdue_events.map(e=><article key={e.id}><div><time dateTime={e.due_date}>{fullDate(e.due_date)}</time><h3>{e.title}</h3></div><div><small>Осталось к оплате</small><strong>{rub(Math.max(0,e.amount-e.paid_amount))}</strong></div><button className="button button-secondary" onClick={()=>openEvent(e.id)}>В календарь <ArrowRight size={16}/></button></article>)}</div>:<div className="plan-clear"><CheckCheck size={22}/><span>Сервер не сообщил о просроченных платежах.</span></div>):<p className="field-hint">{result.loading?'Проверяем просроченные платежи…':'Данные о просроченных платежах недоступны.'}</p>}</section>}</div>;
}
