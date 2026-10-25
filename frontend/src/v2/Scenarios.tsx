import { DatePicker } from './DatePicker';
import { Select } from './Select';
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { RotateCcw } from 'lucide-react';
import { TableViewport } from './TableViewport';
import { ScenarioComparisonChart } from './ScenarioComparisonChart';
import { ScenarioSummary } from './ScenarioSummary';
import type { ActualsResponse, Category, CategoryId, ForecastSnapshot, PlannedEvent, ScenarioAdjustment, ScenarioResponse } from '../../../contracts/types';
import { dateLabel, fullDate, rub } from '../lib/cashflow';
import { api, messageOf } from './client';
import { Empty, ErrorBox, Loading, validateSnapshot } from './shared';

export default function Scenarios({ companyId, forecast, actuals, events, categories }: {companyId:string;forecast:ForecastSnapshot|null;actuals:ActualsResponse|null;events:PlannedEvent[];categories:Category[]}) {
  const [delay,setDelay]=useState(false), [eventId,setEventId]=useState(''), [days,setDays]=useState(21), [drop,setDrop]=useState(false), [percent,setPercent]=useState(20), [extra,setExtra]=useState(false), [amount,setAmount]=useState('100000'), [date,setDate]=useState(forecast?.days[0]?.date??''), [cost,setCost]=useState(false), [costPercent,setCostPercent]=useState(10), [costCategory,setCostCategory]=useState<CategoryId>('rent');
  const [resultKey,setResultKey]=useState(''),[showHistory,setShowHistory]=useState(false);
  const [result,setResult]=useState<ScenarioResponse|null>(null), [error,setError]=useState(''), [pending,setPending]=useState(false), [retry,setRetry]=useState(0);
  const eligible=events.filter(e=>e.direction==='income'&&e.status!=='paid'&&e.status!=='cancelled'&&e.amount>e.paid_amount&&forecast&&e.due_date>=forecast.days[0].date&&e.due_date<=forecast.days.at(-1)!.date);
  useEffect(()=>{setResult(null);setError('');setDate(forecast?.days[0]?.date??'');},[forecast?.id]);
  const adjustments:ScenarioAdjustment[]=[];
  if(forecast) {
    const range={from_date:forecast.days[0].date,to_date:forecast.days.at(-1)!.date};
    if(delay&&eventId)adjustments.push({kind:'delay_income',event_id:eventId,delay_days:days});
    if(drop)adjustments.push({kind:'revenue_drop',percent,...range});
    if(cost)adjustments.push({kind:'fixed_cost_increase',percent:costPercent,category_ids:[costCategory],...range});
    if(extra&&Number(amount)>0&&date>=range.from_date&&date<=range.to_date)adjustments.push({kind:'extra_expense',amount:Number(amount),date,category_id:'other_expense'});
  }

  function handleDelayToggle(enabled: boolean) {
    setDelay(enabled);
    if (enabled && !eventId && eligible.length > 0) {
      setEventId(eligible[0].id);
    }
  }

  const key=JSON.stringify(adjustments);
  const invalid=extra&&(!Number.isFinite(Number(amount))||Number(amount)<=0||!forecast||date<forecast.days[0].date||date>forecast.days.at(-1)!.date)?'Укажите положительный расход и дату внутри прогноза.':'';
  const delayNeedsAccount = delay && !eventId && eligible.length > 0;

  useEffect(()=>{
    const controller=new AbortController();
    if(!forecast||!adjustments.length||invalid||delayNeedsAccount){setPending(false);setResult(null);setError('');return;}
    setPending(true);setError('');
    const timer=setTimeout(()=>{api('scenario',{params:{company_id:companyId,forecast_id:forecast.id},data:{name:'Стресс-тест движения денежных средств',adjustments:JSON.parse(key) as ScenarioAdjustment[]},signal:controller.signal}).then(value=>{validateSnapshot(value.forecast);if(value.base_forecast_id!==forecast.id)throw new Error('Сервер вернул сценарий для другого прогноза.');if(!controller.signal.aborted){setResultKey(`${forecast.id}:${key}`);setResult(value);}}).catch(e=>{if(!controller.signal.aborted){setError(messageOf(e));setResult(null);}}).finally(()=>{if(!controller.signal.aborted)setPending(false);});},120);
    return()=>{clearTimeout(timer);controller.abort();};
  },[key,forecast?.id,companyId,invalid,delayNeedsAccount,retry]);
  if(!forecast)return <Empty>Сначала постройте базовый прогноз в разделе «Обзор финансов».</Empty>;
  const currentResult=!invalid&&!delayNeedsAccount&&result&&resultKey===`${forecast.id}:${key}`?result:null;
  const calculating=pending||(!invalid&&!delayNeedsAccount&&!error&&adjustments.length>0&&!currentResult);
  const extraDate=forecast.days[Math.min(10,forecast.days.length-1)].date;
  const activePreset=drop&&percent===20&&!delay&&!extra&&!cost?'revenue':delay&&days===21&&!drop&&!extra&&!cost?'delay':extra&&Number(amount)===150000&&date===extraDate&&!delay&&!drop&&!cost?'extra':delay&&days===14&&drop&&percent===20&&!extra&&!cost?'combined':'';
  function applyPreset(preset:string){setDelay(preset==='delay'||preset==='combined');setDrop(preset==='revenue'||preset==='combined');setExtra(preset==='extra');setCost(false);if(preset==='revenue'||preset==='combined')setPercent(20);if(preset==='delay'||preset==='combined'){setEventId(eligible[0]?.id??'');setDays(preset==='delay'?21:14);}if(preset==='extra'){setAmount('150000');setDate(extraDate);}}
  const noIncome='Нет подходящих неоплаченных поступлений в календаре на период прогноза.';
  const stressByDate=new Map(currentResult?.forecast.days.map(day=>[day.date,day])??[]);
  return <div className="scenario-layout scenario-redesign"><section className="panel screen-panel scenario-controls"><h2>Условия сценария</h2><p className="field-hint">Включите условия и задайте значения. Расчёт обновится автоматически.</p>
    <ScenarioCondition id="delay" label="Клиент задержит оплату" checked={delay} onChange={handleDelayToggle} disabled={!eligible.length} reason={!eligible.length?noIncome:undefined}>
      <label>Ожидаемое поступление<Select value={eventId} onChange={e=>setEventId(e.target.value)}><option value="">Выберите счёт</option>{eligible.map(e=><option value={e.id} key={e.id}>{e.title} / {rub(e.amount-e.paid_amount)} / {dateLabel(e.due_date)}</option>)}</Select></label>
      {delayNeedsAccount && <p className="field-hint" style={{ marginTop: '4px', color: '#65776a' }}>Выберите счёт из списка выше для расчёта задержки оплаты.</p>}
      <label className="scenario-range"><span>Задержка <strong>{days} дн.</strong></span><input aria-label="Задержка оплаты, дней" type="range" min={14} max={28} value={days} onChange={e=>setDays(Number(e.target.value))}/><span className="range-limits"><span>14 дней</span><span>28 дней</span></span></label>
    </ScenarioCondition>
    <ScenarioCondition id="revenue" label="Выручка снизится" checked={drop} onChange={setDrop}><label className="scenario-range"><span>Снижение <strong>−{percent}%</strong></span><input aria-label="Снижение выручки, процентов" type="range" min={10} max={30} value={percent} onChange={e=>setPercent(Number(e.target.value))}/><span className="range-limits"><span>−10%</span><span>−30%</span></span></label></ScenarioCondition>
    <ScenarioCondition id="extra" label="Внеплановый расход" checked={extra} onChange={setExtra}><label>Сумма<ScenarioMoneyInput value={amount} onChange={setAmount}/></label><label>Дата<DatePicker min={forecast.days[0].date} max={forecast.days.at(-1)!.date} value={date} onChange={setDate}/></label></ScenarioCondition>
    <ScenarioCondition id="cost" label="Постоянные расходы вырастут" checked={cost} onChange={setCost}><label>Категория<Select value={costCategory} onChange={e=>setCostCategory(e.target.value as CategoryId)}>{categories.filter(c=>c.direction!=='income').map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</Select></label><label className="scenario-range"><span>Рост <strong>+{costPercent}%</strong></span><input aria-label="Рост постоянных расходов, процентов" type="range" min={0} max={100} value={costPercent} onChange={e=>setCostPercent(Number(e.target.value))}/><span className="range-limits"><span>0%</span><span>100%</span></span></label></ScenarioCondition>
    <button className="button button-secondary scenario-reset" onClick={()=>{setDelay(false);setDrop(false);setExtra(false);setCost(false);setResult(null);setError('');}}><RotateCcw size={15}/>Сбросить сценарий</button><ErrorBox message={invalid}/>
  </section>
  <section className="panel screen-panel scenario-results"><div className="scenario-results-heading"><div><h2>{currentResult?'Базовый прогноз и стресс-сценарий':'Базовый прогноз'}</h2><p>{fullDate(forecast.days[0].date)} — {fullDate(forecast.days.at(-1)!.date)}</p></div></div>
    <div className="scenario-presets" role="group" aria-label="Готовые стресс-сценарии">{[{id:'revenue',label:'Выручка −20%',disabled:false},{id:'delay',label:'Задержка оплаты',disabled:!eligible.length},{id:'extra',label:'Расход 150 000 ₽',disabled:false},{id:'combined',label:'Комплексный стресс',disabled:!eligible.length}].map(preset=><button key={preset.id} type="button" className="scenario-preset" aria-pressed={activePreset===preset.id} disabled={preset.disabled} title={preset.disabled?noIncome:undefined} onClick={()=>applyPreset(preset.id)}>{preset.label}</button>)}</div>
    {!eligible.length&&<p className="scenario-preset-reason">Задержка оплаты и комплексный стресс недоступны: нет подходящих поступлений в календаре.</p>}
    <ScenarioSummary base={forecast} result={currentResult} pending={calculating}/>
    <div className="scenario-chart-toolbar"><label className="checkbox-label"><input type="checkbox" checked={showHistory} onChange={e=>setShowHistory(e.target.checked)}/>Показать историю</label><span role="status" aria-live="polite">{calculating?<Loading text="Пересчитываем…"/>:currentResult?'Сценарий рассчитан':''}</span></div>
    <ErrorBox message={error} retry={()=>setRetry(n=>n+1)}/><ScenarioComparisonChart base={forecast} scenario={currentResult?.forecast??null} actuals={actuals} showHistory={showHistory}/>
    {!adjustments.length&&<p className="scenario-initial-note">Выберите условие, чтобы сравнить результаты.</p>}
    {currentResult&&<><div className="scenario-gap-context"><span>Первый разрыв в сценарии</span><strong>{currentResult.forecast.summary.first_gap_date?fullDate(currentResult.forecast.summary.first_gap_date):'Не ожидается в базовой траектории'}</strong><span>Максимальная нехватка <b>{rub(currentResult.forecast.summary.maximum_shortage)}</b></span></div>{delay&&<p className="field-hint">Если задержанная оплата выйдет за горизонт, она не попадёт в поступления этого периода.</p>}<details className="scenario-comparison-table"><summary>Таблица сравнения по дням</summary><TableViewport visibleRows={5} label="Сравнение по дням: пять строк, остальные при прокрутке"><table><thead><tr><th>Дата</th><th>База</th><th>Сценарий</th><th>Изменение</th></tr></thead><tbody>{forecast.days.map(day=>{const stress=stressByDate.get(day.date);return <tr key={day.date}><th>{dateLabel(day.date)}</th><td>{rub(day.predicted_balance)}</td><td className={stress&&stress.predicted_balance<0?'negative':''}>{stress?rub(stress.predicted_balance):'Нет данных'}</td><td>{stress?rub(stress.predicted_balance-day.predicted_balance):'Нет данных'}</td></tr>;})}</tbody></table></TableViewport></details></>}
  </section></div>;
}
function ScenarioCondition({id,label,checked,onChange,children,disabled=false,reason}:{id:string;label:string;checked:boolean;onChange:(checked:boolean)=>void;children:ReactNode;disabled?:boolean;reason?:string}){
  return <div className={`scenario-condition ${checked?'is-enabled':''}`}><div className="scenario-condition-heading"><span>{label}</span><button type="button" role="switch" aria-label={label} aria-checked={checked} aria-controls={checked?`scenario-${id}`:undefined} disabled={disabled} title={reason} onClick={()=>onChange(!checked)}><span/></button></div>{reason&&<p className="scenario-unavailable">{reason}</p>}{checked&&<div className="scenario-fields" id={`scenario-${id}`}>{children}</div>}</div>;
}
function ScenarioMoneyInput({value,onChange}:{value:string;onChange:(value:string)=>void}){
  const inputRef = useRef<HTMLInputElement>(null);
  const cursorRef = useRef<number | null>(null);

  const [integer,fraction]=value.split('.');
  const display=integer.replace(/\B(?=(\d{3})+(?!\d))/g,' ')+(value.includes('.')?','+(fraction??''):'');

  useLayoutEffect(() => {
    if (cursorRef.current !== null && inputRef.current) {
      inputRef.current.setSelectionRange(cursorRef.current, cursorRef.current);
      cursorRef.current = null;
    }
  }, [display]);

  function handleChange(event: React.ChangeEvent<HTMLInputElement>) {
    const rawInput = event.target.value;
    const oldCursor = event.target.selectionStart ?? rawInput.length;

    // Считаем количество значащих символов (цифры и точка/запятая) слева от курсора
    const leftText = rawInput.slice(0, oldCursor);
    const digitsLeft = leftText.replace(/[\s\u00A0]/g, '').length;

    let normalized = rawInput.replace(/[\s\u00A0]/g, '');
    if (normalized.includes('.') && normalized.includes(',')) {
      normalized = normalized.replace(/,/g, '');
    } else if ((normalized.match(/,/g) || []).length > 1) {
      normalized = normalized.replace(/,/g, '');
    } else {
      normalized = normalized.replace(',', '.');
    }

    if (/^\d*(?:\.\d{0,2})?$/.test(normalized)) {
      // Предвычисляем новый display для расчета курсора
      const [newInt, newFrac] = normalized.split('.');
      const newDisplay = newInt.replace(/\B(?=(\d{3})+(?!\d))/g, ' ') + (normalized.includes('.') ? ',' + (newFrac ?? '') : '');

      let targetPos = 0;
      let countedDigits = 0;
      while (targetPos < newDisplay.length && countedDigits < digitsLeft) {
        if (newDisplay[targetPos] !== ' ') {
          countedDigits++;
        }
        targetPos++;
      }
      cursorRef.current = targetPos;
      onChange(normalized);
    }
  }

  return (
    <span className="scenario-money-input">
      <input
        ref={inputRef}
        type="text"
        inputMode="decimal"
        aria-label="Сумма внепланового расхода"
        value={display}
        onChange={handleChange}
      />
      <span aria-hidden="true">₽</span>
    </span>
  );
}
