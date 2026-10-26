import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import type { Preferences } from '../services/api';

type Theme = 'dark' | 'light';
export const DEFAULT_PREFERENCES: Preferences = { tema: 'escuro', movimento: 'padrao', densidade: 'confortavel', destaque: 'roxo' };
const ALLOWED: { [K in keyof Preferences]: readonly Preferences[K][] } = {
  tema: ['escuro', 'claro'], movimento: ['padrao', 'reduzida', 'desligada'], densidade: ['confortavel', 'compacta'], destaque: ['roxo', 'magenta', 'verde', 'azul'],
};
const storageKey = 'nexus-wolfs:preferencias';
const legacyThemeKey = 'nexus-wolfs:theme';

/** Só valores aprovados do Design System entram; qualquer outra coisa cai no padrão. */
export function sanitizePreferences(value: unknown): Preferences {
  const source = (value && typeof value === 'object' ? value : {}) as Record<string, unknown>;
  const result = { ...DEFAULT_PREFERENCES };
  for (const key of Object.keys(ALLOWED) as (keyof Preferences)[]) {
    const candidate = source[key];
    if (typeof candidate === 'string' && (ALLOWED[key] as readonly string[]).includes(candidate)) (result as Record<string, string>)[key] = candidate;
  }
  return result;
}

/** Padrão do aparelho: usado sem sessão e como ponto de partida; o perfil conectado traz as suas próprias preferências. */
export function devicePreferences(): Preferences {
  try {
    const raw = localStorage.getItem(storageKey);
    if (raw) return sanitizePreferences(JSON.parse(raw));
    return { ...DEFAULT_PREFERENCES, tema: localStorage.getItem(legacyThemeKey) === 'light' ? 'claro' : 'escuro' };
  } catch { return DEFAULT_PREFERENCES; }
}

function apply(preferences: Preferences) {
  const root = document.documentElement;
  root.dataset.theme = preferences.tema === 'claro' ? 'light' : 'dark';
  root.dataset.motion = preferences.movimento;
  root.dataset.density = preferences.densidade;
  root.dataset.accent = preferences.destaque;
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', preferences.tema === 'claro' ? '#F4F5FA' : '#0A0B10');
}

const ThemeContext = createContext<{ theme: Theme; preferences: Preferences; setPreferences: (next: Preferences, rememberOnDevice: boolean) => void; toggleTheme: () => void } | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preferences, setState] = useState<Preferences>(devicePreferences);
  useEffect(() => apply(preferences), [preferences]);
  const setPreferences = useCallback((next: Preferences, rememberOnDevice: boolean) => {
    const clean = sanitizePreferences(next);
    setState(clean);
    if (rememberOnDevice) { try { localStorage.setItem(storageKey, JSON.stringify(clean)); } catch { /* Preferências continuam valendo na sessão. */ } }
  }, []);
  const theme: Theme = preferences.tema === 'claro' ? 'light' : 'dark';
  const toggleTheme = useCallback(() => setPreferences({ ...preferences, tema: preferences.tema === 'claro' ? 'escuro' : 'claro' }, true), [preferences, setPreferences]);
  return <ThemeContext.Provider value={{ theme, preferences, setPreferences, toggleTheme }}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const value = useContext(ThemeContext);
  if (!value) throw new Error('useTheme requires ThemeProvider');
  return value;
}
