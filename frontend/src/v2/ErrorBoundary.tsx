import { Component, type ErrorInfo, type ReactNode } from 'react';
import { TriangleAlert, RotateCcw, Copy, Check } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallbackTitle?: string;
  onReset?: () => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
  copied: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  public override state: State = {
    hasError: false,
    error: null,
    copied: false,
  };

  public static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  public override componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught error:', error, errorInfo);
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null, copied: false });
    this.props.onReset?.();
  };

  private handleCopy = () => {
    if (this.state.error) {
      void navigator.clipboard.writeText(`${this.state.error.name}: ${this.state.error.message}\n${this.state.error.stack ?? ''}`);
      this.setState({ copied: true });
      setTimeout(() => this.setState({ copied: false }), 2500);
    }
  };

  public override render() {
    if (this.state.hasError) {
      return (
        <div className="panel screen-panel error-boundary-panel" role="alert" style={{ padding: '2rem', textAlign: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.75rem', marginBottom: '1rem', color: '#dc2626' }}>
            <TriangleAlert size={28} />
            <h3 style={{ margin: 0 }}>{this.props.fallbackTitle ?? 'Произошла ошибка при отображении раздела'}</h3>
          </div>
          <p className="field-hint" style={{ maxWidth: '600px', margin: '0 auto 1.5rem auto' }}>
            {this.state.error?.message || 'Не удалось отрисовать данные раздела из-за непредвиденного формата ответа.'}
          </p>
          <div style={{ display: 'flex', gap: '10px', justifyContent: 'center', flexWrap: 'wrap' }}>
            <button className="button button-primary" onClick={this.handleReset}>
              <RotateCcw size={16} /> Попробовать снова
            </button>
            {this.state.error && (
              <button className="button button-secondary" type="button" onClick={this.handleCopy}>
                {this.state.copied ? <Check size={16} /> : <Copy size={16} />}
                {this.state.copied ? 'Скопировано' : 'Скопировать ошибку'}
              </button>
            )}
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
