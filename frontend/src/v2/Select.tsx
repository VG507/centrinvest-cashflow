import { Children, isValidElement, useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import type { CSSProperties, SelectHTMLAttributes } from 'react';
import { createPortal } from 'react-dom';
import { Check, ChevronDown } from 'lucide-react';

/** A compact, scrollable presentation of the existing native select and its handler. */
export function Select({ children, className = '', ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  const native = useRef<HTMLSelectElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const id = useId();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [label, setLabel] = useState('');
  const [position, setPosition] = useState<CSSProperties>({});
  const search = useRef({ text: '', time: 0 });
  const options = Children.toArray(children).filter(isValidElement<{ value?: string | number; disabled?: boolean; children?: React.ReactNode }>).map(child => ({
    value: String(child.props.value ?? child.props.children ?? ''),
    label: child.props.children,
    disabled: child.props.disabled,
  }));
  const selected = options.findIndex(option => option.value === String(props.value ?? props.defaultValue ?? options[0]?.value));

  useEffect(() => {
    const parentLabel = native.current?.labels?.[0];
    setLabel(props['aria-label'] ?? Array.from(parentLabel?.childNodes ?? []).filter(node => node.nodeType === Node.TEXT_NODE).map(node => node.textContent).join('').trim());
  }, [props['aria-label']]);

  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const rect = trigger.current!.getBoundingClientRect();
      const below = window.innerHeight - rect.bottom - 12;
      const above = rect.top - 12;
      const upwards = below < Math.min(options.length, 7) * 44 + 10 && above > below;
      const viewportWidth=document.documentElement.clientWidth,width=Math.min(rect.width,viewportWidth-16);
      setPosition({ left: Math.max(8, Math.min(rect.left, viewportWidth-width-8)), width,
        maxHeight: Math.min(7 * 44 + 10, Math.max(44, upwards ? above : below)),
        ...(upwards ? { bottom: window.innerHeight - rect.top + 6 } : { top: rect.bottom + 6 }) });
    };
    place();
    const closeOutside = (event: Event) => {
      const target = event.target as Node;
      if (!trigger.current?.contains(target) && !menu.current?.contains(target)) setOpen(false);
    };
    window.addEventListener('resize', place);
    document.addEventListener('scroll', place, true);
    document.addEventListener('pointerdown', closeOutside);
    document.addEventListener('focusin', closeOutside);
    return () => {
      window.removeEventListener('resize', place);
      document.removeEventListener('scroll', place, true);
      document.removeEventListener('pointerdown', closeOutside);
      document.removeEventListener('focusin', closeOutside);
    };
  }, [open, options.length]);

  useEffect(() => {
    if (open) menu.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: 'nearest' });
  }, [open, active]);

  const choose = (index: number) => {
    if (options[index]?.disabled || !native.current) return;
    native.current.value = options[index].value;
    native.current.dispatchEvent(new Event('change', { bubbles: true }));
    setOpen(false);
    trigger.current?.focus();
  };
  const move = (start: number, step: number) => {
    for (let i = start; i >= 0 && i < options.length; i += step) {
      if (!options[i].disabled) { setActive(i); return; }
    }
  };

  return <span className={`compact-select ${className}`}>
    <select {...props} ref={native} className="compact-select-native" tabIndex={-1} aria-hidden="true" onInvalid={(e)=>{e.preventDefault();trigger.current?.focus({preventScroll:true});trigger.current?.scrollIntoView({behavior:'smooth',block:'center'});}}>{children}</select>
    <button ref={trigger} type="button" className="compact-select-trigger" role="combobox" disabled={props.disabled}
      aria-disabled={props['aria-disabled'] ?? (props.disabled ? 'true' : undefined)}
      aria-label={label || undefined} aria-labelledby={props['aria-labelledby']} aria-expanded={open} aria-controls={open ? id : undefined}
      aria-haspopup="listbox" aria-activedescendant={open ? `${id}-${active}` : undefined}
      onClick={() => { setActive(Math.max(0, selected)); setOpen(!open); }}
      onKeyDown={event => {
        if (event.key === 'Tab') { setOpen(false); return; }
        if (event.key === 'Escape') { event.preventDefault(); setOpen(false); return; }
        if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
          event.preventDefault();
          if (!open) { setOpen(true); setActive(Math.max(0, selected)); }
          else if (event.key === 'Home') move(0, 1);
          else if (event.key === 'End') move(options.length - 1, -1);
          else move(active + (event.key === 'ArrowDown' ? 1 : -1), event.key === 'ArrowDown' ? 1 : -1);
        } else if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          if (open) choose(active); else { setActive(Math.max(0, selected)); setOpen(true); }
        } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
          const now = Date.now();
          search.current = { text: (now - search.current.time < 700 ? search.current.text : '') + event.key.toLocaleLowerCase('ru'), time: now };
          const match = options.findIndex(option => !option.disabled && String(option.label).toLocaleLowerCase('ru').startsWith(search.current.text));
          if (match >= 0) { event.preventDefault(); setOpen(true); setActive(match); }
        }
      }}><span>{options[selected]?.label ?? 'Выберите значение'}</span><ChevronDown size={17} aria-hidden="true" /></button>
    {open && createPortal(<div ref={menu} id={id} role="listbox" aria-label={label || undefined} className="compact-select-menu" style={position}>
      {options.map((option, index) => <div key={`${option.value}-${index}`} id={`${id}-${index}`} role="option" aria-selected={index === selected}
        aria-disabled={option.disabled || undefined} data-index={index} className={`compact-select-option${index === active ? ' is-active' : ''}`}
        onPointerMove={() => !option.disabled && setActive(index)} onMouseDown={event => event.preventDefault()} onClick={() => choose(index)}>
        <span>{option.label}</span>{index === selected && <Check size={16} aria-hidden="true" />}
      </div>)}
    </div>, document.body)}
  </span>;
}
