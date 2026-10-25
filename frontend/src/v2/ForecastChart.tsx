import { useId } from 'react';
import { Area, CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { ActualsResponse, ForecastSnapshot, PlanActualDay } from '../../../blackboard/contracts/types';
import { addDays, dateLabel, fullDate, rub, shortRub } from '../lib/cashflow';

export function ForecastChart({ forecast, actuals, scenario, selectedDate }: { forecast: ForecastSnapshot; actuals: ActualsResponse | null; scenario?: ForecastSnapshot | null; selectedDate?: string }) {
  const patternId=useId().replaceAll(':','');
  const observed=new Map(actuals?.days.map(d=>[d.date,d])??[]);
  const scenarioDays=new Map(scenario?.days.map(d=>[d.date,d])??[]);
  const data=[...Array.from({length:21},(_,i)=> {
    const date=addDays(forecast.as_of_date,i-20), actual=observed.get(date);
    const balance=actual?.observation==='missing'?null:actual?.closing_balance??null;
    return {date,actual:balance,missing:balance===null,history:true,forecast:date===forecast.as_of_date?forecast.summary.closing_balance:null,interval:null as [number,number]|null,scenario:null as number|null};
  }), ...forecast.days.map(d=>({date:d.date,actual:null,missing:false,history:false,forecast:d.predicted_balance,interval:d.balance_lower!==null&&d.balance_upper!==null?[d.balance_lower,d.balance_upper] as [number,number]:null,scenario:scenarioDays.get(d.date)?.predicted_balance??null}))];
  const historyActuals=data.map(d=>d.actual).filter((v):v is number=>v!==null);
  const low=Math.min(0,...historyActuals,...forecast.days.flatMap(d=>[d.balance_lower??d.predicted_balance,d.predicted_balance]),...scenario?.days.map(d=>d.predicted_balance)??[]);
  const high=Math.max(0,...data.map(d=>d.actual??0),...forecast.days.map(d=>d.balance_upper??d.predicted_balance),...scenario?.days.map(d=>d.predicted_balance)??[]);
  const minimum=forecast.days.find(d=>d.date===forecast.summary.minimum_balance_date);
  const end=forecast.days.at(-1)!;
  const samePoint=minimum?.date===end.date;
  const gaps:{start:string;end:string}[]=[];
  for(const row of data.filter(d=>d.history)) {
    if(!row.missing)continue;
    const previous=gaps.at(-1);
    if(previous&&addDays(previous.end,1)===row.date)previous.end=row.date;
    else gaps.push({start:row.date,end:row.date});
  }
  const range=high-low||Math.abs(high)||1;
  const lineLow=Math.min(forecast.summary.closing_balance,...forecast.days.map(d=>d.predicted_balance));
  const lineHigh=Math.max(forecast.summary.closing_balance,...forecast.days.map(d=>d.predicted_balance));
  const zeroOffset=Math.max(0,Math.min(1,lineHigh/(lineHigh-lineLow||1)));
  const roughStep=(high+range*.12-(low<0?low-range*.18:0))/5;
  const magnitude=10**Math.floor(Math.log10(roughStep));
  const step=([1,2,2.5,5,10].find(n=>n>=roughStep/magnitude)??10)*magnitude;
  const axisLow=Math.floor((low<0?low-range*.18:0)/step)*step;
  const axisHigh=Math.ceil((high+range*.12)/step)*step;
  const axisTicks=Array.from({length:Math.round((axisHigh-axisLow)/step)+1},(_,i)=>axisLow+i*step);
  const axisMoney=(value:number)=>value===0?'0':Math.max(Math.abs(low),Math.abs(high))>=1e6?`${(value/1e6).toLocaleString('ru-RU',{maximumFractionDigits:2})} млн`:shortRub(value).replace(' ₽','');
  return <div className="forecast-visual"><div className="forecast-periods"><span>История <small>до {dateLabel(forecast.as_of_date)}</small></span><span className="forecast-final"><span>Прогноз <small>{dateLabel(forecast.days[0].date)} — {dateLabel(end.date)}</small></span><span className="forecast-final-value"><small>{samePoint?'Минимум и остаток на конец':'Остаток на конец периода'}</small><strong className={end.predicted_balance<0?'negative':''}>{rub(end.predicted_balance)}</strong></span></span></div><div className="chart-legend"><span><i className="legend-line actual"/>История</span><span><i className="legend-line predicted"/>Базовый прогноз</span><span><i className="interval-key"/>{forecast.interval_coverage===null?'Интервал не оценен':'80% интервал'}</span>{scenario&&<span><i className="legend-line stress"/>Стресс-сценарий</span>}</div><div className="v2-chart forecast-balance-chart" role="img" aria-label={`Прогноз на ${forecast.horizon_days} дней. Дата расчёта ${fullDate(forecast.as_of_date)}. Минимум ${rub(forecast.summary.minimum_balance)} на ${fullDate(forecast.summary.minimum_balance_date)}. Остаток в конце ${rub(end.predicted_balance)}. Значения доступны в таблице ниже.`}><ResponsiveContainer width="100%" height="100%"><ComposedChart data={data} margin={{top:50,right:18,bottom:35,left:0}} accessibilityLayer>
    <defs><pattern id={`missing-${patternId}`} width="7" height="7" patternUnits="userSpaceOnUse"><path d="M-2 2L2-2M0 7L7 0M5 9L9 5" stroke="#dbe2dd" strokeWidth="1"/></pattern><linearGradient id={`balance-${patternId}`} x1="0" y1="0" x2="0" y2="1"><stop offset={zeroOffset} stopColor="var(--action)"/><stop offset={zeroOffset} stopColor="var(--rust)"/></linearGradient></defs>
    <CartesianGrid vertical={false} stroke="#dce5de" strokeDasharray="3 5"/><XAxis dataKey="date" tickFormatter={dateLabel} minTickGap={48} axisLine={false} tickLine={false} tickMargin={12} tick={{fontSize:12,fill:'var(--muted)'}}/><YAxis tickFormatter={axisMoney} width={86} ticks={axisTicks} domain={[axisLow,axisHigh]} axisLine={false} tickLine={false} tickMargin={10} tick={{fontSize:13,fill:'var(--muted)'}}/>
    <ReferenceArea x1={data[0].date} x2={forecast.as_of_date} fill="#f5f7f5" fillOpacity={.8}/>
    {gaps.map(gap=><ReferenceArea key={gap.start} x1={gap.start} x2={gap.end===forecast.as_of_date?gap.end:addDays(gap.end,1)} fill={`url(#missing-${patternId})`} fillOpacity={.65}/>)}
    {low<0&&<ReferenceArea x1={forecast.as_of_date} x2={end.date} y1={low-range*.18} y2={0} fill="var(--rust)" fillOpacity={.06}/>}
    <ReferenceLine y={0} stroke="#a4afa7"/><ReferenceLine x={forecast.as_of_date} stroke="#a4afa7" strokeDasharray="4 5" label={{value:`Расчёт ${dateLabel(forecast.as_of_date)}`,position:'top',offset:16,fill:'var(--muted)',fontSize:11}}/>{selectedDate&&<ReferenceLine x={selectedDate} stroke="var(--action)"/>}
    <Area type="linear" dataKey="interval" stroke="none" fill="var(--action)" fillOpacity={.22} isAnimationActive={false} connectNulls={false}/><Line dataKey={row=>row.interval?.[0]??null} name="Нижняя граница интервала" stroke="var(--action)" strokeOpacity={.5} strokeWidth={1} strokeDasharray="3 4" dot={false} connectNulls={false} isAnimationActive={false}/><Line dataKey={row=>row.interval?.[1]??null} name="Верхняя граница интервала" stroke="var(--action)" strokeOpacity={.5} strokeWidth={1} strokeDasharray="3 4" dot={false} connectNulls={false} isAnimationActive={false}/><Line dataKey="actual" name="История" type="linear" stroke="#84958b" strokeWidth={1.8} dot={false} connectNulls={false} isAnimationActive={false}/><Line dataKey="forecast" name="Базовый прогноз" type="linear" stroke={lineLow<0?(lineHigh===lineLow?'var(--rust)':`url(#balance-${patternId})`):'var(--action)'} strokeWidth={3.2} dot={false} activeDot={{r:5,stroke:'#fff',strokeWidth:2}} connectNulls={false} isAnimationActive={false}/>{scenario&&<Line dataKey="scenario" name="Стресс-сценарий" type="linear" stroke="var(--rust)" strokeWidth={2.5} dot={false} isAnimationActive={false}/>}
    {minimum&&!samePoint&&<ReferenceDot x={minimum.date} y={minimum.predicted_balance} r={5} fill={minimum.predicted_balance<0?'var(--rust)':'var(--action)'} stroke="#fff" strokeWidth={2} label={({viewBox})=>viewBox&&'x'in viewBox&&'y'in viewBox?<PointCaption x={Number(viewBox.x)+5} y={Number(viewBox.y)+5} below title={`Минимум · ${dateLabel(minimum.date)}`} amount={minimum.predicted_balance} align={minimum.date>forecast.days[Math.floor(forecast.days.length*.8)].date?'end':'start'}/>:<g/>}/>}
    <ReferenceDot x={end.date} y={end.predicted_balance} r={5} fill={end.predicted_balance<0?'var(--rust)':'var(--action)'} stroke="#fff" strokeWidth={2}/>
    <Tooltip filterNull={false} cursor={{stroke:'#a4afa7',strokeDasharray:'3 4'}} content={({active,payload,label})=>{
      const row=payload?.[0]?.payload as typeof data[number]|undefined;
      if(!active||!row)return null;
      return <div className="forecast-tooltip"><strong>{fullDate(String(label))}</strong>{row.history?<><span>История</span><b>{row.missing?'Нет данных':rub(row.actual!)}</b></>:<><span>Прогноз остатка</span><b className={(row.forecast??0)<0?'negative':''}>{rub(row.forecast!)}</b></>}{row.interval?<div><span>80% интервал</span><p>{rub(row.interval[0])} — {rub(row.interval[1])}</p></div>:!row.history&&<span>Интервал не оценен</span>}{row.scenario!==null&&<div><span>Стресс-сценарий</span><p>{rub(row.scenario)}</p></div>}</div>;
    }}/>
  </ComposedChart></ResponsiveContainer></div>{gaps.length>0&&<p className="forecast-missing-note"><i aria-hidden="true"/>При отсутствии данных могут появляться разрывы в графике истории.</p>}</div>;
}
function PointCaption({x,y,title,amount,align,below=false}:{x:number;y:number;title:string;amount:number;align:'start'|'end';below?:boolean}) {
  return <g className="forecast-point-caption" pointerEvents="none"><text x={x} y={y+(below?23:-35)} textAnchor={align} className="forecast-point-title">{title}</text><text x={x} y={y+(below?41:-16)} textAnchor={align} className={`forecast-point-amount ${amount<0?'is-negative':''}`}>{rub(amount)}</text></g>;
}
export function PlanChart({ days, metric, period }: {days: PlanActualDay[];metric:'balance'|'income'|'expense';period?:{from:string;to:string}}) {
  const values=days.flatMap(d=>[d[`planned_${metric}`],d[`actual_${metric}`]]).filter((v):v is number=>v!==null);
  const low=Math.min(...values),high=Math.max(...values),padding=Math.max((high-low)*.18,Math.abs(high)*.025,1);
  const lower=metric==='balance'?low-padding:Math.min(0,low-padding),upper=high+padding;
  const rough=(upper-lower)/5,magnitude=10**Math.floor(Math.log10(rough));
  const step=([1,2,2.5,5,10].find(n=>n>=rough/magnitude)??10)*magnitude;
  const floor=Math.floor(lower/step)*step,ceiling=Math.ceil(upper/step)*step;
  const ticks=Array.from({length:Math.round((ceiling-floor)/step)+1},(_,i)=>floor+i*step);
  const last=days.at(-1),lastObserved=days.filter(d=>d[`actual_${metric}`]!==null).at(-1);
  const axis=(v:number)=>Math.max(Math.abs(floor),Math.abs(ceiling))>=1e6?`${(v/1e6).toLocaleString('ru-RU',{maximumFractionDigits:2})} млн`:shortRub(v).replace(' ₽','');
  if(!last)return null;
  return <div className="plan-chart-visual"><div className="plan-chart-topline"><div><span>Период сравнения</span><strong>{dateLabel(period?.from??days[0].date)} — {fullDate(period?.to??last.date)}</strong></div><div><span>План на конец периода</span><strong>{rub(last[`planned_${metric}`])}</strong></div></div><div className="v2-chart" role="img" aria-label="План — серая пунктирная линия, факт — зелёная сплошная. Значения доступны в таблице."><ResponsiveContainer width="100%" height="100%"><ComposedChart data={days} margin={{left:0,right:22,top:28,bottom:16}} accessibilityLayer><CartesianGrid vertical={false} stroke="#dce5de" strokeDasharray="3 5"/><XAxis dataKey="date" tickFormatter={dateLabel} minTickGap={62} axisLine={false} tickLine={false} tickMargin={12} tick={{fontSize:12,fill:'var(--muted)'}}/><YAxis width={82} ticks={ticks} domain={[floor,ceiling]} tickFormatter={axis} axisLine={false} tickLine={false} tickMargin={10} tick={{fontSize:12,fill:'var(--muted)'}}/>{floor<0&&ceiling>0&&<><ReferenceArea y1={floor} y2={0} fill="var(--rust)" fillOpacity={.04}/><ReferenceLine y={0} stroke="#acb8af"/></>}<Line type="linear" dataKey={`planned_${metric}`} name="План" stroke="#687d70" strokeWidth={2.5} strokeDasharray="7 5" dot={false} activeDot={{r:5,fill:'#687d70',stroke:'#fff',strokeWidth:2}} isAnimationActive={false}/><Line type="linear" dataKey={`actual_${metric}`} name="Факт" stroke="var(--action)" strokeWidth={3.2} dot={false} activeDot={{r:6,fill:'var(--action)',stroke:'#fff',strokeWidth:2}} connectNulls={false} isAnimationActive={false}/><ReferenceDot x={last.date} y={last[`planned_${metric}`]} r={4} fill="#687d70" stroke="#fff" strokeWidth={2}/>{lastObserved&&<ReferenceDot x={lastObserved.date} y={lastObserved[`actual_${metric}`]!} r={5} fill="var(--action)" stroke="#fff" strokeWidth={2}/>}<Tooltip filterNull={false} cursor={{stroke:'#9cad9f',strokeDasharray:'3 4'}} content={({active,payload,label})=>{const row=payload?.[0]?.payload as PlanActualDay|undefined;if(!active||!row)return null;const plan=row[`planned_${metric}`],fact=row[`actual_${metric}`],difference=fact===null?null:fact-plan;return <div className="forecast-tooltip"><strong>{fullDate(String(label))}</strong><span>План</span><b>{rub(plan)}</b><span>Факт</span><b>{fact===null?'Нет данных':rub(fact)}</b><div><span>Разница</span><p>{difference===null?'Нет оценки':`${difference>0?'+':''}${rub(difference)}`}</p></div></div>;}}/></ComposedChart></ResponsiveContainer></div></div>;
}
