import React from 'react';
import ReactDOM from 'react-dom/client';
import { MotionConfig } from 'framer-motion';
import '@fontsource/inter/latin-400.css';
import '@fontsource/inter/latin-500.css';
import '@fontsource/inter/latin-600.css';
import '@fontsource/inter/latin-700.css';
import './styles.css';
import { App } from './App';
import { ThemeProvider } from './theme/ThemeProvider';
import { BackendProvider } from './services/BackendProvider';

// Only phones on the LAN (HTTPS, non-loopback) get the installable shell; the desktop window keeps a plain page.
if ('serviceWorker' in navigator && window.location.protocol === 'https:' && !['127.0.0.1', 'localhost'].includes(window.location.hostname)) {
  window.addEventListener('load', () => { navigator.serviceWorker.register('/sw.js').catch(() => undefined); });
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><ThemeProvider><BackendProvider><MotionConfig reducedMotion="user"><App /></MotionConfig></BackendProvider></ThemeProvider></React.StrictMode>,
);
