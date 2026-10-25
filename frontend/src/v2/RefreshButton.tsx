import { useRef, useState } from 'react';
import { RefreshCw } from 'lucide-react';

export function RefreshButton({ onRefresh }: { onRefresh: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);

  async function handleRefresh() {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    try {
      await onRefresh();
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  return <button type="button" className="button button-secondary workspace-refresh" disabled={busy} aria-busy={busy} onClick={() => void handleRefresh()}>
    <RefreshCw size={16} aria-hidden="true" />
    <span aria-live="polite">{busy ? 'Обновляем…' : 'Обновить данные'}</span>
  </button>;
}
