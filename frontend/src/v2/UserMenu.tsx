import { useEffect, useRef } from 'react';
import { ChevronDown, LogOut } from 'lucide-react';

export function UserMenu({name,pending,onLogout}:{name:string;pending:boolean;onLogout:()=>Promise<void>}){
  const container=useRef<HTMLDetailsElement>(null);
  useEffect(()=>{
    const outside=(event:PointerEvent)=>{if(event.target instanceof Node&&!container.current?.contains(event.target)&&container.current)container.current.open=false;};
    const escape=(event:KeyboardEvent)=>{if(event.key==='Escape'&&container.current?.open){container.current.open=false;container.current.querySelector('summary')?.focus();}};
    document.addEventListener('pointerdown',outside);document.addEventListener('keydown',escape);
    return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape);};
  },[]);
  const initials=name.split(/\s+/).filter(Boolean).slice(0,2).map(word=>word[0]).join('').toLocaleUpperCase('ru-RU');
  return <details className="account-menu" ref={container}><summary aria-label={`Аккаунт: ${name}`}><span className="account-avatar" aria-hidden="true">{initials}</span><span className="account-name">{name}</span><ChevronDown size={16} aria-hidden="true"/></summary><div className="account-popover"><span className="account-caption">Вы вошли как</span><strong>{name}</strong><button type="button" disabled={pending} onClick={()=>void onLogout()}><LogOut size={17}/>{pending?'Выходим…':'Выйти из аккаунта'}</button></div></details>;
}
