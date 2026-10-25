import { DatePicker } from './DatePicker';
import { MonthPicker } from './MonthPicker';
import { TableViewport } from './TableViewport';
import { Select } from './Select';
import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, Plus, X } from 'lucide-react';
import type { Category, EventKind, ExternalEventsRequest, PlannedEvent, PlannedEventInput } from '../../../blackboard/contracts/types';
import { addDays, dateLabel, fullDate, rub, validDate } from '../lib/cashflow';
import { api, messageOf } from './client';
import { Empty, ErrorBox, Percent } from './shared';

export const eventKinds: Record<EventKind,string>={manual:'Разовый платеж',invoice:'Счет',contract:'Договор',tax:'Налог / ЕНП',loan:'Кредит',payroll:'Зарплата',recurring:'Регулярный платеж'};
export const eventStatuses={planned:'Запланирован',partial:'Оплачен частично',paid:'Оплачен',overdue:'Просрочен',cancelled:'Отменен'};
export default function Calendar({ companyId, revision, events, categories, cutoff, selectedId, onChange }: {companyId:string;revision?:number;events:PlannedEvent[];categories:Category[];cutoff:string;selectedId:string;onChange:()=>Promise<void>}) {
  const [month,setMonth]=useState((cutoff||new Date().toISOString().slice(0,10)).slice(0,7)), [editing,setEditing]=useState<PlannedEvent|null>(null), [formOpen,setFormOpen]=useState(false), [busy,setBusy]=useState(false), [error,setError]=useState(''), [notice,setNotice]=useState(''), [external,setExternal]=useState('');
  const [title,setTitle]=useState(''), [kind,setKind]=useState<EventKind>('manual'), [direction,setDirection]=useState<'income'|'expense'>('income'), [amount,setAmount]=useState(''), [due,setDue]=useState(addDays(cutoff||new Date().toISOString().slice(0,10),1)), [category,setCategory]=useState<PlannedEventInput['category_id']>('sales'), [counterparty,setCounterparty]=useState(''), [probability,setProbability]=useState('');
  const [activeDayModal, setActiveDayModal] = useState<string | null>(null);
  const editorRevisionRef = useRef<number | null>(null);
  const params={company_id:companyId};

  useEffect(()=>{
    if (!activeDayModal) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setActiveDayModal(null);
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [activeDayModal]);

  useEffect(()=>{ const event=events.find(e=>e.id===selectedId); if(event) {setMonth(event.due_date.slice(0,7));setTimeout(()=>document.getElementById(`event-${event.id}`)?.scrollIntoView({block:'center'}),0);} },[selectedId,events]);
  const monthEvents=events.filter(e=>e.due_date.startsWith(month));
  const cells=useMemo(()=>{const first=`${month}-01`,weekday=new Date(`${first}T12:00:00Z`).getUTCDay();return Array.from({length:42},(_,i)=>addDays(first,i-((weekday+6)%7)));},[month]);
  function moveMonth(step:number) { const date=new Date(`${month}-01T12:00:00Z`);date.setUTCMonth(date.getUTCMonth()+step);setMonth(date.toISOString().slice(0,7)); }
  function open(event:PlannedEvent|null) {if(busy) return;editorRevisionRef.current=revision??null;setEditing(event);setTitle(event?.title??'');setKind(event?.kind??'manual');setDirection(event?.direction??'income');setAmount(event?String(event.amount):'');setDue(event?.due_date??addDays(cutoff||`${month}-01`,1));setCategory(event?.category_id??'sales');setCounterparty(event?.counterparty_name??'');setProbability(event?.on_time_probability===null||!event?'':String(event.on_time_probability*100));setError('');setFormOpen(true);setTimeout(()=>document.getElementById('event-title')?.focus(),0);}
  function input():PlannedEventInput {
    const probNum = probability.trim() === '' ? null : Number(probability);
    return {
      title:title.trim(),
      kind,
      direction,
      amount:Number(amount),
      due_date:due,
      category_id:category,
      counterparty_name:counterparty.trim()||null,
      on_time_probability:probNum === null ? null : probNum / 100,
      source:editing?.source??{kind:'manual',source_id:null,external_id:null,label:'Введено предпринимателем'}
    };
  }
  async function save(cancelled=false) {
    if(busy) return;
    setBusy(true);setError('');setNotice('');
    try {
      const value=input();
      if(!value.title||!validDate(value.due_date)||!Number.isFinite(value.amount)||value.amount<=0) {
        throw new Error('Укажите название, дату и положительную сумму.');
      }
      if(value.on_time_probability !== null) {
        if(!Number.isFinite(value.on_time_probability) || value.on_time_probability < 0 || value.on_time_probability > 1) {
          throw new Error('Вероятность оплаты в срок должна быть в диапазоне от 0% до 100%.');
        }
      }
      if(editing) await api('updateEvent',{params:{...params,event_id:editing.id},data:{...value,cancelled,expected_data_revision:editorRevisionRef.current}});
      else await api('createEvent',{params,data:value});
      setFormOpen(false);
      await onChange();
      setNotice(cancelled?'Платеж отменен. Прогноз обновляется.':'Платеж сохранен. Прогноз обновляется.');
    }catch(e){setError(messageOf(e));}finally{setBusy(false);}}

  const activeDayEvents = activeDayModal ? events.filter(e => e.due_date === activeDayModal && e.status !== 'cancelled') : [];

  return <div className="screen-stack"><section className="panel screen-panel calendar-panel"><div className="section-title"><div><h2>Платежный календарь</h2><p>Счета клиентов, кредиты, налоги и регулярные обязательства</p></div><button className="button button-primary" onClick={()=>open(null)}><Plus size={17}/>Добавить платеж</button></div><div className="calendar-toolbar"><button className="button button-secondary" aria-label="Предыдущий месяц" onClick={()=>moveMonth(-1)}><ChevronLeft size={18}/></button><MonthPicker value={month} onChange={setMonth}/><button className="button button-secondary" aria-label="Следующий месяц" onClick={()=>moveMonth(1)}><ChevronRight size={18}/></button></div>
    <div className="calendar-grid" aria-label="Календарь платежей">{['Пн','Вт','Ср','Чт','Пт','Сб','Вс'].map(day=><div className="calendar-weekday" key={day}>{day}</div>)}{cells.map(date=>{const items=events.filter(e=>e.due_date===date&&e.status!=='cancelled');return <div className={`calendar-cell ${date.startsWith(month)?'':'outside'}`} key={date}><time dateTime={date}>{Number(date.slice(-2))}</time>{items.slice(0,2).map(e=><button className={`calendar-payment ${e.direction}`} key={e.id} onClick={()=>{setMonth(e.due_date.slice(0,7));open(e);}} title={`${e.title}: ${rub(e.amount-e.paid_amount)}`}><span>{e.title}</span><strong>{rub(e.status==='cancelled'||e.status==='paid'?0:Math.max(0,e.amount-e.paid_amount))}</strong></button>)}{items.length>2&&<button type="button" className="calendar-more-badge" onClick={(e)=>{e.stopPropagation();setActiveDayModal(date);}} aria-label={`Показать все ${items.length} событий на ${dateLabel(date)}`}>Еще {items.length-2}</button>}</div>;})}</div>
    <p className="field-hint">ЕНП и другие налоги добавляются с подтвержденной датой и суммой. Сервис не назначает налоговые обязательства автоматически.</p><ErrorBox message={error}/>{notice&&<p className="success-message" role="status">{notice}</p>}
    {formOpen&&<form className="event-form" onSubmit={e=>{e.preventDefault();void save();}}><h3>{editing?'Изменить платеж':'Новый платеж'}</h3><div className="form-grid"><label>Название<input id="event-title" required maxLength={200} value={title} onChange={e=>setTitle(e.target.value)}/></label><label>Тип<Select value={kind} onChange={e=>setKind(e.target.value as EventKind)}>{Object.entries(eventKinds).map(([id,name])=><option value={id} key={id}>{name}</option>)}</Select></label><label>Направление<Select value={direction} onChange={e=>{const value=e.target.value as typeof direction;setDirection(value);setCategory(value==='income'?'sales':'other_expense');}}><option value="income">Поступление</option><option value="expense">Списание</option></Select></label><label>Сумма, ₽<input required type="number" step=".01" min=".01" value={amount} onChange={e=>setAmount(e.target.value)}/></label><label>Срок оплаты<DatePicker required value={due} onChange={setDue}/></label><label>Категория<Select value={category} onChange={e=>setCategory(e.target.value as typeof category)}>{categories.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</Select></label><label>Контрагент<input value={counterparty} onChange={e=>setCounterparty(e.target.value)}/></label><label>Вероятность оплаты в срок, %<input type="number" min="0" max="100" step=".1" value={probability} onChange={e=>setProbability(e.target.value)}/><small>Необязательно; число от 0 до 100.</small></label></div><div className="action-row"><button className="button button-primary" disabled={busy}>{busy?'Сохраняем…':'Сохранить платеж'}</button>{editing&&<button className="button button-secondary" type="button" disabled={busy||editing.status==='paid'||editing.status==='cancelled'} onClick={()=>void save(true)}>Отменить платеж</button>}<button className="button button-plain" type="button" onClick={()=>setFormOpen(false)}>Закрыть форму</button></div></form>}
    <div className="calendar-ledger"><TableViewport visibleRows={5} label="Платежи за месяц: до пяти строк, остальные при прокрутке"><table><colgroup><col className="event-date"/><col/><col className="event-amount"/><col className="event-probability"/><col className="event-action"/></colgroup><caption>Платежи за месяц <span>Остаток к оплате по сохранённым событиям</span></caption><thead><tr><th>Дата / статус</th><th>Событие</th><th>К оплате</th><th>Оплата в срок</th><th>Действие</th></tr></thead><tbody>{monthEvents.map(e=><tr id={`event-${e.id}`} key={e.id} className={`${selectedId===e.id?'selected-row':''} event-row-${e.status}`}><th scope="row"><time dateTime={e.due_date} title={fullDate(e.due_date)}>{dateLabel(e.due_date)}</time><small className={`status-${e.status}`}>{eventStatuses[e.status]}</small></th><td className="operation-description"><strong>{e.title}</strong><small>{eventKinds[e.kind]}{e.counterparty_name?` / ${e.counterparty_name}`:''}</small><small className="event-source">{e.source.label}</small></td><td className={`event-amount-cell ${e.direction==='income'?'positive':''}`}>{e.direction==='income'?'+':'−'}{rub(e.status==='cancelled'||e.status==='paid'?0:Math.max(0,e.amount-e.paid_amount))}<small>Всего {rub(e.amount)}</small></td><td><Percent value={e.on_time_probability}/></td><td><button className="button button-secondary event-edit" onClick={()=>open(e)}>Изменить</button></td></tr>)}</tbody></table></TableViewport></div>{!monthEvents.length&&<Empty>В этом месяце нет сохраненных платежей. Добавьте ожидаемое поступление или обязательство.</Empty>}

    {activeDayModal && (
      <div className="calendar-day-modal-backdrop" onClick={() => setActiveDayModal(null)}>
        <div className="calendar-day-modal" role="dialog" aria-modal="true" aria-label={`События на ${fullDate(activeDayModal)}`} onClick={e => e.stopPropagation()}>
          <div className="calendar-day-modal-header">
            <div>
              <h3>Платежи на {fullDate(activeDayModal)}</h3>
              <p className="field-hint">Всего событий: {activeDayEvents.length}</p>
            </div>
            <button type="button" className="button button-plain" onClick={() => setActiveDayModal(null)} aria-label="Закрыть">
              <X size={18} />
            </button>
          </div>
          <div className="calendar-day-modal-list">
            {activeDayEvents.map(item => (
              <div key={item.id} className="calendar-day-modal-item">
                <div className="calendar-day-modal-info">
                  <strong>{item.title}</strong>
                  <span className="field-hint">{eventKinds[item.kind]}{item.counterparty_name ? ` / ${item.counterparty_name}` : ''}</span>
                  <span className={`status-${item.status}`} style={{ fontSize: '11px', display: 'inline-block', marginTop: '2px' }}>{eventStatuses[item.status]}</span>
                </div>
                <div className="calendar-day-modal-actions">
                  <span className={`event-amount-cell ${item.direction === 'income' ? 'positive' : ''}`} style={{ fontWeight: 600 }}>
                    {item.direction === 'income' ? '+' : '−'}{rub(item.status === 'cancelled' || item.status === 'paid' ? 0 : Math.max(0, item.amount - item.paid_amount))}
                  </span>
                  <button type="button" className="button button-secondary" style={{ minHeight: '34px', padding: '6px 12px', fontSize: '12px' }} onClick={() => { setActiveDayModal(null); open(item); }}>
                    Изменить
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    )}
  </section><section className="panel screen-panel calendar-import-panel"><h2>Импорт счетов, договоров и налогов</h2><p className="field-hint">Загрузите подготовленный файл счетов, графиков договоров и налогов. Даты, суммы и источник сохранятся; повторы проверит сервер.</p><label htmlFor="external-events">Файл ожидаемых платежей (JSON)<input id="external-events" type="file" accept=".json,application/json" disabled={busy} onChange={async e=>{const file=e.target.files?.[0];if(file){setExternal('');if(file.size>10485760){setError('Файл больше 10 МБ.');return;}setExternal(await file.text());setError('');}}}/></label>{external&&<p className="field-hint">Файл прочитан. Нажмите «Импортировать события» для проверки и сохранения.</p>}<button className="button button-secondary" disabled={busy||!external.trim()} onClick={async()=>{setBusy(true);setError('');try{const data=JSON.parse(external) as ExternalEventsRequest;if(!data.source||!data.source.label||![data.invoices,data.contracts,data.taxes].every(Array.isArray))throw new Error('Укажите source с названием и массивы invoices, contracts, taxes.');const result=await api('importExternalEvents',{params,data});await onChange();setNotice(`Добавлено ${result.created_events.length}, обновлено ${result.updated_count}, повторов ${result.duplicate_count}.`);setExternal('');}catch(e){setError(messageOf(e));}finally{setBusy(false);}}}>Импортировать события</button><ErrorBox message={error}/></section></div>;
}
