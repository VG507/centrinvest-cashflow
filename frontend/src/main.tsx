import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './v2/App';
import { ErrorBoundary } from './v2/ErrorBoundary';
import './styles.css';
import './v2/design.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary
      fallbackTitle="Произошла непредвиденная ошибка приложения"
      onReset={() => window.location.reload()}
    >
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
