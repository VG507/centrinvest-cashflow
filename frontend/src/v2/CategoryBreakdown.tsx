import { ArrowDownLeft, ArrowUpRight } from 'lucide-react';
import type { Category, CategoryTotal } from '../../../contracts/types';
import { rub } from '../lib/cashflow';
import { categoryName, Empty } from './shared';

export function CategoryBreakdown({categories,totals}:{categories:Category[];totals:CategoryTotal[]}){
  return <section className="panel screen-panel category-breakdown"><div className="section-title"><div><h2>Распределение по категориям</h2><p>По всей загруженной истории. Доли рассчитаны отдельно для поступлений и расходов.</p></div></div>{totals.length?(['income','expense'] as const).map(direction=>{
    const items=totals.filter(item=>item.direction===direction).sort((a,b)=>b.amount-a.amount);
    if(!items.length)return null;
    const total=items.reduce((sum,item)=>sum+item.amount,0);
    const Icon=direction==='income'?ArrowUpRight:ArrowDownLeft;
    return <div className={`category-group ${direction}`} key={direction}><div className="category-group-heading"><span className="category-group-icon"><Icon size={19}/></span><h3>{direction==='income'?'Поступления':'Расходы'}</h3><strong>{rub(total)}</strong></div><div className="category-distribution">{items.map(item=>{
      const share=total>0?item.amount/total*100:0;
      const name=categoryName(categories,item.category_id);
      return <article className="category-distribution-row" key={item.category_id}><div><span>{name}</span><strong>{rub(item.amount)}</strong></div><div className="category-share"><span className="category-share-track" role="progressbar" aria-label={`Доля категории ${name} в ${direction==='income'?'поступлениях':'расходах'}`} aria-valuenow={share} aria-valuemin={0} aria-valuemax={100}><span style={{width:`${share}%`}}/></span><span>{share.toLocaleString('ru-RU',{maximumFractionDigits:1})}%</span></div></article>;
    })}</div></div>;
  }):<Empty>Категории появятся после загрузки выписки.</Empty>}</section>;
}
