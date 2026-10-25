import { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, ShieldCheck, X } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

type SectionItem = { id: string; name: string; icon: LucideIcon; disabled: boolean };

export function MobileSectionMenu({
  items,
  value,
  onChange,
}: {
  items: SectionItem[];
  value: string;
  onChange: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLElement>(null);
  const id = useId();

  const current = items.find((item) => item.id === value) ?? items[0];
  const CurrentIcon = current.icon;

  function close(returnFocus = false) {
    setOpen(false);
    if (returnFocus) {
      triggerRef.current?.focus({ preventScroll: true });
    }
  }

  useEffect(() => {
    if (!open) return;

    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        close(true);
      }
    };

    const desktop = window.matchMedia('(min-width: 761px)');
    const handleResize = () => {
      if (desktop.matches) close();
    };

    document.addEventListener('keydown', escape);
    desktop.addEventListener('change', handleResize);

    return () => {
      document.body.style.overflow = prevOverflow;
      document.removeEventListener('keydown', escape);
      desktop.removeEventListener('change', handleResize);
    };
  }, [open]);

  const drawerContent = (
    <>
      <div
        className={`mobile-drawer-backdrop ${open ? 'is-open' : ''}`}
        onClick={() => close(true)}
        aria-hidden="true"
      />
      <aside
        id={id}
        ref={drawerRef}
        className={`mobile-drawer-panel ${open ? 'is-open' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label="Навигация по разделам сервиса"
      >
        <div className="mobile-drawer-header">
          <div className="mobile-drawer-title">
            <span className="mobile-drawer-title-icon-wrap" aria-hidden="true">
              <CurrentIcon size={20} />
            </span>
            <div className="mobile-drawer-title-text">
              <h2>{current.name}</h2>
              <span className="mobile-drawer-subtitle">Разделы сервиса</span>
            </div>
          </div>
          <button
            type="button"
            className="mobile-drawer-close"
            onClick={() => close(true)}
            aria-label="Закрыть шторку"
          >
            <X size={20} aria-hidden="true" />
          </button>
        </div>

        <nav className="mobile-drawer-nav" aria-label="Разделы на мобильном экране">
          {items.map(({ id: itemId, name, icon: ItemIcon, disabled }) => {
            const active = itemId === value;
            return (
              <button
                key={itemId}
                type="button"
                disabled={disabled}
                title={disabled ? 'Функция не поддерживается подключенным сервером' : undefined}
                aria-current={active ? 'page' : undefined}
                className={`mobile-drawer-item ${active ? 'is-active' : ''}`}
                onClick={() => {
                  onChange(itemId);
                  close(true);
                }}
              >
                <span className="mobile-drawer-item-icon" aria-hidden="true">
                  <ItemIcon size={19} />
                </span>
                <span className="mobile-drawer-item-label">{name}</span>
                {active && <Check size={17} className="mobile-drawer-item-check" aria-hidden="true" />}
              </button>
            );
          })}
        </nav>

        <div className="mobile-drawer-footer">
          <div className="privacy-note">
            <ShieldCheck size={18} aria-hidden="true" />
            <p>Видны компании, к которым у вас есть доступ. После выхода доступ к данным закрывается.</p>
          </div>
        </div>
      </aside>
    </>
  );

  return (
    <div className="mobile-nav-container">
      <button
        ref={triggerRef}
        type="button"
        className="mobile-nav-toggle"
        aria-label={open ? 'Закрыть меню разделов' : `Открыть меню: ${current.name}`}
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        onClick={() => setOpen(!open)}
      >
        <span className="hamburger-box" aria-hidden="true">
          <span className="hamburger-line line-1" />
          <span className="hamburger-line line-2" />
          <span className="hamburger-line line-3" />
        </span>
      </button>
      {typeof document !== 'undefined' ? createPortal(drawerContent, document.body) : drawerContent}
    </div>
  );
}
