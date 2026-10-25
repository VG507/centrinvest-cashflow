import { createDebouncedRequest, forecastControlValues } from '../lib/requestSafety';
import { DatePicker } from './DatePicker';
import { ForecastWarnings } from './ForecastWarnings';
import { TableViewport } from './TableViewport';
import { Select } from './Select';
import { useEffect, useState, useRef } from 'react';
import { ArrowDownToLine, ArrowDownLeft, ArrowUpRight, CalendarDays, RefreshCw, ShieldCheck, Wallet, Sparkles, Table2 } from 'lucide-react';
import type { ActualsResponse, AdviceResponse, Company, CreateForecastRequest, ForecastSnapshot } from '../../../contracts/types';
import { dateLabel, downloadCsv, fullDate, rub } from '../lib/cashflow';
import { api, messageOf } from './client';
import { Empty, ErrorBox, Loading, modelNames, Percent } from './shared';
import { ForecastChart } from './ForecastChart';
import { RiskSummary } from './RiskSummary';
import { downloadForecastExcel } from '../lib/forecastExcel';

export default function Overview({ company, actuals, forecast, request, loading, error, create, openEvent, canProbability }: { company:Company;actuals:ActualsResponse|null;forecast:ForecastSnapshot|null;request:CreateForecastRequest|null;loading:boolean;error:string;create:(request:CreateForecastRequest)=>Promise<void>;openEvent:(id:string)=>void;canProbability:boolean }) {
  const controls=forecastControlValues(request,{as_of_date:forecast?.as_of_date??company.balance_date??'',horizon_days:forecast?.horizon_days??30});
  const [horizon,setHorizon]=useState<30|60|90>(controls.horizon), [cutoff,setCutoff]=useState(controls.cutoff), [model,setModel]=useState<CreateForecastRequest['model']>(controls.model), [events,setEvents]=useState(controls.events), [override,setOverride]=useState(controls.override), [table,setTable]=useState(false), [selectedDate,setSelectedDate]=useState('');

  const [advice, setAdvice] = useState<AdviceResponse | null>(null);
  const [adviceLoading, setAdviceLoading] = useState(false);
  const [adviceError, setAdviceError] = useState('');
  const [excelBusy,setExcelBusy]=useState(false), [excelError,setExcelError]=useState('');
  async function exportExcel(){if(!forecast||excelBusy)return;setExcelBusy(true);setExcelError('');try{await downloadForecastExcel(forecast);}catch(e){setExcelError(messageOf(e));}finally{setExcelBusy(false);}}
  const activeForecastIdRef = useRef<string | null>(forecast?.id ?? null);
  const adviceAbortRef = useRef<AbortController | null>(null);

  const stale=!!forecast&&forecast.data_revision!==company.data_revision;
  useEffect(()=>{
    activeForecastIdRef.current = forecast?.id ?? null;
    adviceAbortRef.current?.abort();
    adviceAbortRef.current = null;
    setAdvice(null);
    setAdviceError('');
    setAdviceLoading(false);
    if(forecast){
setCutoff(controls.cutoff);
      setHorizon(controls.horizon);
      setModel(controls.model);
      setEvents(controls.events);
      setOverride(controls.override);

      setSelectedDate('');
    }
  },[forecast?.id,request]);

  const createRef=useRef(create);createRef.current=create;
  const debounced=useRef(createDebouncedRequest<CreateForecastRequest>(request=>{void createRef.current(request);},280));
  useEffect(()=>()=>debounced.current.cancel(),[]);
  const triggerDebouncedCreate=(request:CreateForecastRequest)=>debounced.current.schedule(request);
  const run=()=>debounced.current.run({as_of_date:cutoff,horizon_days:horizon,initial_balance:override===''?null:Number(override),include_planned_events:events,model,expected_data_revision:company.data_revision});

  function changeHorizon(days: 30 | 60 | 90) {
    setHorizon(days);
    if (company.balance_date && (!forecast || request)) {
      triggerDebouncedCreate({
        as_of_date: cutoff || company.balance_date,
        horizon_days: days,
        initial_balance: override === '' ? null : Number(override),
        include_planned_events: events,
        model,
        expected_data_revision: company.data_revision
      });
    }
  }

  function changeModel(nextModel: CreateForecastRequest['model']) {
    setModel(nextModel);
    if (company.balance_date && (!forecast || request)) {
      triggerDebouncedCreate({
        as_of_date: cutoff || company.balance_date,
        horizon_days: horizon,
        initial_balance: override === '' ? null : Number(override),
        include_planned_events: events,
        model: nextModel,
        expected_data_revision: company.data_revision
      });
    }
  }

  async function fetchAdvice() {
    if (!forecast) return;
    const targetId = forecast.id;
    adviceAbortRef.current?.abort();
    const controller = new AbortController();
    adviceAbortRef.current = controller;
    setAdviceLoading(true);
    setAdviceError('');
    try {
      const res = await api('advice', {
        params: { company_id: company.id, forecast_id: targetId },
        data: { business_type: company.business_type || 'Малый бизнес' },
        signal: controller.signal
      });
      if (!controller.signal.aborted && activeForecastIdRef.current === targetId && res.forecast_id === targetId) {
        setAdvice(res);
      }
    } catch (e) {
      if (!controller.signal.aborted && activeForecastIdRef.current === targetId) {
        setAdviceError(messageOf(e));
      }
    } finally {
      if (!controller.signal.aborted && activeForecastIdRef.current === targetId) {
        setAdviceLoading(false);
      }
    }
  }

  const summary=forecast?.summary;
  return <div className="screen-stack overview-stack"><div className="context-strip data-context"><span className="data-context-icon"><CalendarDays size={19}/></span><span className="data-context-date">{company.balance_date?<>Данные по <strong>{fullDate(company.balance_date)}</strong></>:'Нет загруженной выписки'}</span><span className="neutral-tag data-version">Версия данных {company.data_revision}</span></div><div className="metrics"><article className="metric"><div className="metric-label"><Wallet size={18}/>Подтвержденный остаток</div><strong>{company.closing_balance===null?'Нет данных':rub(company.closing_balance)}</strong><p>{company.balance_date?`На конец ${dateLabel(company.balance_date)}`:'Добавьте выписку'}</p></article><article className="metric"><div className="metric-label"><ArrowUpRight size={18}/>Поступления в прогнозе</div><strong>{summary?rub(summary.total_income):'Нет расчета'}</strong><p>{forecast?`${forecast.horizon_days} дней от ${dateLabel(forecast.as_of_date)}`:'Выберите период и постройте прогноз'}</p></article><article className="metric"><div className="metric-label"><ArrowDownLeft size={18}/>Расходы в прогнозе</div><strong>{summary?rub(summary.total_expense):'Нет расчета'}</strong><p>С учетом выбранных плановых событий</p></article></div>
  <section className="panel screen-panel"><div className="section-title"><div><h2>Прогноз остатка денежных средств</h2><p>Статистический прогноз с учетом регулярных и плановых платежей</p></div><ShieldCheck size={24}/></div>
    {forecast&&!request&&<p className="notice" role="status">Исходные параметры этого прогноза неизвестны. Ниже указаны условия нового расчета. Проверьте их и нажмите «Построить прогноз».</p>}
    <form className="forecast-controls" onSubmit={e=>{e.preventDefault();void run();}}><label>Дата расчета<DatePicker required max={company.balance_date??undefined} value={cutoff} onChange={value=>{debounced.current.cancel();setCutoff(value);}}/></label><label>Модель<Select value={model} onChange={e=>changeModel(e.target.value as typeof model)}>{Object.entries(modelNames).map(([id,name])=><option value={id} key={id}>{name}</option>)}</Select></label><fieldset className="period-control"><legend className="sr-only">Горизонт</legend>{([30,60,90] as const).map(days=><button key={days} type="button" aria-pressed={horizon===days} onClick={()=>changeHorizon(days)}>{days} дней</button>)}</fieldset><label className="checkbox-label"><input type="checkbox" checked={events} onChange={e=>{debounced.current.cancel();setEvents(e.target.checked);}}/>Учитывать плановые платежи</label><button className="button button-primary" disabled={loading||!company.balance_date}><RefreshCw size={17}/>{loading?'Рассчитываем…':'Построить прогноз'}</button><details className="balance-override"><summary>Указать другой начальный остаток</summary><label>Сумма в рублях<input type="number" step=".01" value={override} onChange={e=>{debounced.current.cancel();setOverride(e.target.value);}}/></label><p className="field-hint">Пустое поле использует подтвержденный остаток на дату расчета.</p></details></form>
    <ErrorBox message={error} retry={()=>void run()}/>{loading&&<Loading text={forecast?'Обновляем прогноз; ниже показан предыдущий расчет.':'Рассчитываем прогноз…'}/>}{stale&&<p className="notice" role="status">Источники изменились. Этот расчет относится к версии {forecast!.data_revision}; обновляем по текущим данным.</p>}
    {forecast?<><ForecastChart forecast={forecast} actuals={actuals} selectedDate={selectedDate}/><div className="chart-footnote forecast-chart-actions"><button className="button button-secondary chart-action" onClick={()=>setTable(!table)} aria-expanded={table}><Table2 size={15}/>Таблица по дням</button><button className="button button-secondary chart-action" onClick={()=>downloadCsv(`forecast-${forecast.id}.csv`,'date,income,expense,balance,lower,upper,gap_probability\n'+forecast.days.map(d=>[d.date,d.predicted_income,d.predicted_expense,d.predicted_balance,d.balance_lower??'',d.balance_upper??'',d.gap_probability??''].join(',')).join('\n'))}><ArrowDownToLine size={15}/>Экспорт CSV</button><button className="button button-secondary chart-action" disabled={excelBusy} onClick={()=>void exportExcel()}><ArrowDownToLine size={15}/>{excelBusy?'Готовим Excel…':'Экспорт Excel'}</button></div><ErrorBox message={excelError}/>
    {table&&<TableViewport label="Дневной прогноз: семь строк, остальные доступны при прокрутке"><table><caption>Дневной прогноз; суммы в рублях</caption><thead><tr><th>Дата</th><th>Поступления</th><th>Расходы</th><th>Остаток</th><th>80% интервал</th><th>Вероятность нехватки</th></tr></thead><tbody>{forecast.days.map(d=><tr key={d.date} className={selectedDate===d.date?'selected-row':''}><th scope="row">{dateLabel(d.date)}</th><td>{rub(d.predicted_income)}</td><td>{rub(d.predicted_expense)}</td><td className={d.predicted_balance<0?'negative':''}>{rub(d.predicted_balance)}{d.predicted_balance<0&&<small>Нехватка</small>}</td><td>{d.balance_lower===null||d.balance_upper===null?'Нет оценки':`${rub(d.balance_lower)} — ${rub(d.balance_upper)}`}</td><td><Percent value={d.gap_probability}/></td></tr>)}</tbody></table></TableViewport>}</>:<Empty>Постройте прогноз после загрузки выписки. Результат и риски будут рассчитаны сервером.</Empty>}
  </section>{forecast&&<><RiskSummary forecast={forecast} canProbability={canProbability}/>

  {(summary!.maximum_shortage > 0 || summary!.risk_level === 'critical' || summary!.risk_level === 'medium') && (
    <section className="panel screen-panel quick-solutions-panel">
      <div className="section-title">
        <div>
          <h2>Как снизить риск кассового разрыва</h2>
          <p>Рекомендации по текущему прогнозу и ожидаемым платежам</p>
        </div>
      </div>
      <div className="advice-actions">
        <button
          type="button"
          className="button button-primary advice-request"
          disabled={adviceLoading}
          onClick={() => void fetchAdvice()}
        >
          <Sparkles size={16} />
          {adviceLoading ? 'Готовим рекомендации…' : 'Получить рекомендации'}
        </button>
        <ErrorBox message={adviceError} retry={() => void fetchAdvice()} />
        {advice && (
          <div className="advice-box" aria-live="polite">
            <h3>{advice.mode === 'llm' ? 'Анализ финансового ассистента' : 'Рекомендации по правилам'}</h3>
            <p>{advice.analysis}</p>
            <div className="advice-list">
              {advice.recommendations.map((rec, i) => (
                <div key={i} className={`advice-item ${rec.priority === 'high' ? 'high' : ''}`}>
                  <strong>
                    {rec.title} {rec.priority === 'high' ? '(Срочно)' : ''}
                  </strong>
                  <p>{rec.rationale}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  )}

  <ForecastWarnings forecast={forecast} openDate={date=>{setSelectedDate(date);setTable(true);}} openEvent={openEvent}/></>}
  </div>;
}

