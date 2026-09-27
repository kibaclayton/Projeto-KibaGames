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

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><ThemeProvider><BackendProvider><MotionConfig reducedMotion="user"><App /></MotionConfig></BackendProvider></ThemeProvider></React.StrictMode>,
);
