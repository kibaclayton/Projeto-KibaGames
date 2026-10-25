import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { NexusApi, type Profile, type Session, type Summary } from './api';
import { clearDevice, loadDevice, saveDevice } from './device';

interface BackendState {
  session: Session | null; api: NexusApi; summary: Summary | null; summaryError: string; notice: string; restoring: boolean;
  enter: (session: Session) => void; leave: () => Promise<void>; refreshSummary: () => Promise<void>;
  updateProfile: (patch: Partial<Profile>) => void; expire: (notice: string) => void; forgetThisDevice: () => void;
}
const Context = createContext<BackendState | null>(null);

export function BackendProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [summaryError, setSummaryError] = useState('');
  const [notice, setNotice] = useState('');
  const [restoring, setRestoring] = useState(() => loadDevice() !== null);
  const summaryRequest = useRef<AbortController | null>(null);
  const token = session?.token;

  const enter = useCallback((next: Session) => {
    summaryRequest.current?.abort(); setSummary(null); setSummaryError(''); setNotice('');
    // A credencial do aparelho é trocada a cada uso; guardar a nova é o que mantém o acesso na próxima abertura.
    if (next.aparelho_token && next.aparelho_id) saveDevice({ id: next.aparelho_id, token: next.aparelho_token });
    setSession(next);
  }, []);
  const drop = useCallback((message: string) => { summaryRequest.current?.abort(); setSession(null); setSummary(null); setSummaryError(''); setNotice(message); }, []);
  // Um 401 com token: a sessão de 12 h acabou ou foi revogada. Se este aparelho é lembrado, renova sem pedir senha.
  // Vários pedidos falham ao mesmo tempo; só uma renovação corre por vez, senão a segunda usaria a credencial já trocada.
  const renewing = useRef<Promise<void> | null>(null);
  const expire = useCallback((message: string) => {
    if (renewing.current) return;
    const remembered = loadDevice();
    if (!remembered) { drop(message); return; }
    renewing.current = new NexusApi().deviceLogin(remembered.token).then(next => { enter(next); setNotice('Sessão renovada neste aparelho.'); })
      .catch(() => { clearDevice(); drop(message); })
      .finally(() => { renewing.current = null; });
  }, [drop, enter]);
  const api = useMemo(() => new NexusApi(token, () => expire('Sua sessão terminou. Selecione seu perfil e entre novamente.')), [token, expire]);

  useEffect(() => {
    // Abertura do app: entra sozinho quando este aparelho foi lembrado.
    const remembered = loadDevice();
    if (!remembered) return;
    const controller = new AbortController();
    new NexusApi().deviceLogin(remembered.token, controller.signal).then(next => { if (!controller.signal.aborted) enter(next); })
      .catch(cause => { if (!controller.signal.aborted) { if (cause instanceof Error && 'status' in cause && (cause as { status: number }).status === 401) clearDevice(); } })
      .finally(() => { if (!controller.signal.aborted) setRestoring(false); });
    return () => controller.abort();
  }, [enter]);

  const refreshSummary = useCallback(async () => {
    if (!token) return;
    summaryRequest.current?.abort();
    const controller = new AbortController();
    summaryRequest.current = controller;
    try {
      const result = await api.summary(controller.signal);
      if (!controller.signal.aborted) { setSummary(result); setSummaryError(''); }
    }
    catch (error) { if (!controller.signal.aborted) setSummaryError(error instanceof Error ? error.message : 'Não foi possível ler a biblioteca.'); }
  }, [api, token]);
  useEffect(() => {
    void refreshSummary();
    return () => summaryRequest.current?.abort();
  }, [refreshSummary]);

  const leave = async () => {
    summaryRequest.current?.abort();
    const remembered = loadDevice();
    try {
      if (remembered) { try { await api.forgetDevice(remembered.id); } catch { /* Já esquecido ou fora do ar: o token local é apagado mesmo assim. */ } }
      await api.logout();
    }
    finally { clearDevice(); summaryRequest.current?.abort(); setSession(null); setSummary(null); setSummaryError(''); }
  };
  const forgetThisDevice = () => clearDevice();
  const updateProfile = (patch: Partial<Profile>) => setSession(current => current ? { ...current, perfil: { ...current.perfil, ...patch } } : current);
  return <Context.Provider value={{ session, api, summary, summaryError, notice, restoring, enter, leave, refreshSummary, updateProfile, expire, forgetThisDevice }}>{children}</Context.Provider>;
}

export function useBackend() {
  const value = useContext(Context);
  if (!value) throw new Error('BackendProvider ausente');
  return value;
}
