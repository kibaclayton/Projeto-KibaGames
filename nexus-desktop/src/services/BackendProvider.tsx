import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { NexusApi, type Session, type Summary } from './api';

interface BackendState {
  session: Session | null; api: NexusApi; summary: Summary | null; summaryError: string;
  enter: (session: Session) => void; leave: () => Promise<void>; refreshSummary: () => Promise<void>;
}
const Context = createContext<BackendState | null>(null);

export function BackendProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [summaryError, setSummaryError] = useState('');
  const summaryRequest = useRef<AbortController | null>(null);
  const api = useMemo(() => new NexusApi(session?.token), [session]);
  const refreshSummary = useCallback(async () => {
    if (!session) return;
    summaryRequest.current?.abort();
    const controller = new AbortController();
    summaryRequest.current = controller;
    try {
      const result = await api.summary(controller.signal);
      if (!controller.signal.aborted) { setSummary(result); setSummaryError(''); }
    }
    catch (error) { if (!controller.signal.aborted) setSummaryError(error instanceof Error ? error.message : 'Não foi possível ler a biblioteca.'); }
  }, [api, session]);
  useEffect(() => {
    void refreshSummary();
    return () => summaryRequest.current?.abort();
  }, [refreshSummary]);
  const enter = (next: Session) => { summaryRequest.current?.abort(); setSummary(null); setSummaryError(''); setSession(next); };
  const leave = async () => {
    summaryRequest.current?.abort();
    try { await api.logout(); }
    finally { summaryRequest.current?.abort(); setSession(null); setSummary(null); setSummaryError(''); }
  };
  return <Context.Provider value={{ session, api, summary, summaryError, enter, leave, refreshSummary }}>{children}</Context.Provider>;
}

export function useBackend() {
  const value = useContext(Context);
  if (!value) throw new Error('BackendProvider ausente');
  return value;
}
