import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import { CalendarDays, ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react';

const months=['Январь','Февраль','Март','Апрель','Май','Июнь','Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь'];
export function MonthPicker({value,onChange}:{value:string;onChange:(month:string)=>void}){
  const [open,setOpen]=useState(false),[year,setYear]=useState(Number(value.slice(0,4))),[position,setPosition]=useState<CSSProperties>({});
  const trigger=useRef<HTMLButtonElement>(null),popup=useRef<HTMLDivElement>(null),id=useId();
  function close(){setOpen(false);trigger.current?.focus({preventScroll:true});}
  useLayoutEffect(()=>{
    if(!open)return;
    const place=()=>{const rect=trigger.current!.getBoundingClientRect(),width=Math.min(290,document.documentElement.clientWidth-24);setPosition({position:'fixed',width,left:Math.max(12,Math.min(rect.left,document.documentElement.clientWidth-width-12)),top:window.innerHeight-rect.bottom>=270?rect.bottom+8:Math.max(12,rect.top-258),maxHeight:window.innerHeight-24});};
    place();window.addEventListener('resize',place);window.addEventListener('scroll',place,true);
    return()=>{window.removeEventListener('resize',place);window.removeEventListener('scroll',place,true);};
  },[open]);
  useEffect(()=>{
    if(!open)return;
    popup.current?.querySelector<HTMLButtonElement>('[aria-pressed="true"]')?.focus({preventScroll:true});
    const outside=(event:PointerEvent)=>{if(event.target instanceof Node&&!popup.current?.contains(event.target)&&!trigger.current?.contains(event.target))setOpen(false);};
    const escape=(event:KeyboardEvent)=>{if(event.key==='Escape'){event.preventDefault();close();}};
    const focusOutside=(event:FocusEvent)=>{if(event.target instanceof Node&&!popup.current?.contains(event.target)&&!trigger.current?.contains(event.target))setOpen(false);};
    document.addEventListener('pointerdown',outside);document.addEventListener('keydown',escape);document.addEventListener('focusin',focusOutside);
    return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape);document.removeEventListener('focusin',focusOutside);};
  },[open]);
  const selectedYear=Number(value.slice(0,4)),selectedMonth=Number(value.slice(5,7))-1;
  return <><button ref={trigger} type="button" className="month-picker-trigger" aria-label={`Выберите месяц: ${months[selectedMonth]} ${selectedYear}`} aria-haspopup="dialog" aria-expanded={open} aria-controls={open?id:undefined} onClick={()=>{if(!open)setYear(selectedYear);setOpen(!open);}}><CalendarDays size={16}/><span>{months[selectedMonth]} {selectedYear}</span><ChevronDown size={15}/></button>{open&&createPortal(<div ref={popup} id={id} role="dialog" aria-label="Выбор месяца" className="month-picker-popup" style={position}><div className="month-picker-year"><button type="button" aria-label="Предыдущий год" disabled={year<=1} onClick={()=>setYear(y=>y-1)}><ChevronLeft size={17}/></button><strong aria-live="polite">{year}</strong><button type="button" aria-label="Следующий год" disabled={year>=9999} onClick={()=>setYear(y=>y+1)}><ChevronRight size={17}/></button></div><div className="month-picker-months">{months.map((month,index)=><button key={month} type="button" data-month={index} aria-pressed={year===selectedYear&&index===selectedMonth} onKeyDown={event=>{const step=event.key==='ArrowRight'?1:event.key==='ArrowLeft'?-1:event.key==='ArrowDown'?3:event.key==='ArrowUp'?-3:0;if(step){event.preventDefault();popup.current?.querySelector<HTMLButtonElement>(`[data-month="${(index+step+12)%12}"]`)?.focus({preventScroll:true});}}} onClick={()=>{onChange(`${String(year).padStart(4,'0')}-${String(index+1).padStart(2,'0')}`);close();}}>{month}</button>)}</div></div>,document.body)}</>;
}
