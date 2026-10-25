import { useLayoutEffect, useRef, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';

/** Keep a bounded number of complete rows visible, including multiline content. */
export function TableViewport({ children, label, visibleRows=7 }: { children: ReactNode; label: string; visibleRows?: number }) {
  const viewport = useRef<HTMLDivElement>(null);
  const [style, setStyle] = useState<CSSProperties>();

  useLayoutEffect(() => {
    const table = viewport.current?.querySelector('table');
    if (!table) return;
    const measure = () => {
      const caption = table.caption?.getBoundingClientRect().height ?? 0;
      const header = table.tHead?.getBoundingClientRect().height ?? 0;
      const rows = Array.from(table.tBodies[0]?.rows ?? []).slice(0, visibleRows);
      const horizontalScrollbar = Math.max(0, viewport.current!.offsetHeight - viewport.current!.clientHeight - 2);
      const height = caption + header + rows.reduce((sum, row) => sum + row.getBoundingClientRect().height, 0) + 2 + horizontalScrollbar;
      setStyle({ maxHeight: height, '--table-caption-height': `${caption}px` } as CSSProperties);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(table);
    return () => observer.disconnect();
  }, [children, visibleRows]);

  return <div ref={viewport} className="table-scroll seven-row-table" style={style} role="region" aria-label={label} tabIndex={0}>{children}</div>;
}
