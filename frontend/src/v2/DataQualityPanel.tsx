import { Database, CalendarDays, Tags, Copy, TriangleAlert } from 'lucide-react';
import type { ForecastSnapshot } from '../../../contracts/types';
import { Percent } from './shared';
import { fullDate } from '../lib/cashflow';

function warningText(text:string){
  const missing=/^Detected (\d+) missing business days in historical statement\.$/.exec(text);
  if(missing)return `В истории выписки обнаружены пропуски за ${missing[1]} рабочих дней.`;
  if(text==='Short history (<28 observed days). Prediction uncertainty is elevated.')return 'Короткая история: менее 28 дней наблюдений. Неопределённость прогноза повышена.';
  return text;
}
export function DataQualityPanel({forecast,revision}:{forecast:ForecastSnapshot;revision:number}){
  const quality=forecast.data_quality;
  return <section className="panel screen-panel data-quality-panel"><div className="section-title"><div><h2>Качество входных данных</h2><p>История, на которой построен прогноз от {fullDate(forecast.as_of_date)}</p></div><Database size={24}/></div><div className="quality-facts"><article><CalendarDays size={19}/><strong>{quality.observed_days}</strong><span>Дней наблюдений</span></article><article className={quality.missing_days?'has-issue':''}><TriangleAlert size={19}/><strong>{quality.missing_days}</strong><span>Пропущенных дней</span></article><article><Tags size={19}/><strong><Percent value={quality.uncategorized_share}/></strong><span>Без категории</span></article><article><Copy size={19}/><strong>{quality.duplicate_rows}</strong><span>Повторяющихся строк</span></article></div>{revision!==forecast.data_revision&&<p className="notice">Показатели относятся к версии {forecast.data_revision}. Текущая версия — {revision}: обновите прогноз.</p>}<div className="quality-notes">{quality.warnings.map((text,i)=><p key={i}><TriangleAlert size={17}/><span>{warningText(text)}</span></p>)}</div></section>;
}
