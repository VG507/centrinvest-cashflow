import type { PlanActualDay } from '../../../blackboard/contracts/types';
import { addDays } from '../lib/cashflow';
export function groupPlanWeeks(days: PlanActualDay[]): PlanActualDay[] {
  const groups=new Map<string,PlanActualDay[]>();
  for(const day of days) {const offset=(new Date(`${day.date}T12:00:00Z`).getUTCDay()+6)%7,key=addDays(day.date,-offset);groups.set(key,[...(groups.get(key)??[]),day]);}
  return [...groups.entries()].map(([date,rows])=>{
    const complete=rows.every(r=>r.actual_income!==null&&r.actual_expense!==null&&r.actual_balance!==null),last=rows.at(-1)!;
    return {date,planned_income:rows.reduce((s,r)=>s+r.planned_income,0),planned_expense:rows.reduce((s,r)=>s+r.planned_expense,0),planned_balance:last.planned_balance,actual_income:complete?rows.reduce((s,r)=>s+r.actual_income!,0):null,actual_expense:complete?rows.reduce((s,r)=>s+r.actual_expense!,0):null,actual_balance:complete?last.actual_balance:null,net_flow_variance:complete?rows.reduce((s,r)=>s+(r.net_flow_variance??0),0):null,overdue_event_ids:[...new Set(rows.flatMap(r=>r.overdue_event_ids))]};
  });
}
